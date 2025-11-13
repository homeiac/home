#!/usr/bin/env python3
"""
Unit tests for PBS Storage Manager.

Tests cover:
- DNS resolution and validation
- PBS connectivity checks
- Storage reconciliation logic
- Configuration loading and validation
"""

import socket
import ssl
from pathlib import Path
from typing import Any, Dict
from unittest import mock

import pytest
import yaml

from homelab.pbs_storage_manager import (
    PBSStorageConfig,
    PBSStorageManager,
)


# ===== Fixtures =====

@pytest.fixture
def mock_proxmox() -> Any:
    """Mock Proxmox API client."""
    return mock.MagicMock()


@pytest.fixture
def pbs_manager(mock_proxmox: Any) -> PBSStorageManager:
    """Create PBS storage manager with mocked Proxmox client."""
    return PBSStorageManager(mock_proxmox)


@pytest.fixture
def sample_config_data() -> Dict[str, Any]:
    """Sample PBS storage configuration data."""
    return {
        "name": "homelab-backup",
        "enabled": True,
        "server": "proxmox-backup-server.maas",
        "datastore": "homelab-backup",
        "content": ["backup"],
        "username": "root@pam",
        "fingerprint": "54:52:3A:D2:43:F0:80:66:E3:D0:BB:D6:0B:28:50:9F:C6:1C:73:BD:45:EA:D0:38:BC:25:54:EE:A4:D5:D1:54",
        "prune_backups": {"keep_daily": 7, "keep_weekly": 4, "keep_monthly": 3},
        "description": "Primary PBS storage",
    }


@pytest.fixture
def sample_config(sample_config_data: Dict[str, Any]) -> PBSStorageConfig:
    """Create sample PBS storage config object."""
    return PBSStorageConfig(sample_config_data)


@pytest.fixture
def temp_config_file(tmp_path: Path, sample_config_data: Dict[str, Any]) -> Path:
    """Create temporary config file for testing."""
    config_file = tmp_path / "pbs-storage.yaml"
    config_data = {"pbs_storages": [sample_config_data]}

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    return config_file


# ===== PBSStorageConfig Tests =====

def test_pbs_storage_config_initialization(sample_config_data: Dict[str, Any]) -> None:
    """Test PBS storage config initialization."""
    config = PBSStorageConfig(sample_config_data)

    assert config.name == "homelab-backup"
    assert config.enabled is True
    assert config.server == "proxmox-backup-server.maas"
    assert config.datastore == "homelab-backup"
    assert config.content == ["backup"]
    assert config.username == "root@pam"
    assert config.prune_backups == {"keep_daily": 7, "keep_weekly": 4, "keep_monthly": 3}


def test_pbs_storage_config_defaults() -> None:
    """Test PBS storage config with minimal data (defaults)."""
    minimal_data = {
        "name": "test-storage",
        "server": "pbs.example.com",
        "datastore": "test-datastore",
        "fingerprint": "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99",
    }

    config = PBSStorageConfig(minimal_data)

    assert config.enabled is True  # Default
    assert config.content == ["backup"]  # Default
    assert config.username == "root@pam"  # Default
    assert config.prune_backups == {}  # Default
    assert config.description == ""  # Default


def test_pbs_storage_config_to_proxmox_params(sample_config: PBSStorageConfig) -> None:
    """Test conversion to Proxmox API parameters."""
    params = sample_config.to_proxmox_params()

    assert params["type"] == "pbs"
    assert params["server"] == "proxmox-backup-server.maas"
    assert params["datastore"] == "homelab-backup"
    assert params["content"] == "backup"
    assert params["username"] == "root@pam"
    assert params["fingerprint"] == sample_config.fingerprint
    assert "prune-backups" in params
    assert "keep-daily=7" in params["prune-backups"]
    assert "keep-weekly=4" in params["prune-backups"]
    assert "keep-monthly=3" in params["prune-backups"]
    assert params["comment"] == "Primary PBS storage"


# ===== DNS Resolution Tests =====

@mock.patch("socket.gethostbyname")
def test_resolve_hostname_success(
    mock_gethostbyname: mock.MagicMock,
    pbs_manager: PBSStorageManager
) -> None:
    """Test successful hostname resolution."""
    mock_gethostbyname.return_value = "192.168.4.211"

    ip = pbs_manager.resolve_hostname("proxmox-backup-server.maas")

    assert ip == "192.168.4.211"
    mock_gethostbyname.assert_called_once_with("proxmox-backup-server.maas")


@mock.patch("socket.gethostbyname")
def test_resolve_hostname_failure(
    mock_gethostbyname: mock.MagicMock,
    pbs_manager: PBSStorageManager
) -> None:
    """Test failed hostname resolution."""
    mock_gethostbyname.side_effect = socket.gaierror("Name or service not known")

    ip = pbs_manager.resolve_hostname("nonexistent.maas")

    assert ip is None


# ===== PBS Connectivity Tests =====

@mock.patch("socket.gethostbyname")
@mock.patch("socket.create_connection")
@mock.patch("ssl.SSLContext.wrap_socket")
def test_check_pbs_connectivity_success(
    mock_wrap_socket: mock.MagicMock,
    mock_create_connection: mock.MagicMock,
    mock_gethostbyname: mock.MagicMock,
    pbs_manager: PBSStorageManager
) -> None:
    """Test successful PBS connectivity check."""
    mock_gethostbyname.return_value = "192.168.4.211"
    mock_socket = mock.MagicMock()
    mock_create_connection.return_value = mock_socket
    mock_ssl_socket = mock.MagicMock()
    mock_wrap_socket.return_value.__enter__.return_value = mock_ssl_socket

    result = pbs_manager.check_pbs_connectivity("proxmox-backup-server.maas")

    assert result["reachable"] is True
    assert result["dns_resolved"] is True
    assert result["ip"] == "192.168.4.211"
    assert result["port_open"] is True
    assert result["ssl_valid"] is True
    assert result["error"] is None


@mock.patch("socket.gethostbyname")
def test_check_pbs_connectivity_dns_failure(
    mock_gethostbyname: mock.MagicMock,
    pbs_manager: PBSStorageManager
) -> None:
    """Test PBS connectivity check with DNS failure."""
    mock_gethostbyname.side_effect = socket.gaierror("Name or service not known")

    result = pbs_manager.check_pbs_connectivity("nonexistent.maas")

    assert result["reachable"] is False
    assert result["dns_resolved"] is False
    assert result["ip"] is None
    assert result["port_open"] is False
    assert result["ssl_valid"] is False
    assert "DNS resolution failed" in result["error"]


@mock.patch("socket.gethostbyname")
@mock.patch("socket.create_connection")
def test_check_pbs_connectivity_port_closed(
    mock_create_connection: mock.MagicMock,
    mock_gethostbyname: mock.MagicMock,
    pbs_manager: PBSStorageManager
) -> None:
    """Test PBS connectivity check with port closed."""
    mock_gethostbyname.return_value = "192.168.4.211"
    mock_create_connection.side_effect = ConnectionRefusedError("Connection refused")

    result = pbs_manager.check_pbs_connectivity("proxmox-backup-server.maas")

    assert result["reachable"] is False
    assert result["dns_resolved"] is True
    assert result["ip"] == "192.168.4.211"
    assert result["port_open"] is False
    assert result["ssl_valid"] is False
    assert "not reachable" in result["error"]


# ===== Storage Validation Tests =====

@mock.patch.object(PBSStorageManager, "check_pbs_connectivity")
def test_validate_storage_config_success(
    mock_check_connectivity: mock.MagicMock,
    pbs_manager: PBSStorageManager,
    sample_config: PBSStorageConfig
) -> None:
    """Test successful storage configuration validation."""
    mock_check_connectivity.return_value = {
        "reachable": True,
        "dns_resolved": True,
        "ip": "192.168.4.211",
        "port_open": True,
        "ssl_valid": True,
        "error": None,
    }

    result = pbs_manager.validate_storage_config(sample_config)

    assert result["valid"] is True
    assert len(result["errors"]) == 0
    assert len(result["warnings"]) == 0


@mock.patch.object(PBSStorageManager, "check_pbs_connectivity")
def test_validate_storage_config_dns_failure(
    mock_check_connectivity: mock.MagicMock,
    pbs_manager: PBSStorageManager,
    sample_config: PBSStorageConfig
) -> None:
    """Test storage validation with DNS failure."""
    mock_check_connectivity.return_value = {
        "reachable": False,
        "dns_resolved": False,
        "ip": None,
        "port_open": False,
        "ssl_valid": False,
        "error": "DNS resolution failed",
    }

    result = pbs_manager.validate_storage_config(sample_config)

    assert result["valid"] is False
    assert any("DNS resolution failed" in err for err in result["errors"])


@mock.patch.object(PBSStorageManager, "check_pbs_connectivity")
def test_validate_storage_config_invalid_fingerprint(
    mock_check_connectivity: mock.MagicMock,
    pbs_manager: PBSStorageManager,
    sample_config_data: Dict[str, Any]
) -> None:
    """Test storage validation with invalid fingerprint."""
    mock_check_connectivity.return_value = {
        "reachable": True,
        "dns_resolved": True,
        "ip": "192.168.4.211",
        "port_open": True,
        "ssl_valid": True,
        "error": None,
    }

    # Invalid fingerprint
    sample_config_data["fingerprint"] = "invalid"
    config = PBSStorageConfig(sample_config_data)

    result = pbs_manager.validate_storage_config(config)

    assert result["valid"] is False
    assert any("Fingerprint" in err for err in result["errors"])


# ===== Storage Management Tests =====

def test_get_storage_exists(
    mock_proxmox: Any,
    pbs_manager: PBSStorageManager
) -> None:
    """Test getting existing storage."""
    mock_storage_data = {"storage": "homelab-backup", "type": "pbs"}
    mock_proxmox.storage.return_value.get.return_value = mock_storage_data

    result = pbs_manager.get_storage("homelab-backup")

    assert result == mock_storage_data


def test_get_storage_not_exists(
    mock_proxmox: Any,
    pbs_manager: PBSStorageManager
) -> None:
    """Test getting non-existent storage."""
    mock_proxmox.storage.return_value.get.side_effect = Exception("Not found")

    result = pbs_manager.get_storage("nonexistent")

    assert result is None


def test_storage_exists(
    mock_proxmox: Any,
    pbs_manager: PBSStorageManager
) -> None:
    """Test checking if storage exists."""
    mock_proxmox.storage.return_value.get.return_value = {"storage": "test"}

    assert pbs_manager.storage_exists("test") is True


def test_create_storage(
    mock_proxmox: Any,
    pbs_manager: PBSStorageManager,
    sample_config: PBSStorageConfig
) -> None:
    """Test creating PBS storage."""
    result = pbs_manager.create_storage(sample_config)

    assert result["action"] == "created"
    assert result["name"] == "homelab-backup"
    mock_proxmox.storage.create.assert_called_once()


def test_disable_storage(
    mock_proxmox: Any,
    pbs_manager: PBSStorageManager
) -> None:
    """Test disabling PBS storage."""
    mock_proxmox.storage.return_value.get.return_value = {"disable": 0}

    result = pbs_manager.disable_storage("test-storage")

    assert result["action"] == "disabled"
    mock_proxmox.storage.return_value.put.assert_called_with(disable=1)


def test_disable_storage_already_disabled(
    mock_proxmox: Any,
    pbs_manager: PBSStorageManager
) -> None:
    """Test disabling already disabled storage."""
    mock_proxmox.storage.return_value.get.return_value = {"disable": 1}

    result = pbs_manager.disable_storage("test-storage")

    assert result["action"] == "no_change"
    mock_proxmox.storage.return_value.put.assert_not_called()


def test_enable_storage(
    mock_proxmox: Any,
    pbs_manager: PBSStorageManager
) -> None:
    """Test enabling PBS storage."""
    mock_proxmox.storage.return_value.get.return_value = {"disable": 1}

    result = pbs_manager.enable_storage("test-storage")

    assert result["action"] == "enabled"
    mock_proxmox.storage.return_value.put.assert_called_with(disable=0)


# ===== Configuration Loading Tests =====

def test_load_config_from_file(
    pbs_manager: PBSStorageManager,
    temp_config_file: Path
) -> None:
    """Test loading configuration from YAML file."""
    configs = pbs_manager.load_config(str(temp_config_file))

    assert len(configs) == 1
    assert configs[0].name == "homelab-backup"
    assert configs[0].server == "proxmox-backup-server.maas"


def test_load_config_file_not_found(
    pbs_manager: PBSStorageManager
) -> None:
    """Test loading config from non-existent file."""
    with pytest.raises(FileNotFoundError):
        pbs_manager.load_config("/nonexistent/config.yaml")


def test_load_config_missing_key(
    pbs_manager: PBSStorageManager,
    tmp_path: Path
) -> None:
    """Test loading config without pbs_storages key."""
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text("other_key: value")

    with pytest.raises(ValueError, match="missing 'pbs_storages' key"):
        pbs_manager.load_config(str(config_file))


# ===== Reconciliation Tests =====

@mock.patch.object(PBSStorageManager, "validate_storage_config")
@mock.patch.object(PBSStorageManager, "get_storage")
@mock.patch.object(PBSStorageManager, "create_storage")
def test_reconcile_storage_create(
    mock_create: mock.MagicMock,
    mock_get: mock.MagicMock,
    mock_validate: mock.MagicMock,
    pbs_manager: PBSStorageManager,
    sample_config: PBSStorageConfig
) -> None:
    """Test reconciliation creates missing storage."""
    mock_validate.return_value = {"valid": True, "checks": {}, "warnings": [], "errors": []}
    mock_get.return_value = None  # Storage doesn't exist
    mock_create.return_value = {"action": "created", "name": "homelab-backup"}

    result = pbs_manager.reconcile_storage(sample_config)

    assert result["action"] == "created"
    mock_create.assert_called_once()


@mock.patch.object(PBSStorageManager, "validate_storage_config")
def test_reconcile_storage_validation_failure(
    mock_validate: mock.MagicMock,
    pbs_manager: PBSStorageManager,
    sample_config: PBSStorageConfig
) -> None:
    """Test reconciliation fails on validation errors."""
    mock_validate.return_value = {
        "valid": False,
        "checks": {},
        "warnings": [],
        "errors": ["DNS resolution failed"]
    }

    result = pbs_manager.reconcile_storage(sample_config)

    assert result["action"] == "validation_failed"


@mock.patch.object(PBSStorageManager, "get_storage")
@mock.patch.object(PBSStorageManager, "disable_storage")
def test_reconcile_storage_disable(
    mock_disable: mock.MagicMock,
    mock_get: mock.MagicMock,
    pbs_manager: PBSStorageManager,
    sample_config: PBSStorageConfig
) -> None:
    """Test reconciliation disables storage when enabled=false."""
    sample_config.enabled = False
    mock_get.return_value = {"storage": "homelab-backup", "disable": 0}
    mock_disable.return_value = {"action": "disabled", "name": "homelab-backup"}

    result = pbs_manager.reconcile_storage(sample_config, skip_validation=True)

    assert result["action"] == "disabled"
    mock_disable.assert_called_once()


# ===== Integration Tests =====

def test_reconcile_from_file(
    mock_proxmox: Any,
    pbs_manager: PBSStorageManager,
    temp_config_file: Path
) -> None:
    """Test full reconciliation from config file."""
    mock_proxmox.storage.return_value.get.side_effect = Exception("Not found")

    with mock.patch.object(PBSStorageManager, "validate_storage_config") as mock_validate:
        mock_validate.return_value = {"valid": True, "checks": {}, "warnings": [], "errors": []}

        results = pbs_manager.reconcile_from_file(str(temp_config_file))

        assert len(results) == 1
        assert results[0]["action"] == "created"
