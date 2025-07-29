"""Tests for main module."""

from unittest import mock

import pytest

from homelab.main import main


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