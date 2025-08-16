"""Comprehensive tests for Coral TPU LXC configuration management."""

import pytest
from pathlib import Path
from unittest import mock
import subprocess

from homelab.coral_config import LXCConfigManager
from homelab.coral_models import ContainerStatus, ConfigurationError


class TestLXCConfigManager:
    """Test cases for LXCConfigManager class."""

    @pytest.fixture
    def config_manager(self, tmp_path):
        """Create config manager with test paths."""
        config_path = tmp_path / "113.conf"
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        return LXCConfigManager("113", config_path, backup_dir)

    def test_parse_existing_config(self, config_manager, lxc_config_correct):
        """Test parsing existing LXC configuration."""
        config_manager.config_path.write_text(lxc_config_correct)
        
        lxc_config = config_manager.get_current_config()
        
        assert lxc_config.container_id == "113"
        assert lxc_config.current_dev0 == "/dev/bus/usb/003/004"
        assert lxc_config.has_usb_permissions is True

    def test_parse_config_missing_dev0(self, config_manager, lxc_config_missing_dev0):
        """Test parsing config missing dev0."""
        config_manager.config_path.write_text(lxc_config_missing_dev0)
        
        lxc_config = config_manager.get_current_config()
        
        assert lxc_config.current_dev0 is None
        assert lxc_config.has_usb_permissions is True

    def test_parse_config_missing_usb_perms(self, config_manager, lxc_config_missing_usb_perms):
        """Test parsing config missing USB permissions."""
        config_manager.config_path.write_text(lxc_config_missing_usb_perms)
        
        lxc_config = config_manager.get_current_config()
        
        assert lxc_config.current_dev0 == "/dev/bus/usb/003/004"
        assert lxc_config.has_usb_permissions is False

    def test_get_container_status_running(self, config_manager, pct_status_running):
        """Test getting running container status."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = pct_status_running
            mock_run.return_value.returncode = 0
            
            status = config_manager.get_container_status()
            
            assert status == ContainerStatus.RUNNING

    def test_get_container_status_stopped(self, config_manager, pct_status_stopped):
        """Test getting stopped container status."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = pct_status_stopped
            mock_run.return_value.returncode = 0
            
            status = config_manager.get_container_status()
            
            assert status == ContainerStatus.STOPPED

    def test_get_container_status_error(self, config_manager, pct_status_error):
        """Test getting error container status."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = pct_status_error
            mock_run.return_value.returncode = 0
            
            status = config_manager.get_container_status()
            
            assert status == ContainerStatus.ERROR

    def test_get_container_status_command_failure(self, config_manager):
        """Test container status command failure."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, 'pct')
            
            with pytest.raises(ConfigurationError, match="Failed to get container status"):
                config_manager.get_container_status()

    def test_update_config_new_device(self, config_manager, lxc_config_missing_dev0):
        """Test updating config with new device."""
        config_manager.config_path.write_text(lxc_config_missing_dev0)
        
        result = config_manager.update_config("/dev/bus/usb/003/004", dry_run=False)
        
        assert result is True
        updated_content = config_manager.config_path.read_text()
        assert "dev0: /dev/bus/usb/003/004" in updated_content
        assert "lxc.cgroup2.devices.allow: c 189:* rwm" in updated_content

    def test_update_config_pmxcfs_direct_write(self, config_manager, lxc_config_wrong_device):
        """Test updating config on pmxcfs filesystem uses direct write."""
        # Set up config path to look like pmxcfs
        pmxcfs_path = Path("/etc/pve/lxc/113.conf")
        config_manager.config_path = pmxcfs_path
        
        # Mock the file operations
        with mock.patch.object(Path, 'exists', return_value=True), \
             mock.patch.object(Path, 'read_text', return_value=lxc_config_wrong_device), \
             mock.patch.object(Path, 'write_text') as mock_write:
            
            result = config_manager.update_config("/dev/bus/usb/003/003", dry_run=False)
            
            assert result is True
            # Verify direct write was called (not atomic move)
            mock_write.assert_called_once()
            written_content = mock_write.call_args[0][0]
            assert "dev0: /dev/bus/usb/003/003" in written_content

    def test_update_config_regular_filesystem_atomic(self, config_manager, lxc_config_wrong_device, tmp_path):
        """Test updating config on regular filesystem uses atomic replacement."""
        # Regular path (not under /etc/pve/)
        config_manager.config_path.write_text(lxc_config_wrong_device)
        
        with mock.patch('shutil.move') as mock_move:
            result = config_manager.update_config("/dev/bus/usb/003/003", dry_run=False)
            
            assert result is True
            # Verify atomic move was called
            mock_move.assert_called_once()

    def test_update_config_pmxcfs_write_failure(self, config_manager):
        """Test handling write failure on pmxcfs."""
        # Set up config path to look like pmxcfs
        pmxcfs_path = Path("/etc/pve/lxc/113.conf")
        config_manager.config_path = pmxcfs_path
        
        with mock.patch.object(Path, 'exists', return_value=True), \
             mock.patch.object(Path, 'read_text', return_value="dev0: /dev/bus/usb/003/004\n"), \
             mock.patch.object(Path, 'write_text', side_effect=PermissionError("Operation not permitted")):
            
            with pytest.raises(ConfigurationError, match="Failed to update config"):
                config_manager.update_config("/dev/bus/usb/003/003", dry_run=False)

    def test_update_config_replace_device(self, config_manager, lxc_config_wrong_device):
        """Test updating config with replacement device."""
        config_manager.config_path.write_text(lxc_config_wrong_device)
        
        result = config_manager.update_config("/dev/bus/usb/003/004", dry_run=False)
        
        assert result is True
        updated_content = config_manager.config_path.read_text()
        assert "dev0: /dev/bus/usb/003/004" in updated_content
        assert "dev0: /dev/bus/usb/003/005" not in updated_content

    def test_update_config_dry_run(self, config_manager, lxc_config_missing_dev0):
        """Test config update in dry run mode."""
        original_content = lxc_config_missing_dev0
        config_manager.config_path.write_text(original_content)
        
        result = config_manager.update_config("/dev/bus/usb/003/004", dry_run=True)
        
        assert result is True
        # Content should not change in dry run
        assert config_manager.config_path.read_text() == original_content

    def test_update_config_file_not_found(self, config_manager):
        """Test config update when file doesn't exist."""
        # Don't create the config file
        
        with pytest.raises(ConfigurationError, match="Config file does not exist"):
            config_manager.update_config("/dev/bus/usb/003/004", dry_run=False)

    def test_create_backup(self, config_manager, lxc_config_correct):
        """Test creating configuration backup."""
        config_manager.config_path.write_text(lxc_config_correct)
        
        backup_path = config_manager._create_backup()
        
        assert backup_path.exists()
        assert backup_path.read_text() == lxc_config_correct
        assert backup_path.name.startswith("lxc_113_")
        assert backup_path.name.endswith(".conf")

    def test_stop_container_success(self, config_manager):
        """Test successful container stop."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            
            result = config_manager.stop_container(dry_run=False)
            
            assert result is True
            mock_run.assert_called_once_with(
                ["pct", "stop", "113"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )

    def test_stop_container_dry_run(self, config_manager):
        """Test container stop in dry run mode."""
        result = config_manager.stop_container(dry_run=True)
        
        assert result is True

    def test_stop_container_failure(self, config_manager):
        """Test container stop failure."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, 'pct')
            
            result = config_manager.stop_container(dry_run=False)
            
            assert result is False

    def test_start_container_success(self, config_manager):
        """Test successful container start."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            
            result = config_manager.start_container(dry_run=False)
            
            assert result is True
            mock_run.assert_called_once_with(
                ["pct", "start", "113"],
                capture_output=True,
                text=True,
                check=True,
                timeout=60
            )

    def test_start_container_dry_run(self, config_manager):
        """Test container start in dry run mode."""
        result = config_manager.start_container(dry_run=True)
        
        assert result is True

    def test_start_container_failure(self, config_manager):
        """Test container start failure."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, 'pct')
            
            result = config_manager.start_container(dry_run=False)
            
            assert result is False

    def test_verify_coral_access_success(self, config_manager):
        """Test successful Coral access verification."""
        with mock.patch('subprocess.run') as mock_run:
            # Mock successful exec command
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "crw-rw-rw- 1 root plugdev 189, 259"
            
            result = config_manager.verify_coral_access("/dev/bus/usb/003/004")
            
            assert result is True

    def test_verify_coral_access_failure(self, config_manager):
        """Test failed Coral access verification."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, 'pct')
            
            result = config_manager.verify_coral_access("/dev/bus/usb/003/004")
            
            assert result is False

    def test_verify_coral_access_no_device_path(self, config_manager):
        """Test Coral access verification with no device path."""
        result = config_manager.verify_coral_access(None)
        
        assert result is False

    def test_wait_for_status_success(self, config_manager):
        """Test waiting for container status change."""
        with mock.patch('subprocess.run') as mock_run, \
             mock.patch('time.sleep') as mock_sleep:
            
            # First call returns running, second returns stopped
            mock_run.side_effect = [
                mock.MagicMock(stdout="status: running", returncode=0),
                mock.MagicMock(stdout="status: stopped", returncode=0)
            ]
            
            result = config_manager.wait_for_status(ContainerStatus.STOPPED, timeout=5)
            
            assert result is True
            assert mock_run.call_count == 2
            mock_sleep.assert_called_once_with(1)

    def test_wait_for_status_timeout(self, config_manager):
        """Test waiting for container status timeout."""
        with mock.patch('subprocess.run') as mock_run, \
             mock.patch('time.sleep') as mock_sleep, \
             mock.patch('time.time') as mock_time:
            
            # Mock time progression
            mock_time.side_effect = [0, 1, 2, 3, 4, 5, 6]  # Exceed 5 second timeout
            mock_run.return_value.stdout = "status: running"
            mock_run.return_value.returncode = 0
            
            result = config_manager.wait_for_status(ContainerStatus.STOPPED, timeout=5)
            
            assert result is False

    def test_rollback_config_success(self, config_manager, lxc_config_correct):
        """Test successful configuration rollback."""
        # Create backup
        backup_path = config_manager.backup_dir / "backup.conf"
        backup_path.write_text(lxc_config_correct)
        
        # Create different current config
        config_manager.config_path.write_text("corrupted config")
        
        result = config_manager.rollback_config(backup_path)
        
        assert result is True
        assert config_manager.config_path.read_text() == lxc_config_correct

    def test_rollback_config_backup_not_found(self, config_manager):
        """Test rollback when backup doesn't exist."""
        non_existent_backup = config_manager.backup_dir / "nonexistent.conf"
        
        result = config_manager.rollback_config(non_existent_backup)
        
        assert result is False

    def test_parse_container_status_edge_cases(self, config_manager):
        """Test parsing container status edge cases."""
        # Test with unknown status
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = "status: unknown"
            mock_run.return_value.returncode = 0
            
            status = config_manager.get_container_status()
            
            assert status == ContainerStatus.ERROR

    def test_config_path_property(self, config_manager):
        """Test config path property access."""
        assert isinstance(config_manager.config_path, Path)
        assert config_manager.config_path.name == "113.conf"

    def test_backup_dir_property(self, config_manager):
        """Test backup dir property access."""
        assert isinstance(config_manager.backup_dir, Path)
        assert config_manager.backup_dir.name == "backups"