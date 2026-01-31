"""Tests for zfs_exporter_manager module."""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest
import yaml

from homelab.zfs_exporter_manager import (
    ZfsExporterManager,
    apply_from_config,
    get_status_from_config,
    get_zfs_exporter_hosts,
    load_cluster_config,
    print_status_table,
)


SAMPLE_CONFIG = {
    "nodes": [
        {"name": "still-fawn", "ip": "192.168.4.17", "enabled": True},
        {"name": "pumped-piglet", "ip": "192.168.4.175", "enabled": True},
        {"name": "chief-horse", "ip": "192.168.4.174", "enabled": True},
    ],
    "monitoring": {
        "zfs_exporter": {
            "enabled": True,
            "version": "2.3.11",
            "port": 9134,
            "binary_path": "/usr/local/bin/zfs_exporter",
            "service": "zfs-exporter",
            "hosts": ["still-fawn", "pumped-piglet", "chief-horse"],
        }
    },
}


@pytest.fixture
def config_file(tmp_path):
    """Create a temporary cluster.yaml with ZFS exporter config."""
    config_path = tmp_path / "cluster.yaml"
    config_path.write_text(yaml.dump(SAMPLE_CONFIG))
    return config_path


@pytest.fixture
def mock_ssh():
    """Mock SSH client and command execution."""
    with mock.patch("paramiko.SSHClient") as mock_ssh_class:
        ssh_client = mock.MagicMock()
        mock_ssh_class.return_value = ssh_client

        # Mock successful command execution by default
        stdout = mock.MagicMock()
        stderr = mock.MagicMock()
        stdout.read.return_value.decode.return_value = ""
        stdout.channel.recv_exit_status.return_value = 0
        stderr.read.return_value.decode.return_value = ""

        ssh_client.exec_command.return_value = (None, stdout, stderr)

        yield ssh_client


@pytest.fixture
def manager(config_file, mock_ssh):
    """Create ZfsExporterManager with mocked SSH."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        mgr = ZfsExporterManager("still-fawn", config_path=config_file)
        yield mgr
        mgr.cleanup()


def _mock_exec(ssh_client, responses):
    """Helper to set up sequential mock SSH responses.

    Each response is a tuple: (stdout_text, stderr_text, exit_code)
    """
    side_effects = []
    for out, err, code in responses:
        stdout = mock.MagicMock()
        stderr = mock.MagicMock()
        stdout.read.return_value.decode.return_value = out
        stdout.channel.recv_exit_status.return_value = code
        stderr.read.return_value.decode.return_value = err
        side_effects.append((None, stdout, stderr))
    ssh_client.exec_command.side_effect = side_effects


# --- Config loading tests ---


def test_load_cluster_config(config_file):
    """Test loading cluster config from YAML file."""
    config = load_cluster_config(config_file)
    assert config["monitoring"]["zfs_exporter"]["version"] == "2.3.11"


def test_load_cluster_config_missing():
    """Test loading non-existent config raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_cluster_config(Path("/nonexistent/cluster.yaml"))


def test_get_zfs_exporter_hosts():
    """Test extracting ZFS exporter hosts from config."""
    hosts = get_zfs_exporter_hosts(SAMPLE_CONFIG)
    assert hosts == ["still-fawn", "pumped-piglet", "chief-horse"]


def test_get_zfs_exporter_hosts_empty():
    """Test extracting hosts when config is empty."""
    hosts = get_zfs_exporter_hosts({"monitoring": {}})
    assert hosts == []


# --- Manager initialization tests ---


def test_manager_init(config_file):
    """Test ZfsExporterManager initialization."""
    mgr = ZfsExporterManager("still-fawn", config_path=config_file)
    assert mgr.hostname == "still-fawn"
    assert mgr.version == "2.3.11"
    assert mgr.port == 9134
    assert mgr.binary_path == "/usr/local/bin/zfs_exporter"
    assert mgr.service == "zfs-exporter"
    assert mgr.ip == "192.168.4.17"
    assert mgr.ssh_client is None


def test_manager_init_with_config():
    """Test initialization with pre-loaded config."""
    mgr = ZfsExporterManager("pumped-piglet", config=SAMPLE_CONFIG)
    assert mgr.hostname == "pumped-piglet"
    assert mgr.ip == "192.168.4.175"


def test_manager_defaults():
    """Test manager uses defaults when config section is missing."""
    config = {"nodes": [], "monitoring": {}}
    mgr = ZfsExporterManager("test-host", config=config)
    assert mgr.version == "2.3.11"
    assert mgr.port == 9134
    assert mgr.ip is None


# --- SSH connection tests ---


def test_get_ssh_client(manager, mock_ssh):
    """Test SSH client creation."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        client = manager._get_ssh_client()
        assert client is not None
        mock_ssh.connect.assert_called_once()


def test_get_ssh_client_cached(manager, mock_ssh):
    """Test SSH client is cached on subsequent calls."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        client1 = manager._get_ssh_client()
        client2 = manager._get_ssh_client()
        assert client1 is client2
        # connect should only be called once
        mock_ssh.connect.assert_called_once()


def test_execute_command(manager, mock_ssh):
    """Test command execution via SSH."""
    _mock_exec(mock_ssh, [("test output", "", 0)])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        stdout, stderr, exit_code = manager._execute_command("test command")
    assert stdout == "test output"
    assert stderr == ""
    assert exit_code == 0


# --- is_installed tests ---


def test_is_installed_true(manager, mock_ssh):
    """Test is_installed returns True when binary exists."""
    _mock_exec(mock_ssh, [("installed", "", 0)])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        assert manager.is_installed() is True


def test_is_installed_false(manager, mock_ssh):
    """Test is_installed returns False when binary missing."""
    _mock_exec(mock_ssh, [("", "", 1)])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        assert manager.is_installed() is False


# --- is_running tests ---


def test_is_running_true(manager, mock_ssh):
    """Test is_running returns True when service is active."""
    _mock_exec(mock_ssh, [("active", "", 0)])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        assert manager.is_running() is True


def test_is_running_false(manager, mock_ssh):
    """Test is_running returns False when service is inactive."""
    _mock_exec(mock_ssh, [("inactive", "", 3)])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        assert manager.is_running() is False


# --- get_version tests ---


def test_get_version(manager, mock_ssh):
    """Test get_version parses version string."""
    _mock_exec(mock_ssh, [("zfs_exporter version 2.3.11 (branch: HEAD)", "", 0)])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        assert manager.get_version() == "2.3.11"


def test_get_version_not_installed(manager, mock_ssh):
    """Test get_version returns None when not installed."""
    _mock_exec(mock_ssh, [("", "not found", 127)])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        assert manager.get_version() is None


# --- get_status tests ---


def test_get_status_running(manager, mock_ssh):
    """Test get_status for a running exporter."""
    _mock_exec(mock_ssh, [
        ("installed", "", 0),          # is_installed
        ("2.3.11", "", 0),             # get_version
        ("active", "", 0),             # is_running
        ("enabled", "", 0),            # is_enabled
        ("200", "", 0),                # curl metrics check
        ("rpool", "", 0),              # zpool list
        ('zfs_pool_health{pool="rpool"} 0', "", 0),  # curl pool health
    ])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        status = manager.get_status()
    assert status["hostname"] == "still-fawn"
    assert status["installed"] is True
    assert status["running"] is True
    assert status["metrics_available"] is True
    assert "rpool" in status["pools"]


def test_get_status_not_installed(manager, mock_ssh):
    """Test get_status when exporter is not installed."""
    _mock_exec(mock_ssh, [("", "", 1)])  # is_installed returns false
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        status = manager.get_status()
    assert status["installed"] is False
    assert status["running"] is False
    assert status["metrics_available"] is False


def test_get_status_ssh_error(manager, mock_ssh):
    """Test get_status handles SSH errors gracefully."""
    mock_ssh.exec_command.side_effect = Exception("Connection refused")
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        status = manager.get_status()
    assert "error" in status


# --- install tests ---


def test_install_success(manager, mock_ssh):
    """Test successful install."""
    _mock_exec(mock_ssh, [
        ("", "", 0),   # curl download
        ("", "", 0),   # tar extract
        ("", "", 0),   # mv + chmod
        ("", "", 0),   # cleanup
    ])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        result = manager.install()
    assert result["status"] == "installed"


def test_install_download_failure(manager, mock_ssh):
    """Test install fails on download error."""
    _mock_exec(mock_ssh, [("", "404 Not Found", 22)])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        result = manager.install()
    assert result["status"] == "failed"
    assert "Download failed" in result["error"]


def test_install_extract_failure(manager, mock_ssh):
    """Test install fails on extract error."""
    _mock_exec(mock_ssh, [
        ("", "", 0),                    # download OK
        ("", "not a gzip archive", 1),  # extract fails
    ])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        result = manager.install()
    assert result["status"] == "failed"
    assert "Extract failed" in result["error"]


# --- configure tests ---


def test_configure_success(manager, mock_ssh):
    """Test successful configure."""
    _mock_exec(mock_ssh, [
        ("", "", 0),  # write unit file
        ("", "", 0),  # daemon-reload
    ])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        result = manager.configure()
    assert result["status"] == "configured"


def test_configure_write_failure(manager, mock_ssh):
    """Test configure fails on write error."""
    _mock_exec(mock_ssh, [("", "Permission denied", 1)])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        result = manager.configure()
    assert result["status"] == "failed"


# --- enable_and_start tests ---


def test_enable_and_start_success(manager, mock_ssh):
    """Test successful enable and start."""
    _mock_exec(mock_ssh, [
        ("", "", 0),  # systemctl enable
        ("", "", 0),  # systemctl restart
    ])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        result = manager.enable_and_start()
    assert result["status"] == "started"


def test_enable_and_start_enable_failure(manager, mock_ssh):
    """Test enable_and_start fails on enable error."""
    _mock_exec(mock_ssh, [("", "Unit not found", 5)])
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        result = manager.enable_and_start()
    assert result["status"] == "failed"


# --- deploy tests ---


def test_deploy_fresh_install(manager, mock_ssh):
    """Test deploy with fresh install."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        with mock.patch.object(manager, "is_installed", return_value=False):
            with mock.patch.object(manager, "install", return_value={"status": "installed"}):
                with mock.patch.object(manager, "configure", return_value={"status": "configured"}):
                    with mock.patch.object(manager, "enable_and_start", return_value={"status": "started"}):
                        with mock.patch.object(manager, "get_status", return_value={
                            "running": True,
                            "metrics_available": True,
                            "version": "2.3.11",
                            "pools": ["rpool"],
                        }):
                            result = manager.deploy()

    assert result["status"] == "success"
    assert "installed" in result["actions"]
    assert "configured" in result["actions"]
    assert "enabled_and_started" in result["actions"]
    assert result["version"] == "2.3.11"
    assert result["pools"] == ["rpool"]


def test_deploy_already_installed(manager, mock_ssh):
    """Test deploy when already installed."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        with mock.patch.object(manager, "is_installed", return_value=True):
            with mock.patch.object(manager, "configure", return_value={"status": "configured"}):
                with mock.patch.object(manager, "enable_and_start", return_value={"status": "started"}):
                    with mock.patch.object(manager, "get_status", return_value={
                        "running": True,
                        "metrics_available": True,
                        "version": "2.3.11",
                        "pools": ["rpool"],
                    }):
                        result = manager.deploy()

    assert result["status"] == "success"
    assert "already_installed" in result["actions"]


def test_deploy_install_failure(manager, mock_ssh):
    """Test deploy fails when install fails."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        with mock.patch.object(manager, "is_installed", return_value=False):
            with mock.patch.object(manager, "install", return_value={
                "status": "failed", "error": "Download failed"
            }):
                result = manager.deploy()

    assert result["status"] == "failed"
    assert "Download failed" in result["error"]


def test_deploy_configure_failure(manager, mock_ssh):
    """Test deploy fails when configure fails."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        with mock.patch.object(manager, "is_installed", return_value=True):
            with mock.patch.object(manager, "configure", return_value={
                "status": "failed", "error": "Permission denied"
            }):
                result = manager.deploy()

    assert result["status"] == "failed"


def test_deploy_partial(manager, mock_ssh):
    """Test deploy with partial success (service started but no metrics)."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        with mock.patch.object(manager, "is_installed", return_value=True):
            with mock.patch.object(manager, "configure", return_value={"status": "configured"}):
                with mock.patch.object(manager, "enable_and_start", return_value={"status": "started"}):
                    with mock.patch.object(manager, "get_status", return_value={
                        "running": True,
                        "metrics_available": False,
                        "version": "2.3.11",
                        "pools": [],
                    }):
                        result = manager.deploy()

    assert result["status"] == "partial"
    assert "warning" in result


def test_deploy_exception(manager, mock_ssh):
    """Test deploy handles exceptions gracefully."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        with mock.patch.object(manager, "is_installed", side_effect=Exception("SSH failed")):
            result = manager.deploy()

    assert result["status"] == "failed"
    assert "SSH failed" in result["error"]


# --- Context manager tests ---


def test_context_manager(config_file, mock_ssh):
    """Test ZfsExporterManager as context manager."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        with ZfsExporterManager("still-fawn", config_path=config_file) as mgr:
            assert mgr.hostname == "still-fawn"
    # cleanup should close SSH client
    assert mgr.ssh_client is None


def test_cleanup(manager, mock_ssh):
    """Test cleanup closes SSH client."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        manager._get_ssh_client()
    manager.cleanup()
    mock_ssh.close.assert_called_once()
    assert manager.ssh_client is None


def test_cleanup_no_client(manager):
    """Test cleanup when no SSH client exists."""
    manager.cleanup()  # Should not raise


# --- Module-level function tests ---


def test_apply_from_config(config_file, mock_ssh):
    """Test apply_from_config deploys to all configured hosts."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        with mock.patch(
            "homelab.zfs_exporter_manager.ZfsExporterManager.deploy",
            return_value={"hostname": "test", "status": "success", "actions": []},
        ):
            results = apply_from_config(config_file)

    assert len(results) == 3
    assert all(r["status"] == "success" for r in results)


def test_apply_from_config_disabled(config_file):
    """Test apply_from_config skips when disabled."""
    config = SAMPLE_CONFIG.copy()
    config["monitoring"] = {"zfs_exporter": {"enabled": False}}
    disabled_path = config_file.parent / "disabled.yaml"
    disabled_path.write_text(yaml.dump(config))

    results = apply_from_config(disabled_path)
    assert len(results) == 1
    assert results[0]["status"] == "skipped"


def test_apply_from_config_no_hosts(config_file):
    """Test apply_from_config skips when no hosts configured."""
    config = SAMPLE_CONFIG.copy()
    config["monitoring"] = {"zfs_exporter": {"enabled": True, "hosts": []}}
    empty_path = config_file.parent / "empty.yaml"
    empty_path.write_text(yaml.dump(config))

    results = apply_from_config(empty_path)
    assert len(results) == 1
    assert results[0]["status"] == "skipped"


def test_apply_from_config_with_failure(config_file, mock_ssh):
    """Test apply_from_config handles per-host failures."""
    call_count = 0

    def deploy_side_effect(self):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise Exception("Connection refused")
        return {"hostname": self.hostname, "status": "success", "actions": []}

    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        with mock.patch(
            "homelab.zfs_exporter_manager.ZfsExporterManager.deploy",
            deploy_side_effect,
        ):
            results = apply_from_config(config_file)

    assert len(results) == 3
    assert results[0]["status"] == "success"
    assert results[1]["status"] == "failed"
    assert results[2]["status"] == "success"


def test_get_status_from_config(config_file, mock_ssh):
    """Test get_status_from_config queries all hosts."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        with mock.patch(
            "homelab.zfs_exporter_manager.ZfsExporterManager.get_status",
            return_value={
                "hostname": "test",
                "ip": "192.168.4.17",
                "installed": True,
                "running": True,
                "metrics_available": True,
                "pools": ["rpool"],
            },
        ):
            results = get_status_from_config(config_file)

    assert len(results) == 3


def test_get_status_from_config_with_error(config_file, mock_ssh):
    """Test get_status_from_config handles errors."""
    with mock.patch("socket.gethostbyname", side_effect=Exception("DNS failed")):
        results = get_status_from_config(config_file)

    assert len(results) == 3
    assert all("error" in r for r in results)


# --- print_status_table tests ---


def test_print_status_table_running(capsys):
    """Test status table output for running exporter."""
    results = [{
        "hostname": "still-fawn",
        "ip": "192.168.4.17",
        "installed": True,
        "running": True,
        "version": "2.3.11",
        "pools": ["rpool"],
    }]
    print_status_table(results)
    captured = capsys.readouterr()
    assert "still-fawn" in captured.out
    assert "OK" in captured.out
    assert "rpool" in captured.out


def test_print_status_table_stopped(capsys):
    """Test status table output for stopped exporter."""
    results = [{
        "hostname": "still-fawn",
        "ip": "192.168.4.17",
        "installed": True,
        "running": False,
        "version": "2.3.11",
    }]
    print_status_table(results)
    captured = capsys.readouterr()
    assert "STOPPED" in captured.out


def test_print_status_table_missing(capsys):
    """Test status table output for missing exporter."""
    results = [{
        "hostname": "still-fawn",
        "ip": "192.168.4.17",
        "installed": False,
        "running": False,
    }]
    print_status_table(results)
    captured = capsys.readouterr()
    assert "MISSING" in captured.out


def test_print_status_table_error(capsys):
    """Test status table output for error."""
    results = [{
        "hostname": "still-fawn",
        "ip": "192.168.4.17",
        "error": "Connection refused",
    }]
    print_status_table(results)
    captured = capsys.readouterr()
    assert "ERROR" in captured.out
    assert "Connection refused" in captured.out
