"""Tests for main module."""

from unittest import mock

import pytest

from homelab.main import main, join_vms_to_k3s


@mock.patch('homelab.main.VMManager')
@mock.patch('homelab.main.IsoManager')
def test_main_function_calls_all_managers(mock_iso_manager, mock_vm_manager):
    """Test main function calls all required manager methods."""
    main()

    mock_iso_manager.download_iso.assert_called_once()
    mock_iso_manager.upload_iso_to_nodes.assert_called_once()
    mock_vm_manager.create_or_update_vm.assert_called_once()


@mock.patch('homelab.main.VMManager')
@mock.patch('homelab.main.IsoManager')
def test_main_function_call_order(mock_iso_manager, mock_vm_manager):
    """Test main function calls methods in correct order."""
    call_order = []

    def track_download():
        call_order.append('download_iso')

    def track_upload():
        call_order.append('upload_iso_to_nodes')

    def track_vm_create():
        call_order.append('create_or_update_vm')

    mock_iso_manager.download_iso.side_effect = track_download
    mock_iso_manager.upload_iso_to_nodes.side_effect = track_upload
    mock_vm_manager.create_or_update_vm.side_effect = track_vm_create

    main()

    expected_order = ['download_iso', 'upload_iso_to_nodes', 'create_or_update_vm']
    assert call_order == expected_order


@mock.patch('homelab.main.K3sManager')
@mock.patch('homelab.main.Config')
@mock.patch('homelab.main.os.getenv')
def test_join_vms_to_k3s_success(mock_getenv, mock_config, mock_k3s_class, capsys):
    """Test join_vms_to_k3s successfully joins nodes to cluster."""
    # Setup environment
    mock_getenv.return_value = "192.168.4.212"

    # Setup config nodes
    mock_config.get_nodes.return_value = [
        {"name": "pve", "storage": "local-zfs"},
        {"name": "still-fawn", "storage": "local-2TB-zfs"},
    ]
    mock_config.VM_NAME_TEMPLATE = "k3s-vm-{node}"

    # Setup K3sManager instance
    mock_k3s = mock.MagicMock()
    mock_k3s_class.return_value = mock_k3s
    mock_k3s.get_cluster_token.return_value = "test-token-123"
    mock_k3s.node_in_cluster.return_value = False
    mock_k3s.install_k3s.return_value = True

    # Run function
    join_vms_to_k3s()

    # Verify token was retrieved
    mock_k3s.get_cluster_token.assert_called_once_with("192.168.4.212")

    # Verify both nodes were checked and joined
    assert mock_k3s.node_in_cluster.call_count == 2
    mock_k3s.node_in_cluster.assert_any_call("k3s-vm-pve")
    mock_k3s.node_in_cluster.assert_any_call("k3s-vm-still-fawn")

    assert mock_k3s.install_k3s.call_count == 2
    mock_k3s.install_k3s.assert_any_call("k3s-vm-pve", "test-token-123", "https://192.168.4.212:6443")
    mock_k3s.install_k3s.assert_any_call("k3s-vm-still-fawn", "test-token-123", "https://192.168.4.212:6443")

    # Verify output
    captured = capsys.readouterr()
    assert "Joining k3s-vm-pve to k3s cluster" in captured.out
    assert "k3s-vm-pve joined cluster" in captured.out


@mock.patch('homelab.main.K3sManager')
@mock.patch('homelab.main.Config')
@mock.patch('homelab.main.os.getenv')
def test_join_vms_to_k3s_skips_existing_nodes(mock_getenv, mock_config, mock_k3s_class, capsys):
    """Test join_vms_to_k3s skips nodes already in cluster."""
    # Setup environment
    mock_getenv.return_value = "192.168.4.212"

    # Setup config nodes
    mock_config.get_nodes.return_value = [{"name": "pve", "storage": "local-zfs"}]
    mock_config.VM_NAME_TEMPLATE = "k3s-vm-{node}"

    # Setup K3sManager - node already in cluster
    mock_k3s = mock.MagicMock()
    mock_k3s_class.return_value = mock_k3s
    mock_k3s.get_cluster_token.return_value = "test-token-123"
    mock_k3s.node_in_cluster.return_value = True

    # Run function
    join_vms_to_k3s()

    # Verify node was checked but not joined
    mock_k3s.node_in_cluster.assert_called_once_with("k3s-vm-pve")
    mock_k3s.install_k3s.assert_not_called()

    # Verify output
    captured = capsys.readouterr()
    assert "k3s-vm-pve already in cluster" in captured.out


@mock.patch('homelab.main.os.getenv')
def test_join_vms_to_k3s_skips_without_existing_node_ip(mock_getenv, capsys):
    """Test join_vms_to_k3s skips if K3S_EXISTING_NODE_IP not set."""
    # No K3S_EXISTING_NODE_IP
    mock_getenv.return_value = None

    # Run function
    join_vms_to_k3s()

    # Verify warning message
    captured = capsys.readouterr()
    assert "K3S_EXISTING_NODE_IP not set" in captured.out
    assert "skipping k3s join" in captured.out


@mock.patch('homelab.main.K3sManager')
@mock.patch('homelab.main.Config')
@mock.patch('homelab.main.os.getenv')
def test_join_vms_to_k3s_handles_token_error(mock_getenv, mock_config, mock_k3s_class, capsys):
    """Test join_vms_to_k3s handles token retrieval errors gracefully."""
    # Setup environment
    mock_getenv.return_value = "192.168.4.212"
    mock_config.get_nodes.return_value = [{"name": "pve", "storage": "local-zfs"}]

    # Setup K3sManager - token retrieval fails
    mock_k3s = mock.MagicMock()
    mock_k3s_class.return_value = mock_k3s
    mock_k3s.get_cluster_token.side_effect = RuntimeError("SSH failed")

    # Run function
    join_vms_to_k3s()

    # Verify graceful handling
    mock_k3s.node_in_cluster.assert_not_called()
    mock_k3s.install_k3s.assert_not_called()

    # Verify error message
    captured = capsys.readouterr()
    assert "Could not get k3s token" in captured.out


@mock.patch('homelab.main.K3sManager')
@mock.patch('homelab.main.Config')
@mock.patch('homelab.main.os.getenv')
def test_join_vms_to_k3s_continues_on_individual_node_failure(mock_getenv, mock_config, mock_k3s_class, capsys):
    """Test join_vms_to_k3s continues processing nodes after one fails."""
    # Setup environment
    mock_getenv.return_value = "192.168.4.212"

    # Setup config nodes
    mock_config.get_nodes.return_value = [
        {"name": "pve", "storage": "local-zfs"},
        {"name": "still-fawn", "storage": "local-2TB-zfs"},
    ]
    mock_config.VM_NAME_TEMPLATE = "k3s-vm-{node}"

    # Setup K3sManager - first install fails, second succeeds
    mock_k3s = mock.MagicMock()
    mock_k3s_class.return_value = mock_k3s
    mock_k3s.get_cluster_token.return_value = "test-token-123"
    mock_k3s.node_in_cluster.return_value = False
    mock_k3s.install_k3s.side_effect = [RuntimeError("Install failed"), True]

    # Run function
    join_vms_to_k3s()

    # Verify both installs were attempted
    assert mock_k3s.install_k3s.call_count == 2

    # Verify error and success messages
    captured = capsys.readouterr()
    assert "Failed to join k3s-vm-pve" in captured.out
    assert "k3s-vm-still-fawn joined cluster" in captured.out


@mock.patch('homelab.main.join_vms_to_k3s')
@mock.patch('homelab.main.VMManager')
@mock.patch('homelab.main.IsoManager')
def test_main_calls_join_vms_to_k3s(mock_iso, mock_vm, mock_join_k3s):
    """Test main function calls join_vms_to_k3s after VM provisioning."""
    main()

    # Verify k3s join was called
    mock_join_k3s.assert_called_once()


@mock.patch('homelab.main.join_vms_to_k3s')
@mock.patch('homelab.main.VMManager')
@mock.patch('homelab.main.IsoManager')
def test_main_calls_phases_in_correct_order(mock_iso, mock_vm, mock_join_k3s):
    """Test main function calls all phases in correct order."""
    call_order = []

    mock_iso.download_iso.side_effect = lambda: call_order.append('download_iso')
    mock_iso.upload_iso_to_nodes.side_effect = lambda: call_order.append('upload_iso')
    mock_vm.create_or_update_vm.side_effect = lambda: call_order.append('create_vm')
    mock_join_k3s.side_effect = lambda: call_order.append('join_k3s')

    main()

    expected_order = ['download_iso', 'upload_iso', 'create_vm', 'join_k3s']
    assert call_order == expected_order