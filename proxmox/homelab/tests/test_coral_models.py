"""Comprehensive tests for Coral TPU data models."""

import pytest
from pathlib import Path

from homelab.coral_models import (
    CoralDevice,
    CoralMode,
    LXCConfig,
    ContainerStatus,
    SystemState,
    AutomationPlan,
    ActionType,
    InitializationResult,
    CoralAutomationError,
    SafetyViolationError,
    DeviceNotFoundError,
    ConfigurationError,
    InitializationError
)


class TestCoralDevice:
    """Test cases for CoralDevice data model."""

    def test_coral_device_google_mode(self):
        """Test CoralDevice in Google mode."""
        device = CoralDevice(
            mode=CoralMode.GOOGLE,
            bus="003",
            device="004",
            device_path="/dev/bus/usb/003/004",
            description="Google Inc."
        )
        
        assert device.mode == CoralMode.GOOGLE
        assert device.is_initialized is True
        assert device.needs_initialization is False
        assert device.device_path == "/dev/bus/usb/003/004"

    def test_coral_device_unichip_mode(self):
        """Test CoralDevice in Unichip mode."""
        device = CoralDevice(
            mode=CoralMode.UNICHIP,
            bus="003",
            device="003",
            device_path="/dev/bus/usb/003/003",
            description="Global Unichip Corp."
        )
        
        assert device.mode == CoralMode.UNICHIP
        assert device.is_initialized is False
        assert device.needs_initialization is True

    def test_coral_device_not_found(self):
        """Test CoralDevice when not found."""
        device = CoralDevice(mode=CoralMode.NOT_FOUND)
        
        assert device.mode == CoralMode.NOT_FOUND
        assert device.bus is None
        assert device.device is None
        assert device.device_path is None
        assert device.description is None
        assert device.is_initialized is False
        assert device.needs_initialization is False

    def test_coral_device_equality(self):
        """Test CoralDevice equality comparison."""
        device1 = CoralDevice(
            mode=CoralMode.GOOGLE,
            bus="003",
            device="004",
            device_path="/dev/bus/usb/003/004"
        )
        
        device2 = CoralDevice(
            mode=CoralMode.GOOGLE,
            bus="003",
            device="004",
            device_path="/dev/bus/usb/003/004"
        )
        
        device3 = CoralDevice(
            mode=CoralMode.UNICHIP,
            bus="003",
            device="003"
        )
        
        assert device1 == device2
        assert device1 != device3

    def test_coral_device_string_representation(self):
        """Test CoralDevice string representation."""
        device = CoralDevice(
            mode=CoralMode.GOOGLE,
            bus="003",
            device="004",
            device_path="/dev/bus/usb/003/004",
            description="Google Inc."
        )
        
        str_repr = str(device)
        assert "GOOGLE" in str_repr
        assert "/dev/bus/usb/003/004" in str_repr


class TestLXCConfig:
    """Test cases for LXCConfig data model."""

    def test_lxc_config_creation(self):
        """Test LXCConfig creation."""
        config = LXCConfig(
            container_id="113",
            config_path=Path("/etc/pve/lxc/113.conf"),
            current_dev0="/dev/bus/usb/003/004",
            has_usb_permissions=True,
            status=ContainerStatus.RUNNING
        )
        
        assert config.container_id == "113"
        assert config.current_dev0 == "/dev/bus/usb/003/004"
        assert config.has_usb_permissions is True
        assert config.status == ContainerStatus.RUNNING

    def test_lxc_config_defaults(self):
        """Test LXCConfig with default values."""
        config = LXCConfig(
            container_id="113",
            config_path=Path("/etc/pve/lxc/113.conf")
        )
        
        assert config.current_dev0 is None
        assert config.has_usb_permissions is False
        assert config.status == ContainerStatus.UNKNOWN


class TestSystemState:
    """Test cases for SystemState data model."""

    def test_system_state_creation(self, coral_device_google, lxc_config_optimal):
        """Test SystemState creation."""
        state = SystemState(
            coral=coral_device_google,
            lxc=lxc_config_optimal,
            frigate_using_tpu=True
        )
        
        assert state.coral == coral_device_google
        assert state.lxc == lxc_config_optimal
        assert state.frigate_using_tpu is True

    def test_system_state_config_matches_device(self, coral_device_google, lxc_config_optimal):
        """Test config_matches_device property."""
        state = SystemState(
            coral=coral_device_google,
            lxc=lxc_config_optimal,
            frigate_using_tpu=True
        )
        
        assert state.config_matches_device is True

    def test_system_state_config_mismatch(self, coral_device_google, lxc_config_wrong_path):
        """Test config_matches_device when paths don't match."""
        state = SystemState(
            coral=coral_device_google,
            lxc=lxc_config_wrong_path,
            frigate_using_tpu=False
        )
        
        assert state.config_matches_device is False

    def test_system_state_no_coral_device(self, coral_device_not_found, lxc_config_optimal):
        """Test config_matches_device when no coral device."""
        state = SystemState(
            coral=coral_device_not_found,
            lxc=lxc_config_optimal,
            frigate_using_tpu=False
        )
        
        assert state.config_matches_device is False


class TestAutomationPlan:
    """Test cases for AutomationPlan data model."""

    def test_automation_plan_creation(self):
        """Test AutomationPlan creation."""
        plan = AutomationPlan(
            actions=[ActionType.INITIALIZE_CORAL, ActionType.UPDATE_CONFIG],
            reason="Coral needs initialization and config update",
            safe=True,
            backup_required=True
        )
        
        assert ActionType.INITIALIZE_CORAL in plan.actions
        assert ActionType.UPDATE_CONFIG in plan.actions
        assert plan.safe is True
        assert plan.backup_required is True

    def test_automation_plan_defaults(self):
        """Test AutomationPlan with default values."""
        plan = AutomationPlan(
            actions=[ActionType.NO_ACTION],
            reason="System optimal"
        )
        
        assert plan.safe is True
        assert plan.backup_required is False

    def test_automation_plan_unsafe(self):
        """Test AutomationPlan marked as unsafe."""
        plan = AutomationPlan(
            actions=[ActionType.ERROR_ABORT],
            reason="Unsafe conditions detected",
            safe=False
        )
        
        assert plan.safe is False


class TestInitializationResult:
    """Test cases for InitializationResult data model."""

    def test_initialization_result_success(self):
        """Test successful InitializationResult."""
        result = InitializationResult(
            success=True,
            stdout="----INFERENCE TIME----\n13.6ms\n-------RESULTS--------\nAra macao: 0.77734",
            stderr="",
            execution_time=2.5
        )
        
        assert result.success is True
        assert "13.6ms" in result.stdout
        assert result.execution_time == 2.5

    def test_initialization_result_failure(self):
        """Test failed InitializationResult."""
        result = InitializationResult(
            success=False,
            stdout="",
            stderr="RuntimeError: Failed to load model",
            execution_time=0.0
        )
        
        assert result.success is False
        assert "RuntimeError" in result.stderr

    def test_initialization_result_dry_run(self):
        """Test InitializationResult for dry run."""
        result = InitializationResult(
            success=True,
            stdout="[DRY RUN] Would execute initialization",
            stderr="",
            execution_time=0.0,
            dry_run=True
        )
        
        assert result.dry_run is True
        assert "[DRY RUN]" in result.stdout


class TestEnums:
    """Test cases for enumeration types."""

    def test_coral_mode_enum(self):
        """Test CoralMode enumeration."""
        assert CoralMode.GOOGLE.value == "18d1:9302"
        assert CoralMode.UNICHIP.value == "1a6e:089a"
        assert CoralMode.NOT_FOUND.value == "not_found"

    def test_container_status_enum(self):
        """Test ContainerStatus enumeration."""
        assert ContainerStatus.RUNNING.value == "running"
        assert ContainerStatus.STOPPED.value == "stopped"
        assert ContainerStatus.ERROR.value == "error"
        assert ContainerStatus.UNKNOWN.value == "unknown"

    def test_action_type_enum(self):
        """Test ActionType enumeration."""
        assert ActionType.NO_ACTION.value == "no_action"
        assert ActionType.INITIALIZE_CORAL.value == "initialize_coral"
        assert ActionType.UPDATE_CONFIG.value == "update_config"
        assert ActionType.RESTART_CONTAINER.value == "restart_container"
        assert ActionType.ERROR_ABORT.value == "error_abort"


class TestExceptions:
    """Test cases for exception classes."""

    def test_coral_automation_error(self):
        """Test CoralAutomationError exception."""
        with pytest.raises(CoralAutomationError, match="Test automation error"):
            raise CoralAutomationError("Test automation error")

    def test_safety_violation_error(self):
        """Test SafetyViolationError exception."""
        with pytest.raises(SafetyViolationError, match="Safety violation"):
            raise SafetyViolationError("Safety violation")

    def test_device_not_found_error(self):
        """Test DeviceNotFoundError exception."""
        with pytest.raises(DeviceNotFoundError, match="Device not found"):
            raise DeviceNotFoundError("Device not found")

    def test_configuration_error(self):
        """Test ConfigurationError exception."""
        with pytest.raises(ConfigurationError, match="Configuration error"):
            raise ConfigurationError("Configuration error")

    def test_initialization_error(self):
        """Test InitializationError exception."""
        with pytest.raises(InitializationError, match="Initialization error"):
            raise InitializationError("Initialization error")

    def test_exception_inheritance(self):
        """Test that all custom exceptions inherit from CoralAutomationError."""
        assert issubclass(SafetyViolationError, CoralAutomationError)
        assert issubclass(DeviceNotFoundError, CoralAutomationError)
        assert issubclass(ConfigurationError, CoralAutomationError)
        assert issubclass(InitializationError, CoralAutomationError)


class TestDataModelIntegration:
    """Integration tests for data models working together."""

    def test_full_system_state_workflow(self):
        """Test complete system state workflow."""
        # Create devices and configs
        coral = CoralDevice(
            mode=CoralMode.UNICHIP,
            bus="003",
            device="003",
            device_path="/dev/bus/usb/003/003"
        )
        
        lxc = LXCConfig(
            container_id="113",
            config_path=Path("/etc/pve/lxc/113.conf"),
            status=ContainerStatus.STOPPED
        )
        
        # Create system state
        state = SystemState(
            coral=coral,
            lxc=lxc,
            frigate_using_tpu=False
        )
        
        # Create automation plan
        plan = AutomationPlan(
            actions=[ActionType.INITIALIZE_CORAL, ActionType.UPDATE_CONFIG],
            reason="Coral needs initialization",
            safe=True
        )
        
        # Verify the workflow
        assert state.coral.needs_initialization is True
        assert state.config_matches_device is False
        assert plan.safe is True
        assert ActionType.INITIALIZE_CORAL in plan.actions