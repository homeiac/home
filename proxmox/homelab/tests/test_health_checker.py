"""Tests for health_checker module."""
import pytest
from unittest import mock

from homelab.health_checker import VMHealthChecker, VMHealthStatus


@pytest.fixture
def mock_proxmox():
    """Mock Proxmox API client."""
    return mock.MagicMock()


@pytest.fixture
def health_checker(mock_proxmox):
    """Create VMHealthChecker instance."""
    return VMHealthChecker(mock_proxmox, "test-node")


class TestVMHealthChecker:
    """Tests for VMHealthChecker class."""

    def test_init(self, health_checker):
        """Test VMHealthChecker initialization."""
        assert health_checker.node_name == "test-node"
        assert health_checker.proxmox is not None

    def test_vm_running_is_healthy(self, health_checker, mock_proxmox):
        """VM with status='running' should be healthy."""
        mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.return_value = {
            "status": "running",
            "uptime": 3600
        }

        status = health_checker.check_vm_health(108)

        assert status.is_healthy is True
        assert status.should_delete is False
        assert "running" in status.reason.lower()

    def test_vm_stopped_for_long_time_is_unhealthy(self, health_checker, mock_proxmox):
        """VM stopped for >5 min should be marked for deletion."""
        mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.return_value = {
            "status": "stopped",
            "uptime": 0
        }

        status = health_checker.check_vm_health(108)

        assert status.is_healthy is False
        assert status.should_delete is True
        assert "stopped" in status.reason.lower()

    def test_vm_does_not_exist(self, health_checker, mock_proxmox):
        """VM that doesn't exist should be marked unhealthy but not for deletion."""
        mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.side_effect = Exception("VM not found")

        status = health_checker.check_vm_health(999)

        assert status.is_healthy is False
        assert status.should_delete is False
        assert "error" in status.reason.lower()

    def test_vm_paused_state(self, health_checker, mock_proxmox):
        """VM in paused state should be marked unhealthy and for deletion."""
        mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.return_value = {
            "status": "paused",
            "uptime": 1000
        }

        status = health_checker.check_vm_health(108)

        assert status.is_healthy is False
        assert status.should_delete is True
        assert "paused" in status.reason.lower()

    def test_vm_unknown_state(self, health_checker, mock_proxmox):
        """VM in unknown state should be marked unhealthy but not for deletion."""
        mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.return_value = {
            "status": "weird-state",
            "uptime": 100
        }

        status = health_checker.check_vm_health(108)

        assert status.is_healthy is False
        assert status.should_delete is False
        assert "unknown" in status.reason.lower()

    def test_validate_network_bridges_all_exist(self, health_checker, mock_proxmox):
        """Should return True when all bridges exist."""
        mock_proxmox.nodes.return_value.network.get.return_value = [
            {"iface": "vmbr0", "type": "bridge"},
            {"iface": "vmbr1", "type": "bridge"},
            {"iface": "eth0", "type": "eth"}
        ]

        result = health_checker.validate_network_bridges(["vmbr0", "vmbr1"])

        assert result is True

    def test_validate_network_bridges_missing_bridge(self, health_checker, mock_proxmox):
        """Should return False when a required bridge is missing."""
        mock_proxmox.nodes.return_value.network.get.return_value = [
            {"iface": "vmbr0", "type": "bridge"},
            {"iface": "eth0", "type": "eth"}
        ]

        result = health_checker.validate_network_bridges(["vmbr0", "vmbr1"])

        assert result is False

    def test_validate_network_bridges_empty_list(self, health_checker, mock_proxmox):
        """Should return True when no bridges are required."""
        mock_proxmox.nodes.return_value.network.get.return_value = []

        result = health_checker.validate_network_bridges([])

        assert result is True

    def test_validate_network_bridges_api_error(self, health_checker, mock_proxmox):
        """Should return False when API call fails."""
        mock_proxmox.nodes.return_value.network.get.side_effect = Exception("Network API error")

        result = health_checker.validate_network_bridges(["vmbr0"])

        assert result is False


class TestVMHealthStatus:
    """Tests for VMHealthStatus dataclass."""

    def test_healthy_status_creation(self):
        """Test creating a healthy status."""
        status = VMHealthStatus(
            is_healthy=True,
            should_delete=False,
            reason="VM is running normally"
        )

        assert status.is_healthy is True
        assert status.should_delete is False
        assert status.reason == "VM is running normally"

    def test_unhealthy_status_creation(self):
        """Test creating an unhealthy status."""
        status = VMHealthStatus(
            is_healthy=False,
            should_delete=True,
            reason="VM is stopped"
        )

        assert status.is_healthy is False
        assert status.should_delete is True
        assert status.reason == "VM is stopped"
