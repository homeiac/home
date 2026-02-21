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

    def test_check_health_single_camera_no_frames_is_healthy(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
    ) -> None:
        """Test that one camera down with others OK does not trigger restart."""
        stats_partial = {
            "detectors": {"coral": {"inference_speed": 15.0}},
            "cameras": {
                "front_door": {"camera_fps": 0.0, "detection_fps": 0.0},
                "back_yard": {"camera_fps": 5.0, "detection_fps": 0.1},
            },
        }
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(stats_partial),
            True,
        )
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        # Partial camera failure = camera/network issue, not Frigate
        assert result.status == HealthStatus.HEALTHY

    def test_check_health_all_cameras_no_frames(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
    ) -> None:
        """Test that ALL cameras down triggers unhealthy (Frigate-level problem)."""
        stats_all_down = {
            "detectors": {"coral": {"inference_speed": 15.0}},
            "cameras": {
                "front_door": {"camera_fps": 0.0, "detection_fps": 0.0},
                "back_yard": {"camera_fps": 0.0, "detection_fps": 0.0},
            },
        }
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(stats_all_down),
            True,
        )
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        assert result.status == HealthStatus.UNHEALTHY
        assert result.reason == UnhealthyReason.NO_FRAMES
        assert "front_door" in result.message
        assert "back_yard" in result.message

    def test_check_health_skipped_camera_no_frames(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
    ) -> None:
        """Test that skipped cameras (e.g., doorbell) don't fail health check."""
        stats_doorbell_down = {
            "detectors": {"coral": {"inference_speed": 15.0}},
            "cameras": {
                "reolink_doorbell": {"camera_fps": 0.0, "detection_fps": 0.0},
                "back_yard": {"camera_fps": 5.0, "detection_fps": 0.1},
            },
        }
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(stats_doorbell_down),
            True,
        )
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        # Should be healthy because reolink_doorbell is in skip list
        assert result.status == HealthStatus.HEALTHY
        assert result.reason is None

    def test_check_health_all_healthy(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
    ) -> None:
        """Test health check when everything is healthy."""
        stats_healthy = {
            "detectors": {"coral": {"inference_speed": 15.0}},
            "cameras": {
                "front_door": {"camera_fps": 5.0, "detection_fps": 0.2, "skipped_fps": 0.0},
                "back_yard": {"camera_fps": 5.0, "detection_fps": 0.1, "skipped_fps": 0.5},
            },
        }
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(stats_healthy),
            True,
        )
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        assert result.status == HealthStatus.HEALTHY
        assert result.reason is None
        assert result.metrics.api_responsive is True
        assert result.metrics.inference_speed_ms == 15.0

    def test_check_health_python_repr_output(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
    ) -> None:
        """Test health check handles Python dict repr (single quotes) from k8s stream."""
        # Kubernetes stream() sometimes returns Python repr instead of JSON
        python_repr = str(
            {
                "detectors": {"coral": {"inference_speed": 15.0}},
                "cameras": {
                    "front_door": {"camera_fps": 5.0, "detection_fps": 0.2, "skipped_fps": 0.0},
                },
            }
        )
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (python_repr, True)
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        assert result.status == HealthStatus.HEALTHY
        assert result.metrics.api_responsive is True

    def test_check_health_single_high_skip_ratio_is_healthy(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
    ) -> None:
        """Test that one camera with high skip ratio doesn't trigger restart."""
        stats_high_skip = {
            "detectors": {"coral": {"inference_speed": 15.0}},
            "cameras": {
                "trendnet_ip_572w": {
                    "camera_fps": 5.0,
                    "detection_fps": 0.1,
                    "skipped_fps": 4.5,  # 90% frames skipped!
                },
                "back_yard": {
                    "camera_fps": 5.0,
                    "detection_fps": 0.1,
                    "skipped_fps": 0.5,  # 10% is healthy
                },
            },
        }
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(stats_high_skip),
            True,
        )
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        # Single camera skip = camera issue, not Frigate
        assert result.status == HealthStatus.HEALTHY

    def test_check_health_majority_high_skip_ratio(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
    ) -> None:
        """Test that majority of cameras with high skip triggers unhealthy."""
        stats_all_skipping = {
            "detectors": {"coral": {"inference_speed": 15.0}},
            "cameras": {
                "front_door": {
                    "camera_fps": 5.0,
                    "detection_fps": 0.1,
                    "skipped_fps": 4.5,  # 90%
                },
                "back_yard": {
                    "camera_fps": 5.0,
                    "detection_fps": 0.1,
                    "skipped_fps": 4.5,  # 90%
                },
            },
        }
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(stats_all_skipping),
            True,
        )
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        assert result.status == HealthStatus.UNHEALTHY
        assert result.reason == UnhealthyReason.HIGH_SKIP_RATIO

    def test_check_health_skip_ratio_at_threshold(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
    ) -> None:
        """Test that skip ratio exactly at threshold (80%) is healthy."""
        stats_at_threshold = {
            "detectors": {"coral": {"inference_speed": 15.0}},
            "cameras": {
                "front_door": {
                    "camera_fps": 5.0,
                    "detection_fps": 0.2,
                    "skipped_fps": 4.0,  # Exactly 80% - at threshold, not over
                },
            },
        }
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(stats_at_threshold),
            True,
        )
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        # 80% = threshold, not over threshold, so healthy
        assert result.status == HealthStatus.HEALTHY

    def test_check_health_skip_ratio_just_over_threshold(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
    ) -> None:
        """Test that skip ratio just over threshold (81%) is unhealthy."""
        stats_over_threshold = {
            "detectors": {"coral": {"inference_speed": 15.0}},
            "cameras": {
                "front_door": {
                    "camera_fps": 5.0,
                    "detection_fps": 0.2,
                    "skipped_fps": 4.1,  # 82% - over threshold
                },
            },
        }
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(stats_over_threshold),
            True,
        )
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        assert result.status == HealthStatus.UNHEALTHY
        assert result.reason == UnhealthyReason.HIGH_SKIP_RATIO

    def test_check_health_skipped_camera_high_skip_ignored(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
    ) -> None:
        """Test that skipped cameras (reolink_doorbell) with high skip ratio don't fail."""
        stats_doorbell_high_skip = {
            "detectors": {"coral": {"inference_speed": 15.0}},
            "cameras": {
                "reolink_doorbell": {
                    "camera_fps": 5.0,
                    "detection_fps": 0.0,
                    "skipped_fps": 5.0,  # 100% skipped - but in skip list
                },
                "back_yard": {
                    "camera_fps": 5.0,
                    "detection_fps": 0.1,
                    "skipped_fps": 0.5,
                },
            },
        }
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(stats_doorbell_high_skip),
            True,
        )
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        # Should be healthy because reolink_doorbell is in skip list
        assert result.status == HealthStatus.HEALTHY

    def test_check_health_no_skipped_fps_field(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
        mock_pod: MagicMock,
    ) -> None:
        """Test health check when skipped_fps field is missing (older Frigate)."""
        stats_no_skipped = {
            "detectors": {"coral": {"inference_speed": 15.0}},
            "cameras": {
                "front_door": {"camera_fps": 5.0, "detection_fps": 0.2},
                # No skipped_fps field
            },
        }
        mock_k8s_client.get_frigate_pod.return_value = mock_pod
        mock_k8s_client.get_pod_node_name.return_value = "still-fawn"
        mock_k8s_client.exec_in_pod.return_value = (
            json.dumps(stats_no_skipped),
            True,
        )
        checker = HealthChecker(settings, mock_k8s_client)

        result = checker.check_health()

        # Should be healthy - missing skipped_fps defaults to 0
        assert result.status == HealthStatus.HEALTHY


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
        assert decision.should_alert is True  # Alert even without restart
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
        assert decision.should_alert is True  # Alert even without restart
        assert "not Ready" in decision.reason

    def test_evaluate_restart_alert_cooldown(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
    ) -> None:
        """Test that alert is suppressed within 24h cooldown."""
        import time

        mock_k8s_client.is_node_ready.return_value = True
        manager = RestartManager(settings, mock_k8s_client)
        state = HealthState(
            consecutive_failures=1,
            last_restart_times=[],
            last_alert_time=int(time.time()) - 3600,  # 1 hour ago (within 24h cooldown)
        )
        result = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            reason=UnhealthyReason.API_UNRESPONSIVE,
            metrics=HealthMetrics(node_name="still-fawn"),
        )

        decision = manager.evaluate_restart(result, state)

        assert decision.should_restart is True
        assert decision.should_alert is False  # Within cooldown

    def test_evaluate_restart_alert_after_cooldown(
        self,
        settings: Settings,
        mock_k8s_client: MagicMock,
    ) -> None:
        """Test that alert fires after 24h cooldown expires."""
        import time

        mock_k8s_client.is_node_ready.return_value = True
        manager = RestartManager(settings, mock_k8s_client)
        state = HealthState(
            consecutive_failures=1,
            last_restart_times=[],
            last_alert_time=int(time.time()) - 90000,  # 25 hours ago (past cooldown)
        )
        result = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            reason=UnhealthyReason.API_UNRESPONSIVE,
            metrics=HealthMetrics(node_name="still-fawn"),
        )

        decision = manager.evaluate_restart(result, state)

        assert decision.should_restart is True
        assert decision.should_alert is True  # Cooldown expired

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
            last_alert_time=1700000000,
        )

        manager.handle_healthy(state)

        assert state.consecutive_failures == 0
        assert state.last_alert_time == 0
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
