"""Tests for StorageManager module."""

import subprocess
from unittest import mock

import pytest

from homelab.storage_manager import StorageManager


@pytest.fixture
def mock_proxmox():
    """Mock Proxmox API client."""
    return mock.MagicMock()


@pytest.fixture
def storage_manager(mock_proxmox):
    """Create StorageManager instance."""
    return StorageManager(mock_proxmox, "pumped-piglet")


class TestStorageManager:
    """Tests for StorageManager class."""

    def test_init(self, storage_manager):
        """Test StorageManager initialization."""
        assert storage_manager.node == "pumped-piglet"
        assert storage_manager.proxmox is not None

    @mock.patch("subprocess.run")
    def test_pool_exists_true(self, mock_run, storage_manager):
        """Test pool_exists when pool exists."""
        mock_run.return_value = mock.Mock(returncode=0)

        result = storage_manager.pool_exists("local-2TB-zfs")

        assert result is True
        mock_run.assert_called_once()
        assert "zpool" in mock_run.call_args[0][0]
        assert "list" in mock_run.call_args[0][0]

    @mock.patch("subprocess.run")
    def test_pool_exists_false(self, mock_run, storage_manager):
        """Test pool_exists when pool doesn't exist."""
        mock_run.return_value = mock.Mock(returncode=1)

        result = storage_manager.pool_exists("nonexistent-pool")

        assert result is False

    @mock.patch("subprocess.run")
    def test_pool_importable_true(self, mock_run, storage_manager):
        """Test pool_importable when pool can be imported."""
        mock_run.return_value = mock.Mock(
            returncode=0, stdout="local-20TB-zfs  ONLINE"
        )

        result = storage_manager.pool_importable("local-20TB-zfs")

        assert result is True

    @mock.patch("subprocess.run")
    def test_pool_importable_false(self, mock_run, storage_manager):
        """Test pool_importable when pool cannot be imported."""
        mock_run.return_value = mock.Mock(returncode=0, stdout="other-pool  ONLINE")

        result = storage_manager.pool_importable("local-20TB-zfs")

        assert result is False

    @mock.patch("subprocess.run")
    def test_get_pool_status(self, mock_run, storage_manager):
        """Test get_pool_status."""
        # First call checks if pool exists
        # Second call gets pool status
        mock_run.side_effect = [
            mock.Mock(returncode=0),  # pool exists
            mock.Mock(
                returncode=0, stdout="local-2TB-zfs\t1.8T\t200G\t1.6T\tONLINE\n"
            ),
        ]

        result = storage_manager.get_pool_status("local-2TB-zfs")

        assert result is not None
        assert result["name"] == "local-2TB-zfs"
        assert result["size"] == "1.8T"
        assert result["health"] == "ONLINE"

    @mock.patch("subprocess.run")
    def test_create_or_import_pool_already_exists(self, mock_run, storage_manager):
        """Test create_or_import_pool when pool already exists."""
        # First call checks if pool exists (returns True)
        # Second call gets pool status
        mock_run.side_effect = [
            mock.Mock(returncode=0),  # pool exists
            mock.Mock(
                returncode=0, stdout="local-2TB-zfs\t2.0T\t0\t2.0T\tONLINE\n"
            ),
        ]

        result = storage_manager.create_or_import_pool(
            "local-2TB-zfs", "/dev/nvme1n1"
        )

        assert result["exists"] is True
        assert result["created"] is False
        assert result["imported"] is False

    @mock.patch("subprocess.run")
    def test_create_or_import_pool_import(self, mock_run, storage_manager):
        """Test create_or_import_pool importing existing pool."""
        # Mock call sequence:
        # 1. Check if exists (no)
        # 2. Check if importable (yes)
        # 3. Import pool
        # 4. Get status
        mock_run.side_effect = [
            mock.Mock(returncode=1),  # pool doesn't exist
            mock.Mock(returncode=0, stdout="local-20TB-zfs  ONLINE"),  # importable
            mock.Mock(returncode=0),  # import successful
            mock.Mock(returncode=0),  # exists check for status
            mock.Mock(
                returncode=0, stdout="local-20TB-zfs\t20T\t2T\t18T\tONLINE\n"
            ),
        ]

        result = storage_manager.create_or_import_pool(
            "local-20TB-zfs", "/dev/sda", import_if_exists=True
        )

        assert result["exists"] is True
        assert result["created"] is False
        assert result["imported"] is True

    @mock.patch("subprocess.run")
    def test_register_with_proxmox_already_registered(
        self, mock_run, storage_manager, mock_proxmox
    ):
        """Test register_with_proxmox when already registered."""
        # Mock Proxmox API to return existing storage
        mock_proxmox.storage.return_value.get.return_value = {"type": "zfspool"}

        result = storage_manager.register_with_proxmox(
            "local-2TB-zfs", "local-2TB-zfs"
        )

        assert result is False  # Already registered

    @mock.patch("subprocess.run")
    def test_register_with_proxmox_new(self, mock_run, storage_manager, mock_proxmox):
        """Test register_with_proxmox for new storage."""
        # Mock Proxmox API to raise exception (storage doesn't exist)
        mock_proxmox.storage.return_value.get.side_effect = Exception("Not found")

        result = storage_manager.register_with_proxmox(
            "local-2TB-zfs", "local-2TB-zfs"
        )

        assert result is True
        mock_proxmox.storage.create.assert_called_once()

    @mock.patch("subprocess.run")
    def test_create_dataset_already_exists(self, mock_run, storage_manager):
        """Test create_dataset when dataset already exists."""
        mock_run.return_value = mock.Mock(returncode=0)

        result = storage_manager.create_dataset("local-20TB-zfs", "prometheus-data")

        assert result is False  # Already exists

    @mock.patch("subprocess.run")
    def test_create_dataset_new(self, mock_run, storage_manager):
        """Test create_dataset for new dataset."""
        # First call checks if exists (no)
        # Second call creates dataset
        mock_run.side_effect = [
            mock.Mock(returncode=1),  # doesn't exist
            mock.Mock(returncode=0),  # created
        ]

        result = storage_manager.create_dataset("local-20TB-zfs", "new-dataset")

        assert result is True
