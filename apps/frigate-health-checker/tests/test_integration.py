"""Integration tests for Frigate Health Checker.

These tests verify the full workflow from health check to restart decision.
They use mocked Kubernetes clients but test real interactions between components.
"""

import json
import time
from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest

from frigate_health_checker.config import Settings
from frigate_health_checker.health_checker import HealthChecker, RestartManager
from frigate_health_checker.models import HealthStatus
from frigate_health_checker.notifier import EmailNotifier


class TestFullWorkflow:
    """Integration tests for complete health check workflow."""

    @pytest.fixture
    def settings(self) -> Settings:
        """Create test settings."""
        return Settings(
            namespace="frigate",
            deployment_name="frigate",
            configmap_name="frigate-health-state",
            pod_label_selector="app=frigate",
            inference_threshold_ms=100,
            stuck_detection_threshold=2,
            backlog_threshold=5,
            consecutive_failures_required=2,
            max_restarts_per_hour=2,
        )

    @pytest.fixture
    def mock_k8s(self) -> MagicMock:
        """Create mock Kubernetes client with common setup."""
        k8s = MagicMock()

        # Mock pod
        pod = MagicMock()
        pod.metadata.name = "frigate-test-pod"
        pod.spec.node_name = "test-node"
        k8s.get_frigate_pod.return_value = pod
        k8s.get_pod_node_name.return_value = "test-node"

        return k8s

    def test_healthy_workflow_resets_state(
        self,
        settings: Settings,
        mock_k8s: MagicMock,
    ) -> None:
        """Test that healthy status resets failure count and alert flag."""
        # Setup: API returns healthy stats
        healthy_stats = {
            "detectors": {"coral": {"inference_speed": 50.0}},
            "cameras": {},
        }
        mock_k8s.exec_in_pod.return_value = (json.dumps(healthy_stats), True)
        mock_k8s.get_pod_logs.return_value = "Normal operation"
        mock_k8s.get_configmap_data.return_value = {
            "consecutive_failures": "3",
            "alert_sent_for_incident": "true",
            "last_restart_times": "",
        }
        mock_k8s.patch_configmap.return_value = True

        # Execute
        checker = HealthChecker(settings, mock_k8s)
        manager = RestartManager(settings, mock_k8s)

        result = checker.check_health()
        state = manager.load_state()
        manager.handle_healthy(state)

        # Verify
        assert result.status == HealthStatus.HEALTHY
        mock_k8s.patch_configmap.assert_called()
        # State should be reset
        assert state.consecutive_failures == 0
        assert state.alert_sent_for_incident is False

    def test_first_failure_does_not_restart(
        self,
        settings: Settings,
        mock_k8s: MagicMock,
    ) -> None:
        """Test that first failure just increments counter, no restart."""
        # Setup: API unresponsive
        mock_k8s.exec_in_pod.return_value = ("", False)
        mock_k8s.get_configmap_data.return_value = {
            "consecutive_failures": "0",
            "alert_sent_for_incident": "false",
            "last_restart_times": "",
        }
        mock_k8s.patch_configmap.return_value = True

        # Execute
        checker = HealthChecker(settings, mock_k8s)
        manager = RestartManager(settings, mock_k8s)

        result = checker.check_health()
        state = manager.load_state()
        decision = manager.evaluate_restart(result, state)

        # Verify
        assert result.is_healthy is False
        assert decision.should_restart is False
        assert "1/2" in decision.reason

    def test_second_failure_triggers_restart(
        self,
        settings: Settings,
        mock_k8s: MagicMock,
    ) -> None:
        """Test that second consecutive failure triggers restart."""
        # Setup: API unresponsive, already have 1 failure
        mock_k8s.exec_in_pod.return_value = ("", False)
        mock_k8s.get_configmap_data.return_value = {
            "consecutive_failures": "1",
            "alert_sent_for_incident": "false",
            "last_restart_times": "",
        }
        mock_k8s.is_node_ready.return_value = True
        mock_k8s.restart_deployment.return_value = True
        mock_k8s.patch_configmap.return_value = True

        # Execute
        checker = HealthChecker(settings, mock_k8s)
        manager = RestartManager(settings, mock_k8s)

        result = checker.check_health()
        state = manager.load_state()
        decision = manager.evaluate_restart(result, state)

        # Verify
        assert result.is_healthy is False
        assert decision.should_restart is True
        assert decision.should_alert is True

    def test_circuit_breaker_prevents_restart_storm(
        self,
        settings: Settings,
        mock_k8s: MagicMock,
    ) -> None:
        """Test that circuit breaker prevents restart storms."""
        # Setup: Already 2 restarts in last hour
        now = int(time.time())
        mock_k8s.exec_in_pod.return_value = ("", False)
        mock_k8s.get_configmap_data.return_value = {
            "consecutive_failures": "1",
            "alert_sent_for_incident": "false",
            "last_restart_times": f"{now - 1800},{now - 900}",  # 2 restarts
        }

        # Execute
        checker = HealthChecker(settings, mock_k8s)
        manager = RestartManager(settings, mock_k8s)

        result = checker.check_health()
        state = manager.load_state()
        decision = manager.evaluate_restart(result, state)

        # Verify
        assert decision.should_restart is False
        assert decision.circuit_breaker_triggered is True
        assert decision.should_alert is True  # Alert still sent even without restart
        mock_k8s.restart_deployment.assert_not_called()

    def test_node_down_prevents_restart(
        self,
        settings: Settings,
        mock_k8s: MagicMock,
    ) -> None:
        """Test that restart is skipped when node is not ready."""
        # Setup: Node not ready
        mock_k8s.exec_in_pod.return_value = ("", False)
        mock_k8s.get_configmap_data.return_value = {
            "consecutive_failures": "1",
            "alert_sent_for_incident": "false",
            "last_restart_times": "",
        }
        mock_k8s.is_node_ready.return_value = False

        # Execute
        checker = HealthChecker(settings, mock_k8s)
        manager = RestartManager(settings, mock_k8s)

        result = checker.check_health()
        state = manager.load_state()
        decision = manager.evaluate_restart(result, state)

        # Verify
        assert decision.should_restart is False
        assert decision.node_unavailable is True
        assert decision.should_alert is True  # Alert still sent even without restart
        assert "not Ready" in decision.reason
        mock_k8s.restart_deployment.assert_not_called()

    def test_alert_sent_only_once_per_incident(
        self,
        settings: Settings,
        mock_k8s: MagicMock,
    ) -> None:
        """Test that email alert is only sent once per incident."""
        # Setup: First restart (alert should be sent)
        mock_k8s.exec_in_pod.return_value = ("", False)
        mock_k8s.get_configmap_data.return_value = {
            "consecutive_failures": "1",
            "alert_sent_for_incident": "false",
            "last_restart_times": "",
        }
        mock_k8s.is_node_ready.return_value = True

        # Execute first check
        checker = HealthChecker(settings, mock_k8s)
        manager = RestartManager(settings, mock_k8s)

        result = checker.check_health()
        state = manager.load_state()
        decision1 = manager.evaluate_restart(result, state)

        assert decision1.should_alert is True

        # Setup: Second restart attempt (alert already sent)
        mock_k8s.get_configmap_data.return_value = {
            "consecutive_failures": "1",
            "alert_sent_for_incident": "true",
            "last_restart_times": "",
        }

        state2 = manager.load_state()
        decision2 = manager.evaluate_restart(result, state2)

        assert decision2.should_restart is True
        assert decision2.should_alert is False

    def test_no_frames_triggers_restart(
        self,
        settings: Settings,
        mock_k8s: MagicMock,
    ) -> None:
        """Test workflow when camera has no frames."""
        # Setup: Camera with 0 FPS
        no_frames_stats = {
            "detectors": {"coral": {"inference_speed": 15.0}},
            "cameras": {
                "front_door": {"camera_fps": 0.0, "detection_fps": 0.0},
            },
        }
        mock_k8s.exec_in_pod.return_value = (json.dumps(no_frames_stats), True)
        mock_k8s.get_configmap_data.return_value = {
            "consecutive_failures": "1",
            "alert_sent_for_incident": "false",
            "last_restart_times": "",
        }
        mock_k8s.is_node_ready.return_value = True

        # Execute
        checker = HealthChecker(settings, mock_k8s)
        manager = RestartManager(settings, mock_k8s)

        result = checker.check_health()
        state = manager.load_state()
        decision = manager.evaluate_restart(result, state)

        # Verify
        assert result.is_healthy is False
        assert "front_door" in result.message
        assert decision.should_restart is True

    def test_healthy_with_all_cameras_working(
        self,
        settings: Settings,
        mock_k8s: MagicMock,
    ) -> None:
        """Test healthy status when all cameras have frames."""
        # Setup: All cameras working
        healthy_stats = {
            "detectors": {"coral": {"inference_speed": 15.0}},
            "cameras": {
                "front_door": {"camera_fps": 5.0, "detection_fps": 0.2},
                "back_yard": {"camera_fps": 5.0, "detection_fps": 0.1},
            },
        }
        mock_k8s.exec_in_pod.return_value = (json.dumps(healthy_stats), True)
        mock_k8s.get_configmap_data.return_value = {
            "consecutive_failures": "0",
            "alert_sent_for_incident": "false",
            "last_restart_times": "",
        }

        # Execute
        checker = HealthChecker(settings, mock_k8s)
        manager = RestartManager(settings, mock_k8s)

        result = checker.check_health()
        state = manager.load_state()
        decision = manager.evaluate_restart(result, state)

        # Verify
        assert result.is_healthy is True
        assert decision.should_restart is False


class TestEmailIntegration:
    """Integration tests for email notification."""

    @pytest.fixture
    def settings_with_smtp(self) -> Settings:
        """Create settings with SMTP configured."""
        return Settings(
            smtp_host="smtp.test.com",
            smtp_port=465,
            smtp_user="test@test.com",
            smtp_password="secret",
            alert_email="alerts@test.com",
        )

    @patch("frigate_health_checker.notifier.smtplib.SMTP_SSL")
    def test_restart_sends_email_with_metrics(
        self,
        mock_smtp: MagicMock,
        settings_with_smtp: Settings,
    ) -> None:
        """Test that restart sends email with correct metrics."""
        from datetime import datetime

        from frigate_health_checker.models import (
            HealthCheckResult,
            HealthMetrics,
            UnhealthyReason,
        )

        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        notifier = EmailNotifier(settings_with_smtp)
        result = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            reason=UnhealthyReason.INFERENCE_SLOW,
            metrics=HealthMetrics(
                inference_speed_ms=250.0,
                stuck_detection_count=0,
                recording_backlog_count=0,
                pod_name="frigate-abc",
                node_name="test-node",
            ),
            timestamp=datetime.now(UTC),
            message="Coral inference 250ms > 100ms",
        )

        success = notifier.send_restart_notification(result, restarts_in_hour=1)

        assert success is True
        mock_server.send_message.assert_called_once()

        # Verify email content
        sent_msg = mock_server.send_message.call_args[0][0]
        email_body = sent_msg.get_payload()
        assert "250" in email_body  # Inference speed
        assert "Coral" in email_body  # Next steps for inference
