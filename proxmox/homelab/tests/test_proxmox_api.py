"""Tests for proxmox_api module."""

from unittest import mock

import pytest

from homelab.proxmox_api import ProxmoxClient


@mock.patch('homelab.proxmox_api.Config')
def test_proxmox_client_init(mock_config, temp_ssh_key):
    """Test ProxmoxClient initialization with API token parsing."""
    mock_config.API_TOKEN = "testuser!testtoken=secretvalue"

    with mock.patch('homelab.proxmox_api.ProxmoxAPI'):
        client = ProxmoxClient("test-host")

    assert client.host == "test-host.maas"
    assert client.user == "testuser"
    assert client.token_name == "testtoken"
    assert client.api_token == "secretvalue"


@mock.patch('homelab.proxmox_api.Config')
def test_proxmox_client_init_no_api_token(mock_config, temp_ssh_key):
    """Test ProxmoxClient initialization raises error when API_TOKEN is None."""
    mock_config.API_TOKEN = None
    
    with pytest.raises(ValueError, match="API_TOKEN environment variable is not set"):
        ProxmoxClient("test-host")


@mock.patch('homelab.proxmox_api.ProxmoxAPI')
@mock.patch('homelab.proxmox_api.Config')
def test_proxmox_client_api_creation(mock_config, mock_proxmox_api, temp_ssh_key):
    """Test that ProxmoxAPI is created with correct parameters."""
    mock_config.API_TOKEN = "testuser!testtoken=secretvalue"

    client = ProxmoxClient("test-host")

    mock_proxmox_api.assert_called_once_with(
        "test-host.maas",
        user="testuser",
        token_name="testtoken",
        token_value="secretvalue",
        verify_ssl=False
    )


def test_get_node_status(mock_proxmox, mock_env, temp_ssh_key):
    """Test get_node_status method."""
    mock_proxmox.nodes.return_value.status.get.return_value = {
        "cpuinfo": {"cpus": 4},
        "memory": {"total": 8 * 1024**3}
    }

    client = ProxmoxClient("test-host")
    client.proxmox = mock_proxmox

    status = client.get_node_status()

    assert status["cpuinfo"]["cpus"] == 4
    assert status["memory"]["total"] == 8 * 1024**3
    mock_proxmox.nodes.assert_called_with("test-host.maas")
    mock_proxmox.nodes.return_value.status.get.assert_called_once()


def test_get_storage_content(mock_proxmox, mock_env, temp_ssh_key):
    """Test get_storage_content method."""
    expected_content = [
        {"volid": "local:iso/test.iso", "format": "iso"},
        {"volid": "local:iso/another.iso", "format": "iso"}
    ]
    mock_proxmox.nodes.return_value.storage.return_value.content.get.return_value = expected_content

    client = ProxmoxClient("test-host")
    client.proxmox = mock_proxmox

    content = client.get_storage_content("local")

    assert content == expected_content
    mock_proxmox.nodes.assert_called_with("test-host.maas")
    mock_proxmox.nodes.return_value.storage.assert_called_with("local")
    mock_proxmox.nodes.return_value.storage.return_value.content.get.assert_called_once()


@mock.patch('homelab.proxmox_api.Config')
def test_iso_exists_true(mock_config, mock_proxmox, mock_env, temp_ssh_key):
    """Test iso_exists returns True when ISO exists."""
    mock_config.API_TOKEN = "testuser!testtoken=secretvalue"
    mock_config.ISO_NAME = "ubuntu-24.04.2-desktop-amd64.iso"
    storage_content = [
        {"volid": "local:iso/ubuntu-24.04.2-desktop-amd64.iso", "format": "iso"},
        {"volid": "local:iso/other.iso", "format": "iso"}
    ]
    mock_proxmox.nodes.return_value.storage.return_value.content.get.return_value = storage_content

    with mock.patch('homelab.proxmox_api.ProxmoxAPI'):
        client = ProxmoxClient("test-host")
        client.proxmox = mock_proxmox

        exists = client.iso_exists("local")

        assert exists is True


def test_iso_exists_false(mock_proxmox, mock_env, temp_ssh_key):
    """Test iso_exists returns False when ISO doesn't exist."""
    storage_content = [
        {"volid": "local:iso/other.iso", "format": "iso"}
    ]
    mock_proxmox.nodes.return_value.storage.return_value.content.get.return_value = storage_content
    
    client = ProxmoxClient("test-host")
    client.proxmox = mock_proxmox
    
    exists = client.iso_exists("local")
    
    assert exists is False


def test_iso_exists_exception_handling(mock_proxmox, mock_env, temp_ssh_key):
    """Test iso_exists handles exceptions gracefully."""
    mock_proxmox.nodes.return_value.storage.return_value.content.get.side_effect = Exception("API Error")
    
    client = ProxmoxClient("test-host")
    client.proxmox = mock_proxmox
    
    exists = client.iso_exists("local")
    
    assert exists is False


def test_upload_iso_skips_when_exists(mock_proxmox, mock_env, temp_ssh_key):
    """Test upload_iso skips upload when ISO already exists."""
    client = ProxmoxClient("test-host")
    client.proxmox = mock_proxmox
    
    # Mock iso_exists to return True
    with mock.patch.object(client, 'iso_exists', return_value=True):
        client.upload_iso("local", "/path/to/iso")
    
    # Verify upload was not called
    mock_proxmox.nodes.return_value.storage.return_value.upload.post.assert_not_called()


@mock.patch('builtins.open', mock.mock_open(read_data=b"iso content"))
def test_upload_iso_performs_upload(mock_proxmox, mock_env, temp_ssh_key):
    """Test upload_iso performs upload when ISO doesn't exist."""
    client = ProxmoxClient("test-host")
    client.proxmox = mock_proxmox

    # Mock iso_exists to return False
    with mock.patch.object(client, 'iso_exists', return_value=False):
        client.upload_iso("local", "/path/to/test.iso")

    # Verify upload was called
    mock_proxmox.nodes.return_value.storage.return_value.upload.post.assert_called_once()
    call_args = mock_proxmox.nodes.return_value.storage.return_value.upload.post.call_args
    assert call_args[1]["content"] == "iso"


@mock.patch('homelab.proxmox_api.Config')
def test_client_falls_back_to_cli_on_ssl_error(mock_config, temp_ssh_key):
    """When API fails with SSL error, should set cli_mode=True."""
    from proxmoxer.core import ResourceException

    mock_config.API_TOKEN = "root!test=abc123"

    with mock.patch('homelab.proxmox_api.ProxmoxAPI') as mock_api:
        # Simulate SSL error on API connection
        mock_api.side_effect = ResourceException("SSL routines::certificate verify failed", 500, "")

        client = ProxmoxClient("test-node", use_cli_fallback=True)

        assert client.cli_mode is True
        assert client.proxmox is None


@mock.patch('homelab.proxmox_api.Config')
def test_client_raises_on_ssl_error_when_fallback_disabled(mock_config, temp_ssh_key):
    """When fallback disabled, SSL errors should raise."""
    from proxmoxer.core import ResourceException

    mock_config.API_TOKEN = "root!test=abc123"

    with mock.patch('homelab.proxmox_api.ProxmoxAPI') as mock_api:
        mock_api.side_effect = ResourceException("SSL routines::certificate verify failed", 500, "")

        with pytest.raises(ResourceException):
            client = ProxmoxClient("test-node", use_cli_fallback=False)


@mock.patch('homelab.proxmox_api.Config')
@mock.patch('paramiko.SSHClient')
def test_get_node_status_uses_cli_when_in_cli_mode(mock_ssh, mock_config, temp_ssh_key, monkeypatch):
    """get_node_status should use SSH when cli_mode=True."""
    from proxmoxer.core import ResourceException

    mock_config.API_TOKEN = "root!test=abc123"
    monkeypatch.setenv("SSH_USER", "root")
    monkeypatch.setenv("SSH_KEY_PATH", "~/.ssh/id_rsa")

    with mock.patch('homelab.proxmox_api.ProxmoxAPI') as mock_api:
        mock_api.side_effect = ResourceException("SSL error", 500, "")

        # Setup SSH mock
        mock_client = mock.MagicMock()
        mock_ssh.return_value = mock_client
        stdout = mock.MagicMock()
        stderr = mock.MagicMock()
        stdout.read.return_value = b'{"cpu": 0.5, "memory": {"total": 32000000000}}'
        stderr.read.return_value = b''
        mock_client.exec_command.return_value = (None, stdout, stderr)

        client = ProxmoxClient("test-node", use_cli_fallback=True)
        status = client.get_node_status()

        assert "cpu" in status
        assert status["cpu"] == 0.5
        mock_client.exec_command.assert_called_once()
        # Verify the command contains pvesh
        call_args = mock_client.exec_command.call_args[0][0]
        assert "pvesh" in call_args
        assert "get" in call_args
        assert "/nodes/" in call_args