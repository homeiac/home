"""CLI entrypoint for Frigate Health Checker."""

import sys
from datetime import UTC, datetime

import structlog

from .config import get_settings
from .health_checker import HealthChecker, RestartManager
from .kubernetes_client import KubernetesClient
from .notifier import EmailNotifier

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def main() -> int:
    """Main entrypoint for health checker."""
    logger.info(
        "Starting Frigate health check",
        timestamp=datetime.now(UTC).isoformat(),
    )

    try:
        settings = get_settings()
        k8s = KubernetesClient(settings)
        checker = HealthChecker(settings, k8s)
        manager = RestartManager(settings, k8s)
        notifier = EmailNotifier(settings)

        # Load current state
        state = manager.load_state()
        logger.info(
            "Current state",
            consecutive_failures=state.consecutive_failures,
            alert_sent=state.alert_sent_for_incident,
            recent_restarts=state.restarts_in_window(3600),
        )

        # Perform health check
        result = checker.check_health()
        logger.info(
            "Health check complete",
            status=result.status.value,
            reason=result.reason.value if result.reason else None,
            message=result.message,
        )

        if result.is_healthy:
            manager.handle_healthy(state)
            logger.info("Frigate is healthy")
            return 0

        # Evaluate restart decision
        decision = manager.evaluate_restart(result, state)
        logger.info(
            "Restart decision",
            should_restart=decision.should_restart,
            reason=decision.reason,
            circuit_breaker=decision.circuit_breaker_triggered,
            node_unavailable=decision.node_unavailable,
        )

        if decision.should_restart:
            manager.handle_unhealthy(result, state, decision)

            if decision.should_alert:
                restarts = state.restarts_in_window(3600)
                notifier.send_restart_notification(result, restarts)

            logger.info("Restart triggered", reason=result.message)
        else:
            manager.handle_unhealthy(result, state, decision)
            logger.info(
                "Restart not triggered",
                reason=decision.reason,
            )

        return 0

    except Exception as e:
        logger.exception("Health check failed with error", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
