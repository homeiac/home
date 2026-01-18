"""Tests for configuration."""

import os
from unittest.mock import patch

from frigate_health_checker.config import Settings, get_settings


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        settings = Settings()

        assert settings.namespace == "frigate"
        assert settings.deployment_name == "frigate"
        assert settings.inference_threshold_ms == 100
        assert settings.consecutive_failures_required == 2
        assert settings.max_restarts_per_hour == 2

    def test_smtp_enabled_when_configured(self) -> None:
        """Test SMTP enabled property when configured."""
        settings = Settings(
            smtp_user="test@example.com",
            smtp_password="secret",
            alert_email="alerts@example.com",
        )

        assert settings.smtp_enabled is True

    def test_smtp_disabled_when_not_configured(self) -> None:
        """Test SMTP enabled property when not configured."""
        settings = Settings()

        assert settings.smtp_enabled is False

    def test_smtp_disabled_partial_config(self) -> None:
        """Test SMTP disabled with partial configuration."""
        settings = Settings(
            smtp_user="test@example.com",
            # Missing password and alert_email
        )

        assert settings.smtp_enabled is False

    def test_env_prefix(self) -> None:
        """Test that environment variables use correct prefix."""
        with patch.dict(
            os.environ,
            {
                "FRIGATE_HC_NAMESPACE": "custom-ns",
                "FRIGATE_HC_INFERENCE_THRESHOLD_MS": "200",
            },
        ):
            settings = Settings()

            assert settings.namespace == "custom-ns"
            assert settings.inference_threshold_ms == 200

    def test_get_settings_returns_settings(self) -> None:
        """Test get_settings returns a Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)
