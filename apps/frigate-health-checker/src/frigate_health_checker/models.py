"""Data models for Frigate Health Checker."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class HealthStatus(Enum):
    """Health check result status."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class UnhealthyReason(Enum):
    """Reasons for unhealthy status."""

    NO_POD = "no_pod_running"
    API_UNRESPONSIVE = "api_unresponsive"
    NO_FRAMES = "no_frames"  # camera_fps < 1 for one or more cameras
    HIGH_SKIP_RATIO = "high_skip_ratio"  # >80% frames skipped (skipped_fps/camera_fps)
    # Legacy reasons (kept for backwards compatibility)
    INFERENCE_SLOW = "inference_slow"
    DETECTION_STUCK = "detection_stuck"
    RECORDING_BACKLOG = "recording_backlog"
    NODE_NOT_READY = "node_not_ready"


@dataclass
class HealthMetrics:
    """Metrics collected during health check."""

    inference_speed_ms: float | None = None
    stuck_detection_count: int = 0
    recording_backlog_count: int = 0
    pod_name: str | None = None
    node_name: str | None = None
    api_responsive: bool = False


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    status: HealthStatus
    reason: UnhealthyReason | None = None
    metrics: HealthMetrics = field(default_factory=HealthMetrics)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    message: str = ""

    @property
    def is_healthy(self) -> bool:
        """Check if result indicates healthy status."""
        return self.status == HealthStatus.HEALTHY


@dataclass
class HealthState:
    """Persisted health state from ConfigMap."""

    consecutive_failures: int = 0
    last_restart_times: list[int] = field(default_factory=list)
    alert_sent_for_incident: bool = False

    @classmethod
    def from_configmap_data(cls, data: dict[str, str]) -> "HealthState":
        """Create HealthState from ConfigMap data."""
        restart_times_str = data.get("last_restart_times", "")
        restart_times = []
        if restart_times_str:
            for ts in restart_times_str.split(","):
                ts = ts.strip()
                if ts.isdigit():
                    restart_times.append(int(ts))

        return cls(
            consecutive_failures=int(data.get("consecutive_failures", "0")),
            last_restart_times=restart_times,
            alert_sent_for_incident=data.get("alert_sent_for_incident", "false").lower() == "true",
        )

    def to_configmap_data(self) -> dict[str, str]:
        """Convert to ConfigMap data format."""
        return {
            "consecutive_failures": str(self.consecutive_failures),
            "last_restart_times": ",".join(str(ts) for ts in self.last_restart_times),
            "alert_sent_for_incident": str(self.alert_sent_for_incident).lower(),
        }

    def restarts_in_window(self, window_seconds: int) -> int:
        """Count restarts within the given time window."""
        import time

        cutoff = int(time.time()) - window_seconds
        return sum(1 for ts in self.last_restart_times if ts > cutoff)

    def add_restart_timestamp(self, timestamp: int, retention_seconds: int) -> None:
        """Add a restart timestamp and prune old ones."""
        cutoff = timestamp - retention_seconds
        self.last_restart_times = [ts for ts in self.last_restart_times if ts > cutoff]
        self.last_restart_times.append(timestamp)


@dataclass
class RestartDecision:
    """Decision about whether to restart Frigate."""

    should_restart: bool
    reason: str
    should_alert: bool = False
    circuit_breaker_triggered: bool = False
    node_unavailable: bool = False
