"""Tests for iso_manager module."""

from unittest import mock
import os

import pytest

from homelab.iso_manager import IsoManager


@mock.patch('homelab.iso_manager.os.path.isfile')
@mock.patch('homelab.iso_manager.requests.get')
@mock.patch('homelab.iso_manager.Config')
def test_download_iso(mock_config, mock_get, mock_isfile, tmp_path):
    """Test download_iso method."""
    iso_path = tmp_path / "ubuntu-24.04.2-desktop-amd64.iso"
    mock_config.ISO_NAME = str(iso_path)
    mock_config.ISO_URL = "http://example.com/test.iso"
    mock_isfile.return_value = False
    
    # Mock response
    fake_resp = mock.Mock()
    fake_resp.iter_content.return_value = [b"iso content data"]
    mock_get.return_value = fake_resp
    
    IsoManager.download_iso()
    
    mock_get.assert_called_once_with("http://example.com/test.iso", stream=True)
    mock_isfile.assert_called_once_with(str(iso_path))
    assert iso_path.read_bytes() == b"iso content data"


@mock.patch('homelab.iso_manager.os.path.isfile')
@mock.patch('homelab.iso_manager.Config')
def test_download_iso_file_exists(mock_config, mock_isfile, tmp_path):
    """Test download_iso skips download when file exists."""
    iso_path = tmp_path / "ubuntu-24.04.2-desktop-amd64.iso"
    mock_config.ISO_NAME = str(iso_path)
    mock_isfile.return_value = True
    
    with mock.patch('homelab.iso_manager.requests.get') as mock_get:
        IsoManager.download_iso()
        mock_get.assert_not_called()


@mock.patch('homelab.iso_manager.ProxmoxClient')
@mock.patch('homelab.iso_manager.Config')
def test_upload_iso_to_nodes(mock_config, mock_client_class, mock_env):
    """Test upload_iso_to_nodes method."""
    # Setup config mock
    nodes = [
        {"name": "pve", "storage": "local"},
        {"name": "still-fawn", "storage": "local-2TB-zfs"}
    ]
    mock_config.get_nodes.return_value = nodes
    mock_config.ISO_NAME = "ubuntu-24.04.2-desktop-amd64.iso"
    
    # Setup client mock
    mock_client = mock.MagicMock()
    mock_client_class.return_value = mock_client
    
    IsoManager.upload_iso_to_nodes()
    
    # Verify client creation and upload calls
    assert mock_client_class.call_count == 2
    mock_client_class.assert_any_call("pve")
    mock_client_class.assert_any_call("still-fawn")
    
    assert mock_client.upload_iso.call_count == 2
    mock_client.upload_iso.assert_any_call("local", "ubuntu-24.04.2-desktop-amd64.iso")
    mock_client.upload_iso.assert_any_call("local-2TB-zfs", "ubuntu-24.04.2-desktop-amd64.iso")


@mock.patch('homelab.iso_manager.ProxmoxClient')
@mock.patch('homelab.iso_manager.Config')
def test_upload_iso_to_nodes_empty_nodes(mock_config, mock_client_class):
    """Test upload_iso_to_nodes with no nodes."""
    mock_config.get_nodes.return_value = []
    
    IsoManager.upload_iso_to_nodes()
    
    mock_client_class.assert_not_called()


@mock.patch('homelab.iso_manager.ProxmoxClient')
@mock.patch('homelab.iso_manager.Config')
def test_upload_iso_to_nodes_iso_already_exists(mock_config, mock_client_class):
    """Test upload_iso_to_nodes when ISO already exists on storage."""
    # Setup config mock
    nodes = [{"name": "pve", "storage": "local"}]
    mock_config.get_nodes.return_value = nodes
    mock_config.ISO_NAME = "ubuntu-24.04.2-desktop-amd64.iso"
    
    # Setup client mock - ISO already exists
    mock_client = mock.MagicMock()
    storage_content = [
        {"volid": "local:iso/ubuntu-24.04.2-desktop-amd64.iso", "format": "iso"}
    ]
    mock_client.get_storage_content.return_value = storage_content
    mock_client_class.return_value = mock_client
    
    IsoManager.upload_iso_to_nodes()
    
    # Verify client was created but upload was not called
    mock_client_class.assert_called_once_with("pve")
    mock_client.get_storage_content.assert_called_once_with("local")
    mock_client.upload_iso.assert_not_called()
