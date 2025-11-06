"""Data models for Coral TPU automation."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class CoralMode(Enum):
    """Coral TPU device modes."""

    GOOGLE = "18d1:9302"  # Initialized and ready for use
    UNICHIP = "1a6e:089a"  # Uninitialized, needs Python script
    NOT_FOUND = "not_found"


class ContainerStatus(Enum):
    """LXC container status."""

    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    UNKNOWN = "unknown"


class ActionType(Enum):
    """Automation actions that can be taken."""

    NO_ACTION = "no_action"
    INITIALIZE_CORAL = "initialize_coral"
    UPDATE_CONFIG = "update_config"
    RESTART_CONTAINER = "restart_container"
    INITIALIZE_AND_CONFIG = "initialize_and_config"
    ERROR_ABORT = "error_abort"


@dataclass(frozen=True)
class CoralDevice:
    """Represents a detected Coral TPU device."""

    mode: CoralMode
    bus: Optional[str] = None
    device: Optional[str] = None
    device_path: Optional[str] = None
    description: Optional[str] = None

    @property
    def is_initialized(self) -> bool:
        """Check if Coral is in Google mode (initialized)."""
        return self.mode == CoralMode.GOOGLE

    @property
    def needs_initialization(self) -> bool:
        """Check if Coral needs initialization."""
        return self.mode == CoralMode.UNICHIP


@dataclass(frozen=True)
class LXCConfig:
    """Represents LXC container configuration."""

    container_id: str
    config_path: Path
    current_dev0: Optional[str] = None
    has_usb_permissions: bool = False
    status: ContainerStatus = ContainerStatus.UNKNOWN

    @property
    def device_path_correct(self) -> bool:
        """Check if dev0 path matches expected device path."""
        return self.current_dev0 is not None

    @property
    def needs_usb_permissions(self) -> bool:
        """Check if USB permissions need to be added."""
        return not self.has_usb_permissions


@dataclass(frozen=True)
class SystemState:
    """Complete system state for decision making."""

    coral: CoralDevice
    lxc: LXCConfig
    frigate_using_tpu: bool = False

    @property
    def config_matches_device(self) -> bool:
        """Check if LXC config matches detected device."""
        if self.coral.device_path is None or self.lxc.current_dev0 is None:
            return False
        return self.lxc.current_dev0 == self.coral.device_path

    @property
    def safe_to_initialize(self) -> bool:
        """Check if it's safe to run initialization."""
        return (
            self.coral.needs_initialization
            and not self.frigate_using_tpu
            and self.lxc.status != ContainerStatus.RUNNING
        )

    @property
    def safe_to_update_config(self) -> bool:
        """Check if it's safe to update configuration."""
        return not self.frigate_using_tpu


@dataclass(frozen=True)
class AutomationPlan:
    """Plan for automation actions."""

    actions: list[ActionType]
    reason: str
    safe: bool = True
    backup_required: bool = False

    @property
    def requires_container_restart(self) -> bool:
        """Check if plan requires container restart."""
        return ActionType.RESTART_CONTAINER in self.actions or ActionType.UPDATE_CONFIG in self.actions


@dataclass(frozen=True)
class InitializationResult:
    """Result of Coral TPU initialization."""

    success: bool
    stdout: str
    stderr: str
    execution_time: float = 0.0
    dry_run: bool = False


class CoralAutomationError(Exception):
    """Base exception for Coral automation errors."""

    pass


class SafetyViolationError(CoralAutomationError):
    """Raised when attempting unsafe operations."""

    pass


class DeviceNotFoundError(CoralAutomationError):
    """Raised when Coral device is not detected."""

    pass


class InitializationError(CoralAutomationError):
    """Raised when Coral initialization fails."""

    pass


class ConfigurationError(CoralAutomationError):
    """Raised when LXC configuration operations fail."""

    pass
