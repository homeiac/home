"""Tests for monitoring_manager module."""

import time
from unittest import mock

import pytest
import requests

from homelab.monitoring_manager import MonitoringManager, deploy_monitoring_to_all_nodes, get_monitoring_status_all_nodes


@pytest.fixture
def monitoring_manager(mock_env, temp_ssh_key):
    """Create MonitoringManager instance for testing."""
    with mock.patch('homelab.monitoring_manager.ProxmoxClient') as mock_client:
        manager = MonitoringManager("test-node")
        manager.client = mock_client.return_value
        yield manager


@pytest.fixture
def mock_ssh_operations():
    """Mock SSH operations for monitoring manager."""
    with mock.patch('paramiko.SSHClient') as mock_ssh_class:
        ssh_client = mock.MagicMock()
        mock_ssh_class.return_value = ssh_client
        
        # Mock successful command execution by default
        stdout = mock.MagicMock()
        stderr = mock.MagicMock()
        stdout.read.return_value.decode.return_value = "command output"
        stdout.channel.recv_exit_status.return_value = 0
        stderr.read.return_value.decode.return_value = ""
        
        ssh_client.exec_command.return_value = (None, stdout, stderr)
        
        yield ssh_client


def test_monitoring_manager_init(mock_env, temp_ssh_key):
    """Test MonitoringManager initialization."""
    with mock.patch('homelab.monitoring_manager.ProxmoxClient') as mock_client:
        manager = MonitoringManager("test-node")
        
        assert manager.node_name == "test-node"
        assert manager.client is not None
        assert manager.ssh_client is None
        mock_client.assert_called_once_with("test-node")


def test_get_ssh_client(monitoring_manager, mock_ssh_operations):
    """Test SSH client creation and caching."""
    # First call should create SSH client
    client1 = monitoring_manager._get_ssh_client()
    assert client1 is not None
    
    # Second call should return cached client
    client2 = monitoring_manager._get_ssh_client()
    assert client1 is client2


def test_execute_command(monitoring_manager, mock_ssh_operations):
    """Test command execution via SSH."""
    mock_ssh_operations.exec_command.return_value[1].read.return_value.decode.return_value = "test output"
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
    mock_ssh_operations.exec_command.return_value[2].read.return_value.decode.return_value = ""
    
    stdout, stderr, exit_code = monitoring_manager._execute_command("test command")
    
    assert stdout == "test output"
    assert stderr == ""
    assert exit_code == 0
    mock_ssh_operations.exec_command.assert_called_once_with("test command")


def test_find_docker_lxc_by_hostname(monitoring_manager, mock_ssh_operations):
    """Test finding Docker LXC by hostname pattern."""
    # Mock LXC container list
    monitoring_manager.client.proxmox.nodes.return_value.lxc.get.return_value = [
        {"vmid": 100, "status": "running"},
        {"vmid": 101, "status": "running"},
    ]
    
    # Mock container configs
    monitoring_manager.client.proxmox.nodes.return_value.lxc.return_value.config.get.side_effect = [
        {"hostname": "docker-test-node"},  # First container matches
        {"hostname": "other-container"},   # Second doesn't match
    ]
    
    vmid = monitoring_manager._find_docker_lxc()
    assert vmid == 100


def test_find_docker_lxc_by_docker_installation(monitoring_manager, mock_ssh_operations):
    """Test finding Docker LXC by checking for Docker installation."""
    # Mock LXC container list
    monitoring_manager.client.proxmox.nodes.return_value.lxc.get.return_value = [
        {"vmid": 100, "status": "running"},
    ]
    
    # Mock container config without docker in hostname
    monitoring_manager.client.proxmox.nodes.return_value.lxc.return_value.config.get.return_value = {
        "hostname": "regular-container"
    }
    
    # Mock successful docker command (docker found)
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
    
    vmid = monitoring_manager._find_docker_lxc()
    assert vmid == 100


def test_find_docker_lxc_not_found(monitoring_manager, mock_ssh_operations):
    """Test when no Docker LXC is found."""
    # Mock empty LXC container list
    monitoring_manager.client.proxmox.nodes.return_value.lxc.get.return_value = []
    
    vmid = monitoring_manager._find_docker_lxc()
    assert vmid is None


def test_get_next_available_vmid(monitoring_manager):
    """Test finding next available VMID."""
    # Mock existing VMs and containers
    monitoring_manager.client.proxmox.nodes.return_value.qemu.get.return_value = [
        {"vmid": 100}, {"vmid": 102}
    ]
    monitoring_manager.client.proxmox.nodes.return_value.lxc.get.return_value = [
        {"vmid": 101}, {"vmid": 103}
    ]
    
    vmid = monitoring_manager._get_next_available_vmid()
    assert vmid == 104  # First available after 100, 101, 102, 103


def test_wait_for_container_ready_success(monitoring_manager, mock_ssh_operations):
    """Test successful container ready wait."""
    # Mock container status as running
    monitoring_manager.client.proxmox.nodes.return_value.lxc.return_value.status.current.get.return_value = {
        "status": "running"
    }
    
    # Mock successful ready check
    mock_ssh_operations.exec_command.return_value[1].read.return_value.decode.return_value = "ready"
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
    
    # Should not raise an exception
    monitoring_manager._wait_for_container_ready(100, timeout=1)


def test_wait_for_container_ready_timeout(monitoring_manager, mock_ssh_operations):
    """Test container ready wait timeout."""
    # Mock container status as not running
    monitoring_manager.client.proxmox.nodes.return_value.lxc.return_value.status.current.get.return_value = {
        "status": "stopped"
    }
    
    with pytest.raises(RuntimeError, match="did not become ready"):
        monitoring_manager._wait_for_container_ready(100, timeout=1)


def test_install_docker_in_lxc_success(monitoring_manager, mock_ssh_operations):
    """Test successful Docker installation in LXC."""
    # Mock all commands succeed
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
    
    # Mock docker version check
    def mock_exec_command(cmd):
        stdout = mock.MagicMock()
        stderr = mock.MagicMock()
        
        if "docker --version" in cmd:
            stdout.read.return_value.decode.return_value = "Docker version 24.0.0"  
        else:
            stdout.read.return_value.decode.return_value = "command output"
            
        stdout.channel.recv_exit_status.return_value = 0
        stderr.read.return_value.decode.return_value = ""
        return (None, stdout, stderr)
    
    mock_ssh_operations.exec_command.side_effect = mock_exec_command
    
    # Should not raise an exception
    monitoring_manager._install_docker_in_lxc(100)


def test_install_docker_in_lxc_failure(monitoring_manager, mock_ssh_operations):
    """Test Docker installation failure in LXC."""
    # Mock command failure
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 1
    mock_ssh_operations.exec_command.return_value[2].read.return_value.decode.return_value = "command failed"
    
    with pytest.raises(RuntimeError, match="Docker installation failed"):
        monitoring_manager._install_docker_in_lxc(100)


def test_container_exists_true(monitoring_manager, mock_ssh_operations):
    """Test checking if Docker container exists (true case)."""
    mock_ssh_operations.exec_command.return_value[1].read.return_value.decode.return_value = "uptime-kuma"
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
    
    exists = monitoring_manager._container_exists(100, "uptime-kuma")
    assert exists is True


def test_container_exists_false(monitoring_manager, mock_ssh_operations):
    """Test checking if Docker container exists (false case)."""
    mock_ssh_operations.exec_command.return_value[1].read.return_value.decode.return_value = ""
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
    
    exists = monitoring_manager._container_exists(100, "uptime-kuma")
    assert exists is False


def test_container_is_running_true(monitoring_manager, mock_ssh_operations):
    """Test checking if Docker container is running (true case)."""
    mock_ssh_operations.exec_command.return_value[1].read.return_value.decode.return_value = "uptime-kuma"
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
    
    running = monitoring_manager._container_is_running(100, "uptime-kuma")
    assert running is True


def test_container_is_running_false(monitoring_manager, mock_ssh_operations):
    """Test checking if Docker container is running (false case)."""
    mock_ssh_operations.exec_command.return_value[1].read.return_value.decode.return_value = ""
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
    
    running = monitoring_manager._container_is_running(100, "uptime-kuma")
    assert running is False


def test_get_container_ip_success(monitoring_manager, mock_ssh_operations):
    """Test getting container IP address."""
    mock_ssh_operations.exec_command.return_value[1].read.return_value.decode.return_value = "192.168.1.123"
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
    
    ip = monitoring_manager._get_container_ip(100)
    assert ip == "192.168.1.123"


def test_get_container_ip_failure(monitoring_manager, mock_ssh_operations):
    """Test getting container IP address failure."""
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 1
    
    ip = monitoring_manager._get_container_ip(100)
    assert ip is None


@mock.patch('requests.get')
def test_wait_for_uptime_kuma_ready_success(mock_get, monitoring_manager, mock_ssh_operations):
    """Test waiting for Uptime Kuma to be ready (success case)."""
    # Mock container IP
    mock_ssh_operations.exec_command.return_value[1].read.return_value.decode.return_value = "192.168.1.123"
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
    
    # Mock successful HTTP response
    mock_get.return_value.status_code = 200
    
    # Should not raise an exception
    monitoring_manager._wait_for_uptime_kuma_ready(100, 3001, timeout=1)
    
    mock_get.assert_called_with("http://192.168.1.123:3001", timeout=5)


@mock.patch('requests.get')
def test_wait_for_uptime_kuma_ready_no_ip(mock_get, monitoring_manager, mock_ssh_operations):
    """Test waiting for Uptime Kuma when IP cannot be determined."""
    # Mock no IP returned
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 1
    
    # Should not raise an exception, just sleep and return
    monitoring_manager._wait_for_uptime_kuma_ready(100, 3001, timeout=1)
    
    # HTTP request should not be made
    mock_get.assert_not_called()


def test_deploy_uptime_kuma_already_running(monitoring_manager, mock_ssh_operations):
    """Test deploying Uptime Kuma when it's already running."""
    # Mock finding existing Docker LXC
    with mock.patch.object(monitoring_manager, '_find_docker_lxc', return_value=100):
        with mock.patch.object(monitoring_manager, '_container_exists', return_value=True):
            with mock.patch.object(monitoring_manager, '_container_is_running', return_value=True):
                with mock.patch.object(monitoring_manager, '_get_container_ip', return_value="192.168.1.123"):
                    
                    result = monitoring_manager.deploy_uptime_kuma()
                    
                    assert result["status"] == "already_running"
                    assert result["vmid"] == 100
                    assert result["container_ip"] == "192.168.1.123"
                    assert result["url"] == "http://192.168.1.123:3001"


def test_deploy_uptime_kuma_start_existing_container(monitoring_manager, mock_ssh_operations):
    """Test deploying Uptime Kuma by starting existing stopped container."""
    # Mock finding existing Docker LXC
    with mock.patch.object(monitoring_manager, '_find_docker_lxc', return_value=100):
        with mock.patch.object(monitoring_manager, '_container_exists', return_value=True):
            with mock.patch.object(monitoring_manager, '_container_is_running', return_value=False):
                with mock.patch.object(monitoring_manager, '_get_container_ip', return_value="192.168.1.123"):
                    with mock.patch.object(monitoring_manager, '_wait_for_uptime_kuma_ready'):
                        
                        result = monitoring_manager.deploy_uptime_kuma()
                        
                        assert result["status"] == "deployed"
                        assert result["vmid"] == 100
                        
                        # Verify start command was called
                        mock_ssh_operations.exec_command.assert_any_call("pct exec 100 -- docker start uptime-kuma")


def test_deploy_uptime_kuma_create_new_container(monitoring_manager, mock_ssh_operations):
    """Test deploying Uptime Kuma by creating new container."""
    # Mock successful command execution
    mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
    mock_ssh_operations.exec_command.return_value[1].read.return_value.decode.return_value = "container_id_123"
    
    # Mock finding existing Docker LXC
    with mock.patch.object(monitoring_manager, '_find_docker_lxc', return_value=100):
        with mock.patch.object(monitoring_manager, '_container_exists', return_value=False):
            with mock.patch.object(monitoring_manager, '_get_container_ip', return_value="192.168.1.123"):
                with mock.patch.object(monitoring_manager, '_wait_for_uptime_kuma_ready'):
                    
                    result = monitoring_manager.deploy_uptime_kuma()
                    
                    assert result["status"] == "deployed"
                    assert result["vmid"] == 100
                    
                    # Verify docker run command was called
                    calls = [call[0][0] for call in mock_ssh_operations.exec_command.call_args_list]
                    assert any("docker run" in call for call in calls)


def test_deploy_uptime_kuma_create_new_lxc(monitoring_manager, mock_ssh_operations):
    """Test deploying Uptime Kuma by creating new Docker LXC."""
    with mock.patch.object(monitoring_manager, '_find_docker_lxc', return_value=None):
        with mock.patch.object(monitoring_manager, '_create_docker_lxc', return_value=101):
            with mock.patch.object(monitoring_manager, '_container_exists', return_value=False):
                with mock.patch.object(monitoring_manager, '_get_container_ip', return_value="192.168.1.124"):
                    with mock.patch.object(monitoring_manager, '_wait_for_uptime_kuma_ready'):
                        
                        # Mock successful docker run
                        mock_ssh_operations.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
                        mock_ssh_operations.exec_command.return_value[1].read.return_value.decode.return_value = "container_id"
                        
                        result = monitoring_manager.deploy_uptime_kuma()
                        
                        assert result["status"] == "deployed"
                        assert result["vmid"] == 101


def test_get_monitoring_status_with_uptime_kuma(monitoring_manager, mock_ssh_operations):
    """Test getting monitoring status when Uptime Kuma is present."""
    with mock.patch.object(monitoring_manager, '_find_docker_lxc', return_value=100):
        with mock.patch.object(monitoring_manager, '_get_container_ip', return_value="192.168.1.123"):
            with mock.patch.object(monitoring_manager, '_container_exists', return_value=True):
                with mock.patch.object(monitoring_manager, '_container_is_running', return_value=True):
                    
                    status = monitoring_manager.get_monitoring_status()
                    
                    assert status["node"] == "test-node"
                    assert status["docker_lxc"]["vmid"] == 100
                    assert status["docker_lxc"]["ip"] == "192.168.1.123"
                    assert status["uptime_kuma"]["running"] is True
                    assert status["uptime_kuma"]["url"] == "http://192.168.1.123:3001"


def test_get_monitoring_status_no_docker_lxc(monitoring_manager):
    """Test getting monitoring status when no Docker LXC exists."""
    with mock.patch.object(monitoring_manager, '_find_docker_lxc', return_value=None):
        
        status = monitoring_manager.get_monitoring_status()
        
        assert status["node"] == "test-node"
        assert status["docker_lxc"] is None
        assert status["uptime_kuma"] is None


def test_context_manager(mock_env, temp_ssh_key):
    """Test MonitoringManager as context manager."""
    with mock.patch('homelab.monitoring_manager.ProxmoxClient'):
        with MonitoringManager("test-node") as manager:
            assert manager.node_name == "test-node"
        # Cleanup should be called automatically


@mock.patch('homelab.monitoring_manager.Config')
def test_deploy_monitoring_to_all_nodes_success(mock_config, mock_env, temp_ssh_key):
    """Test deploying monitoring to all nodes successfully."""
    mock_config.get_nodes.return_value = [
        {"name": "node1"},
        {"name": "node2"},
    ]
    
    with mock.patch('homelab.monitoring_manager.MonitoringManager') as mock_manager_class:
        # Mock the context manager properly
        mock_manager = mock.MagicMock()
        mock_manager.deploy_uptime_kuma.return_value = {"status": "deployed", "url": "http://192.168.1.123:3001"}
        mock_manager_class.return_value.__enter__ = mock.MagicMock(return_value=mock_manager)
        mock_manager_class.return_value.__exit__ = mock.MagicMock(return_value=None)
        
        results = deploy_monitoring_to_all_nodes()
        
        # Basic functionality checks
        assert len(results) == 2
        assert all(result["status"] == "deployed" for result in results)
        assert all("node" in result for result in results)
        assert all("url" in result for result in results)
        
        # Verify MonitoringManager was called for each node
        assert mock_manager_class.call_count == 2


@mock.patch('homelab.monitoring_manager.Config')
def test_deploy_monitoring_to_all_nodes_with_failure(mock_config, mock_env, temp_ssh_key):
    """Test deploying monitoring to all nodes with one failure."""
    mock_config.get_nodes.return_value = [
        {"name": "node1"},
        {"name": "node2"},
    ]
    
    with mock.patch('homelab.monitoring_manager.MonitoringManager') as mock_manager_class:
        mock_manager = mock.MagicMock()
        mock_manager_class.return_value.__enter__.return_value = mock_manager
        
        # First node succeeds, second fails
        mock_manager.deploy_uptime_kuma.side_effect = [
            {"status": "deployed", "url": "http://192.168.1.123:3001"},
            RuntimeError("Connection failed")
        ]
        
        results = deploy_monitoring_to_all_nodes()
        
        assert len(results) == 2
        assert results[0]["status"] == "deployed"
        assert results[1]["status"] == "failed"
        assert "Connection failed" in results[1]["error"]


@mock.patch('homelab.monitoring_manager.Config')
def test_get_monitoring_status_all_nodes(mock_config, mock_env, temp_ssh_key):
    """Test getting monitoring status from all nodes."""
    mock_config.get_nodes.return_value = [
        {"name": "node1"},
        {"name": "node2"},
    ]
    
    with mock.patch('homelab.monitoring_manager.MonitoringManager') as mock_manager_class:
        mock_manager = mock.MagicMock()
        mock_manager_class.return_value.__enter__.return_value = mock_manager
        mock_manager.get_monitoring_status.return_value = {
            "node": "test-node",
            "docker_lxc": {"vmid": 100},
            "uptime_kuma": {"running": True}
        }
        
        results = get_monitoring_status_all_nodes()
        
        assert len(results) == 2
        assert all("node" in result for result in results)


def test_cleanup(monitoring_manager):
    """Test cleanup method."""
    # Set up mock SSH client
    mock_ssh = mock.MagicMock()
    monitoring_manager.ssh_client = mock_ssh
    
    monitoring_manager.cleanup()
    
    mock_ssh.close.assert_called_once()
    assert monitoring_manager.ssh_client is None