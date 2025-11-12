"""Tests for vm_manager module."""

import os
import time
from unittest import mock

import pytest

from homelab.vm_manager import VMManager


def test_vm_exists_found(mock_proxmox, mock_env, temp_ssh_key):
    """Test vm_exists returns vmid when VM exists."""
    mock_proxmox.nodes.return_value.qemu.get.return_value = [
        {"vmid": "108", "name": "k3s-vm-test-node"},
        {"vmid": "109", "name": "other-vm"}
    ]
    
    vmid = VMManager.vm_exists(mock_proxmox, "test_node")
    assert vmid == 108


def test_vm_exists_not_found(mock_proxmox, mock_env, temp_ssh_key):
    """Test vm_exists returns None when VM doesn't exist."""
    mock_proxmox.nodes.return_value.qemu.get.return_value = [
        {"vmid": "109", "name": "other-vm"}
    ]
    
    vmid = VMManager.vm_exists(mock_proxmox, "test_node")
    assert vmid is None


def test_vm_exists_handles_underscores(mock_proxmox, mock_env, temp_ssh_key):
    """Test vm_exists converts underscores to hyphens in node names."""
    mock_proxmox.nodes.return_value.qemu.get.return_value = [
        {"vmid": "108", "name": "k3s-vm-test-node"}
    ]
    
    vmid = VMManager.vm_exists(mock_proxmox, "test_node")
    assert vmid == 108


def test_get_next_available_vmid_standard_case(mock_proxmox):
    """Test get_next_available_vmid with standard scenario."""
    mock_proxmox.nodes.get.return_value = [{"node": "pve1"}, {"node": "pve2"}]
    mock_proxmox.nodes.return_value.qemu.get.side_effect = [
        [{"vmid": "100"}, {"vmid": "101"}], 
        [{"vmid": "200"}]
    ]
    mock_proxmox.nodes.return_value.lxc.get.side_effect = [[], []]

    vmid = VMManager.get_next_available_vmid(mock_proxmox)
    assert vmid == 102  # First available after 100, 101


def test_get_next_available_vmid_with_lxc(mock_proxmox):
    """Test get_next_available_vmid considers LXC containers."""
    mock_proxmox.nodes.get.return_value = [{"node": "pve1"}]
    mock_proxmox.nodes.return_value.qemu.get.side_effect = [[{"vmid": "100"}]]
    mock_proxmox.nodes.return_value.lxc.get.side_effect = [[{"vmid": "101"}]]

    vmid = VMManager.get_next_available_vmid(mock_proxmox)
    assert vmid == 102


def test_get_next_available_vmid_no_available_raises_error(mock_proxmox):
    """Test get_next_available_vmid raises error when no VMIDs available."""
    mock_proxmox.nodes.get.return_value = [{"node": "pve1"}]
    # Mock all VMIDs as used
    used_vmids = [{"vmid": str(i)} for i in range(100, 9999)]
    mock_proxmox.nodes.return_value.qemu.get.side_effect = [used_vmids]
    mock_proxmox.nodes.return_value.lxc.get.side_effect = [[]]

    with pytest.raises(RuntimeError, match="No available VMIDs found"):
        VMManager.get_next_available_vmid(mock_proxmox)


@mock.patch('homelab.vm_manager.paramiko.SSHClient')
def test_import_disk_via_cli(mock_ssh_class, mock_env):
    """Test _import_disk_via_cli SSH operations."""
    mock_client = mock.MagicMock()
    mock_ssh_class.return_value = mock_client
    
    # Mock command execution
    mock_stdout = mock.MagicMock()
    mock_stderr = mock.MagicMock()
    mock_stdout.read.return_value.decode.return_value = "disk imported successfully"
    mock_stderr.read.return_value.decode.return_value = ""
    mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
    
    VMManager._import_disk_via_cli("test-host", 108, "/path/to/image.img", "local-zfs")
    
    mock_client.connect.assert_called_once_with(
        hostname="test-host", 
        username="root", 
        key_filename=os.path.expanduser("~/.ssh/id_rsa")
    )
    mock_client.exec_command.assert_called_once_with(
        "qm importdisk 108 /path/to/image.img local-zfs"
    )
    mock_client.close.assert_called_once()


@mock.patch('homelab.vm_manager.paramiko.SSHClient')
def test_import_disk_via_cli_with_error(mock_ssh_class, mock_env):
    """Test _import_disk_via_cli handles SSH errors."""
    mock_client = mock.MagicMock()
    mock_ssh_class.return_value = mock_client
    
    # Mock command execution with error
    mock_stdout = mock.MagicMock()
    mock_stderr = mock.MagicMock()
    mock_stdout.read.return_value.decode.return_value = ""
    mock_stderr.read.return_value.decode.return_value = "disk import failed"
    mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
    
    VMManager._import_disk_via_cli("test-host", 108, "/path/to/image.img", "local-zfs")
    
    mock_client.exec_command.assert_called_once()


@mock.patch('homelab.vm_manager.paramiko.SSHClient')
def test_resize_disk_via_cli(mock_ssh_class, mock_env):
    """Test _resize_disk_via_cli SSH operations."""
    mock_client = mock.MagicMock()
    mock_ssh_class.return_value = mock_client
    
    # Mock command execution
    mock_stdout = mock.MagicMock()
    mock_stderr = mock.MagicMock()
    mock_stdout.read.return_value.decode.return_value = "disk resized successfully"
    mock_stderr.read.return_value.decode.return_value = ""
    mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
    
    VMManager._resize_disk_via_cli("test-host", 108, "scsi0", "200G")
    
    mock_client.connect.assert_called_once_with(
        hostname="test-host", 
        username="root", 
        key_filename=os.path.expanduser("~/.ssh/id_rsa")
    )
    mock_client.exec_command.assert_called_once_with(
        "qm resize 108 scsi0 200G"
    )
    mock_client.close.assert_called_once()


@mock.patch('homelab.vm_manager.paramiko.SSHClient')
def test_resize_disk_via_cli_with_error(mock_ssh_class, mock_env):
    """Test _resize_disk_via_cli handles SSH errors."""
    mock_client = mock.MagicMock()
    mock_ssh_class.return_value = mock_client
    
    # Mock command execution with error
    mock_stdout = mock.MagicMock()
    mock_stderr = mock.MagicMock()
    mock_stdout.read.return_value.decode.return_value = ""
    mock_stderr.read.return_value.decode.return_value = "resize failed"
    mock_client.exec_command.return_value = (None, mock_stdout, mock_stderr)
    
    VMManager._resize_disk_via_cli("test-host", 108, "scsi0", "200G")
    
    mock_client.exec_command.assert_called_once()


@mock.patch('homelab.vm_manager.VMManager._resize_disk_via_cli')
@mock.patch('homelab.vm_manager.VMManager._import_disk_via_cli')
@mock.patch('homelab.vm_manager.VMManager.get_next_available_vmid')
@mock.patch('homelab.vm_manager.VMManager.vm_exists')
@mock.patch('homelab.vm_manager.ResourceManager.calculate_vm_resources')
@mock.patch('homelab.vm_manager.ProxmoxClient')
@mock.patch('homelab.vm_manager.Config.get_nodes')
@mock.patch('homelab.vm_manager.Config.get_network_ifaces_for')
@mock.patch('time.sleep')
def test_create_or_update_vm_skips_existing(
    mock_sleep, mock_get_ifaces, mock_get_nodes, mock_client_class, 
    mock_calc_resources, mock_vm_exists, mock_get_vmid, 
    mock_import_disk, mock_resize_disk, mock_env
):
    """Test create_or_update_vm skips existing VMs."""
    # Setup mocks
    mock_get_nodes.return_value = [{"name": "test-node", "img_storage": "local-zfs"}]
    mock_vm_exists.return_value = 108  # VM exists
    
    VMManager.create_or_update_vm()
    
    # Should not create new VM if one exists
    mock_get_vmid.assert_not_called()
    mock_import_disk.assert_not_called()


@mock.patch('homelab.vm_manager.VMManager._resize_disk_via_cli')
@mock.patch('homelab.vm_manager.VMManager._import_disk_via_cli')
@mock.patch('homelab.vm_manager.VMManager.get_next_available_vmid')
@mock.patch('homelab.vm_manager.VMManager.vm_exists')
@mock.patch('homelab.vm_manager.ResourceManager.calculate_vm_resources')
@mock.patch('homelab.vm_manager.ProxmoxClient')
@mock.patch('homelab.vm_manager.Config.get_nodes')
@mock.patch('homelab.vm_manager.Config.get_network_ifaces_for')
@mock.patch('time.sleep')
def test_create_or_update_vm_skips_no_storage(
    mock_sleep, mock_get_ifaces, mock_get_nodes, mock_client_class, 
    mock_calc_resources, mock_vm_exists, mock_get_vmid, 
    mock_import_disk, mock_resize_disk, mock_env
):
    """Test create_or_update_vm skips nodes without storage."""
    # Setup mocks
    mock_get_nodes.return_value = [{"name": "test-node", "img_storage": None}]
    
    VMManager.create_or_update_vm()
    
    # Should not attempt VM operations
    mock_vm_exists.assert_not_called()
    mock_get_vmid.assert_not_called()


@mock.patch('homelab.vm_manager.VMManager._resize_disk_via_cli')
@mock.patch('homelab.vm_manager.VMManager._import_disk_via_cli') 
@mock.patch('homelab.vm_manager.VMManager.get_next_available_vmid')
@mock.patch('homelab.vm_manager.VMManager.vm_exists')
@mock.patch('homelab.vm_manager.ResourceManager.calculate_vm_resources')
@mock.patch('homelab.vm_manager.ProxmoxClient')
@mock.patch('homelab.vm_manager.Config.get_nodes')
@mock.patch('homelab.vm_manager.Config.get_network_ifaces_for')
@mock.patch('time.sleep')
def test_create_or_update_vm_creates_new_vm(
    mock_sleep, mock_get_ifaces, mock_get_nodes, mock_client_class, 
    mock_calc_resources, mock_vm_exists, mock_get_vmid, 
    mock_import_disk, mock_resize_disk, mock_env
):
    """Test create_or_update_vm creates new VM when none exists."""
    # Setup mocks
    mock_get_nodes.return_value = [{"name": "test-node", "img_storage": "local-zfs", "cpu_ratio": 0.5, "memory_ratio": 0.5}]
    mock_get_ifaces.return_value = ["vmbr0", "vmbr25gbe"]
    mock_vm_exists.return_value = None  # No existing VM
    mock_get_vmid.return_value = 108
    mock_calc_resources.return_value = (4, 8 * 1024**3)  # 4 CPUs, 8GB RAM
    
    # Setup client mock
    mock_client = mock.MagicMock()
    mock_proxmox = mock.MagicMock()
    mock_client.proxmox = mock_proxmox
    mock_client.get_node_status.return_value = {"cpuinfo": {"cpus": 8}, "memory": {"total": 16 * 1024**3}}
    mock_client_class.return_value = mock_client
    
    # Mock VM status progression
    mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.side_effect = [
        {"status": "starting"},
        {"status": "running"}
    ]
    
    VMManager.create_or_update_vm()
    
    # Verify VM creation process
    mock_proxmox.nodes.return_value.qemu.create.assert_called_once()
    create_args = mock_proxmox.nodes.return_value.qemu.create.call_args[1]
    assert create_args["vmid"] == 108
    assert create_args["name"] == "k3s-vm-test-node"
    assert create_args["cores"] == 4
    assert create_args["memory"] == 8192  # 8GB in MB
    assert "net0" in create_args
    assert "net1" in create_args
    
    # Verify disk import and resize
    mock_import_disk.assert_called_once_with(
        host="test-node",
        vmid=108,
        img_path="/var/lib/vz/template/iso/ubuntu-24.04.2-desktop-amd64.iso",
        storage="local-zfs"
    )
    mock_resize_disk.assert_called_once_with(
        host="test-node",
        vmid=108,
        disk="scsi0",
        size="200G"
    )
    
    # Verify VM start
    mock_proxmox.nodes.return_value.qemu.return_value.status.start.post.assert_called_once()


@mock.patch('homelab.vm_manager.VMManager._resize_disk_via_cli')
@mock.patch('homelab.vm_manager.VMManager._import_disk_via_cli')
@mock.patch('homelab.vm_manager.VMManager.get_next_available_vmid')
@mock.patch('homelab.vm_manager.VMManager.vm_exists')
@mock.patch('homelab.vm_manager.ResourceManager.calculate_vm_resources')
@mock.patch('homelab.vm_manager.ProxmoxClient')
@mock.patch('homelab.vm_manager.Config.get_nodes')
@mock.patch('homelab.vm_manager.Config.get_network_ifaces_for')
@mock.patch('time.sleep')
def test_create_or_update_vm_timeout(
    mock_sleep, mock_get_ifaces, mock_get_nodes, mock_client_class,
    mock_calc_resources, mock_vm_exists, mock_get_vmid,
    mock_import_disk, mock_resize_disk, mock_env
):
    """Test create_or_update_vm handles VM start timeout."""
    # Setup mocks
    mock_get_nodes.return_value = [{"name": "test-node", "img_storage": "local-zfs", "cpu_ratio": 0.5, "memory_ratio": 0.5}]
    mock_get_ifaces.return_value = ["vmbr0"]
    mock_vm_exists.return_value = None  # No existing VM
    mock_get_vmid.return_value = 108
    mock_calc_resources.return_value = (4, 8 * 1024**3)  # 4 CPUs, 8GB RAM

    # Setup client mock
    mock_client = mock.MagicMock()
    mock_proxmox = mock.MagicMock()
    mock_client.proxmox = mock_proxmox
    mock_client.get_node_status.return_value = {"cpuinfo": {"cpus": 8}, "memory": {"total": 16 * 1024**3}}
    mock_client_class.return_value = mock_client

    # Mock VM never reaches running state (timeout scenario)
    mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.return_value = {"status": "starting"}

    # Mock time.time to trigger timeout
    with mock.patch('time.time') as mock_time:
        # First call (start time), then calls that exceed timeout
        mock_time.side_effect = [0, 100, 200, 300]  # Exceeds 180s timeout

        VMManager.create_or_update_vm()

    # Verify VM creation process was attempted
    mock_proxmox.nodes.return_value.qemu.create.assert_called_once()
    mock_proxmox.nodes.return_value.qemu.return_value.status.start.post.assert_called_once()


@mock.patch('time.sleep')
def test_delete_vm_when_exists_and_running(mock_sleep, mock_proxmox):
    """Should stop and delete VM when it exists and is running."""
    # VM exists and is running
    mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.side_effect = [
        {"status": "running"},  # First check
        {"status": "stopped"}   # After stop
    ]
    mock_proxmox.nodes.return_value.qemu.return_value.status.stop.post.return_value = None
    mock_proxmox.nodes.return_value.qemu.return_value.delete.return_value = None

    result = VMManager.delete_vm(mock_proxmox, "test-node", 108)

    assert result is True
    mock_proxmox.nodes.return_value.qemu.return_value.status.stop.post.assert_called_once()
    mock_proxmox.nodes.return_value.qemu.return_value.delete.assert_called_once()


@mock.patch('time.sleep')
def test_delete_vm_when_exists_and_stopped(mock_sleep, mock_proxmox):
    """Should delete VM when it exists and is already stopped."""
    # VM exists and is stopped
    mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.return_value = {"status": "stopped"}
    mock_proxmox.nodes.return_value.qemu.return_value.delete.return_value = None

    result = VMManager.delete_vm(mock_proxmox, "test-node", 108)

    assert result is True
    mock_proxmox.nodes.return_value.qemu.return_value.status.stop.post.assert_not_called()
    mock_proxmox.nodes.return_value.qemu.return_value.delete.assert_called_once()


def test_delete_vm_when_not_exists(mock_proxmox):
    """Should return False when VM doesn't exist."""
    mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.side_effect = Exception("VM not found")

    result = VMManager.delete_vm(mock_proxmox, "test-node", 108)

    assert result is False
    mock_proxmox.nodes.return_value.qemu.return_value.delete.assert_not_called()


@mock.patch('time.sleep')
def test_delete_vm_stop_timeout(mock_sleep, mock_proxmox):
    """Should still delete VM even if stop times out."""
    # VM is running and never stops (timeout scenario)
    mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.return_value = {"status": "running"}
    mock_proxmox.nodes.return_value.qemu.return_value.status.stop.post.return_value = None
    mock_proxmox.nodes.return_value.qemu.return_value.delete.return_value = None

    # Mock time.time to trigger timeout
    with mock.patch('time.time') as mock_time:
        # First call (start time), then calls that exceed 30s timeout
        mock_time.side_effect = [0, 10, 20, 31]

        result = VMManager.delete_vm(mock_proxmox, "test-node", 108)

    assert result is True
    mock_proxmox.nodes.return_value.qemu.return_value.status.stop.post.assert_called_once()
    mock_proxmox.nodes.return_value.qemu.return_value.delete.assert_called_once()
