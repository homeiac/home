"""Tests for health checker logic."""

import json
from unittest.mock import MagicMock

from frigate_health_checker.config import Settings
from frigate_health_checker.health_checker import HealthChecker, RestartManager
from frigate_health_checker.models import (
    HealthCheckResult,
    HealthMetrics,
    HealthState,
    HealthStatus,
    UnhealthyReason,
)


class TestHealthChecker:
    """Tests for HealthChecker class."""

    def test_check_health_no_pod(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
    ) -> None:
        """Test health check when no pod is found."""
        mock_k8s_client.get_frigate_pod.return_value = None
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        assert result.status == HealthStatus.UNHEALTHY
        assert result.reason == UnhealthyReason.NO_POD

    def test_check_health_api_unresponsive(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
    ) -> None:
        """Test health check when API is unresponsive."""
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = ("", False)
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        assert result.status == HealthStatus.UNHEALTHY
        assert result.reason == UnhealthyReason.API_UNRESPONSIVE

    def test_check_health_slow_inference(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
        frigate_stats_slow_inference: dict,
    ) -> None:
        """Test health check with slow Coral inference."""
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(frigate_stats_slow_inference),
            True,
        )
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        assert result.status == HealthStatus.UNHEALTHY
        assert result.reason == UnhealthyReason.INFERENCE_SLOW
        assert result.metrics.inference_speed_ms == 250.0

    def test_check_health_detection_stuck(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
        frigate_stats_healthy: dict,
    ) -> None:
        """Test health check with stuck detection."""
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(frigate_stats_healthy),
            True,
        )
        # Simulate logs with stuck detection messages
        mock_k8s_client.get_pod_logs.return_value = """
2024-01-15 10:00:00 Detection appears to be stuck
2024-01-15 10:01:00 Detection appears to be stuck
2024-01-15 10:02:00 Detection appears to be stuck
"""
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        assert result.status == HealthStatus.UNHEALTHY
        assert result.reason == UnhealthyReason.DETECTION_STUCK
        assert result.metrics.stuck_detection_count == 3

    def test_check_health_recording_backlog(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
        frigate_stats_healthy: dict,
    ) -> None:
        """Test health check with recording backlog."""
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(frigate_stats_healthy),
            True,
        )
        # Simulate logs with backlog messages (more than threshold)
        backlog_msg = "Too many unprocessed recording segments\n"
        mock_k8s_client.get_pod_logs.return_value = backlog_msg * 6
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        assert result.status == HealthStatus.UNHEALTHY
        assert result.reason == UnhealthyReason.RECORDING_BACKLOG
        assert result.metrics.recording_backlog_count == 6

    def test_check_health_all_healthy(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
        frigate_stats_healthy: dict,
    ) -> None:
        """Test health check when everything is healthy."""
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(frigate_stats_healthy),
            True,
        )
        mock_k8s_client.get_pod_logs.return_value = "Normal log output"
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        assert result.status == HealthStatus.HEALTHY
        assert result.reason is None
        assert result.metrics.api_responsive is True
        assert result.metrics.inference_speed_ms == 45.5


class TestRestartManager:
    """Tests for RestartManager class."""

    def test_evaluate_restart_healthy(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        empty_state: HealthState,
    ) -> None:
        """Test restart evaluation when healthy."""
        manager = RestartManager(settings, mock_k8s_client)
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            metrics=HealthMetrics(),
        )

        decision = manager.evaluate_restart(result, empty_state)

        assert decision.should_restart is False
        assert "healthy" in decision.reason.lower()

    def test_evaluate_restart_first_failure(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        empty_state: HealthState,
    ) -> None:
        """Test restart evaluation on first failure (should wait)."""
        manager = RestartManager(settings, mock_k8s_client)
        result = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            reason=UnhealthyReason.API_UNRESPONSIVE,
            metrics=HealthMetrics(),
        )

        decision = manager.evaluate_restart(result, empty_state)

        assert decision.should_restart is False
        assert "1/2" in decision.reason  # Waiting for confirmation

    def test_evaluate_restart_consecutive_failures(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        state_with_one_failure: HealthState,
    ) -> None:
        """Test restart evaluation with consecutive failures (should restart)."""
        mock_k8s_client.is_node_ready.return_value = True
        manager = RestartManager(settings, mock_k8s_client)
        result = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            reason=UnhealthyReason.API_UNRESPONSIVE,
            metrics=HealthMetrics(node_name="still-fawn"),
        )

        decision = manager.evaluate_restart(result, state_with_one_failure)

        assert decision.should_restart is True
        assert decision.should_alert is True

    def test_evaluate_restart_circuit_breaker(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        state_at_circuit_breaker: HealthState,
    ) -> None:
        """Test restart blocked by circuit breaker."""
        manager = RestartManager(settings, mock_k8s_client)
        result = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            reason=UnhealthyReason.API_UNRESPONSIVE,
            metrics=HealthMetrics(),
        )

        decision = manager.evaluate_restart(result, state_at_circuit_breaker)

        assert decision.should_restart is False
        assert decision.circuit_breaker_triggered is True
        assert "circuit breaker" in decision.reason.lower()

    def test_evaluate_restart_node_not_ready(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        state_with_one_failure: HealthState,
    ) -> None:
        """Test restart blocked when node is not ready."""
        mock_k8s_client.is_node_ready.return_value = False
        manager = RestartManager(settings, mock_k8s_client)
        result = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            reason=UnhealthyReason.API_UNRESPONSIVE,
            metrics=HealthMetrics(node_name="still-fawn"),
        )

        decision = manager.evaluate_restart(result, state_with_one_failure)

        assert decision.should_restart is False
        assert decision.node_unavailable is True
        assert "not Ready" in decision.reason

    def test_evaluate_restart_alert_not_sent_twice(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
    ) -> None:
        """Test that alert is not sent twice for same incident."""
        mock_k8s_client.is_node_ready.return_value = True
        manager = RestartManager(settings, mock_k8s_client)
        state = HealthState(
            consecutive_failures=1,
            last_restart_times=[],
            alert_sent_for_incident=True,  # Already sent
        )
        result = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            reason=UnhealthyReason.API_UNRESPONSIVE,
            metrics=HealthMetrics(node_name="still-fawn"),
        )

        decision = manager.evaluate_restart(result, state)

        assert decision.should_restart is True
        assert decision.should_alert is False  # Don't send again

    def test_handle_healthy_resets_state(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
    ) -> None:
        """Test that healthy handler resets failure state."""
        mock_k8s_client.patch_configmap.return_value = True
        manager = RestartManager(settings, mock_k8s_client)
        state = HealthState(
            consecutive_failures=3,
            last_restart_times=[],
            alert_sent_for_incident=True,
        )

        manager.handle_healthy(state)

        assert state.consecutive_failures == 0
        assert state.alert_sent_for_incident is False
        mock_k8s_client.patch_configmap.assert_called_once()

    def test_execute_restart_success(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
    ) -> None:
        """Test successful restart execution."""
        mock_k8s_client.restart_deployment.return_value = True
        manager = RestartManager(settings, mock_k8s_client)
        state = HealthState(
            consecutive_failures=2,
            last_restart_times=[],
            alert_sent_for_incident=False,
        )

        success = manager.execute_restart(state)

        assert success is True
        assert state.consecutive_failures == 0
        assert len(state.last_restart_times) == 1
        mock_k8s_client.restart_deployment.assert_called_once_with("frigate")
