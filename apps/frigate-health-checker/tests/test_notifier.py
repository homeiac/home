"""Tests for email notifier."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from frigate_health_checker.config import Settings
from frigate_health_checker.models import (
    HealthCheckResult,
    HealthMetrics,
    HealthStatus,
    UnhealthyReason,
)
from frigate_health_checker.notifier import EmailNotifier


class TestEmailNotifier:
    """Tests for EmailNotifier class."""

    @pytest.fixture
    def notifier_settings(self) -> Settings:
        """Create settings with SMTP configured."""
        return Settings(
            smtp_host="smtp.test.com",
            smtp_port=465,
            smtp_user="test@test.com",
            smtp_password="secret",
            alert_email="alerts@test.com",
        )

    @pytest.fixture
    def notifier_settings_no_smtp(self) -> Settings:
        """Create settings without SMTP."""
        return Settings()

    @pytest.fixture
    def unhealthy_result(self) -> HealthCheckResult:
        """Create an unhealthy result."""
        return HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            reason=UnhealthyReason.INFERENCE_SLOW,
            metrics=HealthMetrics(
                inference_speed_ms=250.0,
                stuck_detection_count=0,
                recording_backlog_count=0,
                pod_name="frigate-abc123",
                node_name="still-fawn",
            ),
            timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            message="Coral inference 250ms > 100ms",
        )

    def test_send_notification_smtp_disabled(
        self,
        notifier_settings_no_smtp: Settings,
        unhealthy_result: HealthCheckResult,
    ) -> None:
        """Test notification skipped when SMTP not configured."""
        notifier = EmailNotifier(notifier_settings_no_smtp)

        result = notifier.send_restart_notification(unhealthy_result, 1)

        assert result is False

    @patch("frigate_health_checker.notifier.smtplib.SMTP_SSL")
    def test_send_notification_success(
        self,
        mock_smtp: MagicMock,
        notifier_settings: Settings,
        unhealthy_result: HealthCheckResult,
    ) -> None:
        """Test successful email notification."""
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        notifier = EmailNotifier(notifier_settings)

        result = notifier.send_restart_notification(unhealthy_result, 2)

        assert result is True
        mock_server.login.assert_called_once_with("test@test.com", "secret")
        mock_server.send_message.assert_called_once()

    @patch("frigate_health_checker.notifier.smtplib.SMTP_SSL")
    def test_send_notification_smtp_error(
        self,
        mock_smtp: MagicMock,
        notifier_settings: Settings,
        unhealthy_result: HealthCheckResult,
    ) -> None:
        """Test handling of SMTP errors."""
        import smtplib

        mock_smtp.return_value.__enter__.side_effect = smtplib.SMTPException("Connection failed")
        notifier = EmailNotifier(notifier_settings)

        result = notifier.send_restart_notification(unhealthy_result, 1)

        assert result is False

    def test_get_next_steps_inference(
        self,
        notifier_settings: Settings,
    ) -> None:
        """Test next steps for inference issues."""
        notifier = EmailNotifier(notifier_settings)

        steps = notifier._get_next_steps(UnhealthyReason.INFERENCE_SLOW)

        assert "Coral TPU" in steps
        assert "USB" in steps

    def test_get_next_steps_stuck(
        self,
        notifier_settings: Settings,
    ) -> None:
        """Test next steps for stuck detection."""
        notifier = EmailNotifier(notifier_settings)

        steps = notifier._get_next_steps(UnhealthyReason.DETECTION_STUCK)

        assert "cameras" in steps
        assert "go2rtc" in steps

    def test_get_next_steps_backlog(
        self,
        notifier_settings: Settings,
    ) -> None:
        """Test next steps for recording backlog."""
        notifier = EmailNotifier(notifier_settings)

        steps = notifier._get_next_steps(UnhealthyReason.RECORDING_BACKLOG)

        assert "disk" in steps
        assert "recordings" in steps

    def test_build_email_body_content(
        self,
        notifier_settings: Settings,
        unhealthy_result: HealthCheckResult,
    ) -> None:
        """Test email body contains expected content."""
        notifier = EmailNotifier(notifier_settings)

        body = notifier._build_email_body(unhealthy_result, 2)

        assert "WHAT HAPPENED" in body
        assert "Coral inference 250ms > 100ms" in body
        assert "Restarts in last hour: 2" in body
        assert "still-fawn" in body
        assert "frigate-abc123" in body
        assert "Grafana" in body
