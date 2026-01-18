"""Pytest fixtures for Frigate Health Checker tests."""

from unittest.mock import MagicMock, patch

import pytest

from frigate_health_checker.config import Settings
from frigate_health_checker.kubernetes_client import KubernetesClient
from frigate_health_checker.models import HealthMetrics, HealthState


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        namespace="frigate-test",
        deployment_name="frigate",
        configmap_name="frigate-health-state",
        pod_label_selector="app=frigate",
        inference_threshold_ms=100,
        stuck_detection_threshold=2,
        backlog_threshold=5,
        consecutive_failures_required=2,
        max_restarts_per_hour=2,
        frigate_api_port=5000,
        api_timeout_seconds=10,
        log_window_minutes=5,
    )


@pytest.fixture
def mock_k8s_client(settings: Settings) -> MagicMock:
    """Create a mock Kubernetes client."""
    with (
        patch.object(KubernetesClient, "_load_config"),
        patch("frigate_health_checker.kubernetes_client.client"),
    ):
        client = MagicMock(spec=KubernetesClient)
        client.settings = settings
        return client


@pytest.fixture
def healthy_metrics() -> HealthMetrics:
    """Create healthy metrics."""
    return HealthMetrics(
        inference_speed_ms=50.0,
        stuck_detection_count=0,
        recording_backlog_count=0,
        pod_name="frigate-abc123",
        node_name="still-fawn",
        api_responsive=True,
    )


@pytest.fixture
def empty_state() -> HealthState:
    """Create empty health state."""
    return HealthState(
        consecutive_failures=0,
        last_restart_times=[],
        alert_sent_for_incident=False,
    )


@pytest.fixture
def state_with_one_failure() -> HealthState:
    """Create state with one failure."""
    return HealthState(
        consecutive_failures=1,
        last_restart_times=[],
        alert_sent_for_incident=False,
    )


@pytest.fixture
def state_at_circuit_breaker(settings: Settings) -> HealthState:
    """Create state at circuit breaker limit."""
    import time
    now = int(time.time())
    return HealthState(
        consecutive_failures=2,
        last_restart_times=[now - 1800, now - 900],  # 2 restarts in last hour
        alert_sent_for_incident=False,
    )


@pytest.fixture
def mock_pod() -> MagicMock:
    """Create a mock Kubernetes pod."""
    pod = MagicMock()
    pod.metadata.name = "frigate-abc123"
    pod.spec.node_name = "still-fawn"
    return pod


@pytest.fixture
def frigate_stats_healthy() -> dict:
    """Create healthy Frigate stats response."""
    return {
        "detectors": {
            "coral": {
                "inference_speed": 45.5,
                "pid": 123,
            }
        },
        "cameras": {
            "front_door": {"fps": 30, "detection_fps": 5},
        },
    }


@pytest.fixture
def frigate_stats_slow_inference() -> dict:
    """Create Frigate stats with slow inference."""
    return {
        "detectors": {
            "coral": {
                "inference_speed": 250.0,
                "pid": 123,
            }
        },
        "cameras": {},
    }
