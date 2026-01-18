"""Configuration management for Frigate Health Checker."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="FRIGATE_HC_",
        case_sensitive=False,
    )

    # Kubernetes settings
    namespace: str = Field(default="frigate", description="Kubernetes namespace for Frigate")
    deployment_name: str = Field(default="frigate", description="Frigate deployment name")
    configmap_name: str = Field(
        default="frigate-health-state", description="ConfigMap for health state"
    )
    pod_label_selector: str = Field(default="app=frigate", description="Label selector for pods")

    # Health check thresholds
    inference_threshold_ms: int = Field(
        default=100, description="Max acceptable Coral inference speed in ms"
    )
    stuck_detection_threshold: int = Field(
        default=2, description="Max stuck detection events in check window"
    )
    backlog_threshold: int = Field(
        default=5, description="Max recording backlog events in check window"
    )
    consecutive_failures_required: int = Field(
        default=2, description="Consecutive failures before restart"
    )
    max_restarts_per_hour: int = Field(default=2, description="Circuit breaker: max restarts/hour")

    # API settings
    frigate_api_port: int = Field(default=5000, description="Frigate API port")
    api_timeout_seconds: int = Field(default=10, description="API request timeout")
    log_window_minutes: int = Field(default=5, description="Window for log analysis")

    # SMTP settings (optional)
    smtp_host: str = Field(default="smtp.mail.yahoo.com", description="SMTP server host")
    smtp_port: int = Field(default=465, description="SMTP server port")
    smtp_user: str | None = Field(default=None, description="SMTP username")
    smtp_password: str | None = Field(default=None, description="SMTP password")
    alert_email: str | None = Field(default=None, description="Email for alerts")

    # Restart history retention
    restart_history_hours: int = Field(
        default=2, description="Hours to retain restart timestamps"
    )

    @property
    def smtp_enabled(self) -> bool:
        """Check if SMTP is configured."""
        return bool(self.smtp_user and self.smtp_password and self.alert_email)


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
