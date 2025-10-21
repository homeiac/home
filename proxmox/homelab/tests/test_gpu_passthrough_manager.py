"""Tests for GPUPassthroughManager module."""

import subprocess
from unittest import mock

import pytest

from homelab.gpu_passthrough_manager import GPUPassthroughManager


@pytest.fixture
def mock_proxmox():
    """Mock Proxmox API client."""
    return mock.MagicMock()


@pytest.fixture
def gpu_manager(mock_proxmox):
    """Create GPUPassthroughManager instance."""
    return GPUPassthroughManager(mock_proxmox, "pumped-piglet")


class TestGPUPassthroughManager:
    """Tests for GPUPassthroughManager class."""

    def test_init(self, gpu_manager):
        """Test GPUPassthroughManager initialization."""
        assert gpu_manager.node == "pumped-piglet"
        assert gpu_manager.proxmox is not None

    @mock.patch("subprocess.run")
    def test_detect_nvidia_gpu_found(self, mock_run, gpu_manager):
        """Test detect_nvidia_gpu when GPU is found."""
        mock_run.return_value = mock.Mock(
            returncode=0,
            stdout="b3:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA104 [GeForce RTX 3070] [10de:2484]\n",
        )

        result = gpu_manager.detect_nvidia_gpu()

        assert result is not None
        assert result["pci_address"] == "0000:b3:00.0"
        assert result["short_address"] == "b3:00.0"
        assert "RTX 3070" in result["description"]

    @mock.patch("subprocess.run")
    def test_detect_nvidia_gpu_not_found(self, mock_run, gpu_manager):
        """Test detect_nvidia_gpu when no GPU found."""
        mock_run.return_value = mock.Mock(
            returncode=0, stdout="00:02.0 VGA compatible controller: Intel Corporation\n"
        )

        result = gpu_manager.detect_nvidia_gpu()

        assert result is None

    @mock.patch("subprocess.run")
    def test_detect_nvidia_audio_found(self, mock_run, gpu_manager):
        """Test detect_nvidia_audio when audio device found."""
        mock_run.return_value = mock.Mock(
            returncode=0, stdout="b3:00.1 Audio device: NVIDIA Corporation\n"
        )

        result = gpu_manager.detect_nvidia_audio("b3:00.0")

        assert result == "0000:b3:00.1"

    @mock.patch("subprocess.run")
    def test_detect_nvidia_audio_not_found(self, mock_run, gpu_manager):
        """Test detect_nvidia_audio when no audio device found."""
        mock_run.return_value = mock.Mock(returncode=1, stdout="")

        result = gpu_manager.detect_nvidia_audio("b3:00.0")

        assert result is None

    @mock.patch("subprocess.run")
    def test_get_iommu_group(self, mock_run, gpu_manager):
        """Test get_iommu_group."""
        mock_run.return_value = mock.Mock(
            returncode=0, stdout="../../../kernel/iommu_groups/1\n"
        )

        result = gpu_manager.get_iommu_group("0000:b3:00.0")

        assert result == 1

    @mock.patch("subprocess.run")
    def test_vfio_modules_loaded_all_present(self, mock_run, gpu_manager):
        """Test vfio_modules_loaded when all modules present."""
        mock_run.return_value = mock.Mock(
            returncode=0, stdout="vfio\nvfio_pci\nvfio_iommu_type1\n"
        )

        result = gpu_manager.vfio_modules_loaded()

        assert result is True

    @mock.patch("subprocess.run")
    def test_vfio_modules_loaded_missing(self, mock_run, gpu_manager):
        """Test vfio_modules_loaded when modules missing."""
        mock_run.return_value = mock.Mock(returncode=0, stdout="vfio\n")

        result = gpu_manager.vfio_modules_loaded()

        assert result is False

    @mock.patch("subprocess.run")
    def test_ensure_vfio_modules_already_present(self, mock_run, gpu_manager):
        """Test ensure_vfio_modules when modules already configured."""
        mock_run.return_value = mock.Mock(
            returncode=0, stdout="vfio\nvfio_iommu_type1\nvfio_pci\nvfio_virqfd\n"
        )

        result = gpu_manager.ensure_vfio_modules()

        assert result is False  # No changes needed

    def test_create_hostpci_config_gpu_only(self, gpu_manager):
        """Test create_hostpci_config with GPU only."""
        config = gpu_manager.create_hostpci_config("0000:b3:00.0")

        assert config == "b3:00.0,pcie=1,x-vga=1"

    def test_create_hostpci_config_gpu_and_audio(self, gpu_manager):
        """Test create_hostpci_config with GPU and audio."""
        config = gpu_manager.create_hostpci_config("0000:b3:00.0", "0000:b3:00.1")

        assert config == "b3:00.0;b3:00.1,pcie=1,x-vga=1"

    def test_verify_gpu_passthrough_configured(self, gpu_manager, mock_proxmox):
        """Test verify_gpu_passthrough when GPU is configured."""
        mock_proxmox.nodes.return_value.qemu.return_value.config.get.return_value = {
            "hostpci0": "b3:00.0,pcie=1"
        }

        result = gpu_manager.verify_gpu_passthrough(110)

        assert result is True

    def test_verify_gpu_passthrough_not_configured(self, gpu_manager, mock_proxmox):
        """Test verify_gpu_passthrough when GPU not configured."""
        mock_proxmox.nodes.return_value.qemu.return_value.config.get.return_value = {
            "memory": 4096
        }

        result = gpu_manager.verify_gpu_passthrough(110)

        assert result is False
