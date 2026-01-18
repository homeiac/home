"""Email notification for Frigate Health Checker."""

import smtplib
import ssl
from email.mime.text import MIMEText

import structlog

from .config import Settings
from .models import HealthCheckResult, UnhealthyReason

logger = structlog.get_logger()


class EmailNotifier:
    """Sends email notifications for health events."""

    def __init__(self, settings: Settings) -> None:
        """Initialize email notifier."""
        self.settings = settings

    def send_restart_notification(
        self,
        health_result: HealthCheckResult,
        restarts_in_hour: int,
    ) -> bool:
        """Send email notification about a restart."""
        if not self.settings.smtp_enabled:
            logger.info("SMTP not configured, skipping email notification")
            return False

        subject = f"[Homelab] Frigate Restarted - {health_result.message}"
        body = self._build_email_body(health_result, restarts_in_hour)

        return self._send_email(subject, body)

    def _build_email_body(
        self,
        health_result: HealthCheckResult,
        restarts_in_hour: int,
    ) -> str:
        """Build email body with restart details."""
        metrics = health_result.metrics
        next_steps = self._get_next_steps(health_result.reason)

        return f"""=== WHAT HAPPENED ===
Frigate was automatically restarted by the health checker.

Time: {health_result.timestamp.isoformat()}
Restarts in last hour: {restarts_in_hour}

=== WHY ===
Primary reason: {health_result.message}

Metrics at restart:
- Coral inference speed: {metrics.inference_speed_ms or "N/A"}ms (threshold: {self.settings.inference_threshold_ms}ms)
- Detection stuck count: {metrics.stuck_detection_count} (threshold: {self.settings.stuck_detection_threshold})
- Recording backlog count: {metrics.recording_backlog_count} (threshold: {self.settings.backlog_threshold})
- Pod: {metrics.pod_name or "N/A"}
- Node: {metrics.node_name or "N/A"}

=== NEXT STEPS ===
{next_steps}

=== MONITOR ===
- Grafana: https://grafana.app.home.panderosystems.com
- Frigate: https://frigate.app.home.panderosystems.com

If this keeps happening (>{self.settings.max_restarts_per_hour}x/hour), circuit breaker will pause restarts.
"""

    def _get_next_steps(self, reason: UnhealthyReason | None) -> str:
        """Get recommended next steps based on failure reason."""
        steps = {
            UnhealthyReason.INFERENCE_SLOW: """1. Check Coral TPU: kubectl exec -n frigate deploy/frigate -- ls /dev/bus/usb
2. Check USB errors: ssh root@still-fawn.maas 'dmesg | grep -i usb | tail -20'
3. If recurring, physical Coral unplug/replug may be needed""",
            UnhealthyReason.DETECTION_STUCK: """1. Check cameras: kubectl exec -n frigate deploy/frigate -- curl -s localhost:5000/api/stats | jq '.cameras'
2. Check go2rtc: kubectl exec -n frigate deploy/frigate -- curl -s localhost:1984/api/streams
3. Camera may be offline or network issue""",
            UnhealthyReason.RECORDING_BACKLOG: """1. Check disk: kubectl exec -n frigate deploy/frigate -- df -h /media/frigate
2. Check recordings: kubectl logs deploy/frigate -n frigate | grep record
3. May need to clear old recordings""",
            UnhealthyReason.NO_POD: """1. Check deployment: kubectl get deploy frigate -n frigate
2. Check events: kubectl get events -n frigate --sort-by='.lastTimestamp'
3. Check node affinity/taints""",
            UnhealthyReason.API_UNRESPONSIVE: """1. Check pod status: kubectl get pods -n frigate
2. Check logs: kubectl logs deploy/frigate -n frigate --tail=100
3. May need to check resource limits""",
        }
        if reason is None:
            return """1. Check logs: kubectl logs deploy/frigate -n frigate --tail=100
2. Check pod: kubectl get pods -n frigate
3. Full diagnostics: scripts/k3s/frigate-cpu-stats.sh --status"""
        return steps.get(
            reason,
            """1. Check logs: kubectl logs deploy/frigate -n frigate --tail=100
2. Check pod: kubectl get pods -n frigate
3. Full diagnostics: scripts/k3s/frigate-cpu-stats.sh --status""",
        )

    def _send_email(self, subject: str, body: str) -> bool:
        """Send email via SMTP."""
        if not self.settings.smtp_user or not self.settings.smtp_password:
            return False

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = f"Frigate Health Checker <{self.settings.smtp_user}>"
        msg["To"] = self.settings.alert_email or self.settings.smtp_user

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                self.settings.smtp_host,
                self.settings.smtp_port,
                context=context,
            ) as server:
                server.login(self.settings.smtp_user, self.settings.smtp_password)
                server.send_message(msg)

            logger.info("Email notification sent successfully")
            return True
        except smtplib.SMTPException as e:
            logger.error("Failed to send email", error=str(e))
            return False
