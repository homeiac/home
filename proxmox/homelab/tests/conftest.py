"""Shared test fixtures and configuration for homelab tests."""

import os
import tempfile
from pathlib import Path
from typing import Dict, Any
from unittest import mock

import pytest


@pytest.fixture
def mock_proxmox():
    """Mock Proxmox API client for testing."""
    with mock.patch('homelab.proxmox_api.ProxmoxAPI') as mock_api:
        proxmox = mock.MagicMock()
        mock_api.return_value = proxmox
        
        # Setup common return values
        proxmox.nodes.get.return_value = [
            {"node": "pve"}, 
            {"node": "still-fawn"}, 
            {"node": "chief-horse"}
        ]
        proxmox.nodes.return_value.qemu.get.return_value = []
        proxmox.nodes.return_value.lxc.get.return_value = []
        proxmox.nodes.return_value.status.get.return_value = {
            "cpuinfo": {"cpus": 4},
            "memory": {"total": 8 * 1024**3}
        }
        
        yield proxmox


@pytest.fixture
def temp_ssh_key(tmp_path, monkeypatch):
    """Create temporary SSH key for testing."""
    key_file = tmp_path / "id_rsa.pub"
    key_file.write_text("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ test@example.com")
    monkeypatch.setenv("SSH_PUBKEY_PATH", str(key_file))
    return str(key_file)


@pytest.fixture
def mock_env(monkeypatch, temp_ssh_key):
    """Set up comprehensive test environment variables."""
    # First, clear any existing variables that might interfere from .env file
    for i in range(1, 20):
        for prefix in ["NODE_", "STORAGE_", "IMG_STORAGE_", "CPU_RATIO_", "MEMORY_RATIO_", "NETWORK_IFACES_"]:
            monkeypatch.delenv(f"{prefix}{i}", raising=False)
    
    # Also clear other potentially conflicting variables
    monkeypatch.delenv("API_TOKEN", raising=False)
    
    env_vars = {
        "API_TOKEN": "testuser!testtoken=secretvalue",
        "NODE_1": "pve",
        "NODE_2": "still-fawn", 
        "NODE_3": "chief-horse",
        "STORAGE_1": "local-zfs",
        "STORAGE_2": "local-2TB-zfs",
        "STORAGE_3": "local-256-gb-zfs",
        "IMG_STORAGE_1": "local-zfs",
        "IMG_STORAGE_2": "local-2TB-zfs", 
        "IMG_STORAGE_3": "local-256-gb-zfs",
        "CPU_RATIO_1": "0.5",
        "CPU_RATIO_2": "0.8",
        "CPU_RATIO_3": "0.5",
        "MEMORY_RATIO_1": "0.5",
        "MEMORY_RATIO_2": "0.8",
        "MEMORY_RATIO_3": "0.5",
        "NETWORK_IFACES_1": "vmbr0,vmbr25gbe",
        "NETWORK_IFACES_2": "vmbr25gbe",
        "NETWORK_IFACES_3": "vmbr0,vmbr1,vmbr2",
        "CLOUD_USER": "ubuntu",
        "CLOUD_PASSWORD": "ubuntu",
        "CLOUD_IP_CONFIG": "ip=dhcp",
        "VM_NAME_TEMPLATE": "k3s-vm-{node}",
        "VM_START_TIMEOUT": "180",
        "VM_DISK_SIZE": "200G",
        "ISO_NAME": "ubuntu-24.04.2-desktop-amd64.iso"
    }
    
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    
    return env_vars


@pytest.fixture
def mock_ssh_client():
    """Mock SSH client for testing remote operations."""
    with mock.patch('paramiko.SSHClient') as mock_ssh:
        client = mock.MagicMock()
        mock_ssh.return_value = client
        
        # Mock successful command execution
        stdout = mock.MagicMock()
        stderr = mock.MagicMock()
        stdout.read.return_value.decode.return_value = "command output"
        stderr.read.return_value.decode.return_value = ""
        
        client.exec_command.return_value = (None, stdout, stderr)
        
        yield client


@pytest.fixture
def sample_node_status() -> Dict[str, Any]:
    """Sample node status data for testing."""
    return {
        "cpuinfo": {
            "cpus": 8,
            "model": "Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz"
        },
        "memory": {
            "total": 16 * 1024**3,  # 16GB
            "used": 4 * 1024**3,    # 4GB used
            "free": 12 * 1024**3    # 12GB free
        },
        "loadavg": [0.5, 0.3, 0.2],
        "uptime": 86400
    }


@pytest.fixture
def sample_vm_config() -> Dict[str, Any]:
    """Sample VM configuration for testing."""
    return {
        "vmid": 108,
        "name": "k3s-vm-still-fawn",
        "cores": 4,
        "memory": 8192,
        "net0": "virtio,bridge=vmbr25gbe",
        "scsi0": "local-2TB-zfs:vm-108-disk-0",
        "agent": 1,
        "boot": "c",
        "bootdisk": "scsi0"
    }


@pytest.fixture
def sample_lxc_config() -> Dict[str, Any]:
    """Sample LXC configuration for testing."""
    return {
        "vmid": 100,
        "hostname": "uptime-kuma-pve",
        "memory": 2048,
        "cores": 2,
        "rootfs": "local-zfs:subvol-100-disk-0,size=24G",
        "net0": "name=eth0,bridge=vmbr25gbe,dhcp=1",
        "features": "nest=1,keyctl=1",
        "unprivileged": 1
    }


@pytest.fixture
def temp_config_file(tmp_path):
    """Create temporary configuration file for testing."""
    config_file = tmp_path / "test_config.env"
    config_content = """
API_TOKEN=testuser!testtoken=secret
NODE_1=test-node
STORAGE_1=local-zfs
    """.strip()
    config_file.write_text(config_content)
    return str(config_file)


@pytest.fixture(autouse=True)
def cleanup_environment():
    """Automatically clean up test environment after each test."""
    yield
    # Cleanup any test artifacts or reset global state if needed
    pass


@pytest.fixture
def mock_docker_client():
    """Mock Docker client for container operations."""
    with mock.patch('docker.from_env') as mock_docker:
        client = mock.MagicMock()
        mock_docker.return_value = client
        
        # Mock container operations
        container = mock.MagicMock()
        container.id = "test-container-id"
        container.status = "running"
        client.containers.run.return_value = container
        client.containers.get.return_value = container
        
        yield client


@pytest.fixture
def mock_uptime_kuma_api():
    """Mock Uptime Kuma API for monitoring configuration."""
    with mock.patch('requests.post') as mock_post, \
         mock.patch('requests.get') as mock_get:
        
        # Mock successful API responses
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "success"}
        
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"monitors": []}
        
        yield {"post": mock_post, "get": mock_get}