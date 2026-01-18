"""Tests for data models."""

import time

from frigate_health_checker.models import (
    HealthCheckResult,
    HealthMetrics,
    HealthState,
    HealthStatus,
    RestartDecision,
    UnhealthyReason,
)


class TestHealthState:
    """Tests for HealthState model."""

    def test_from_configmap_data_empty(self) -> None:
        """Test creating HealthState from empty ConfigMap data."""
        state = HealthState.from_configmap_data({})
        assert state.consecutive_failures == 0
        assert state.last_restart_times == []
        assert state.alert_sent_for_incident is False

    def test_from_configmap_data_with_values(self) -> None:
        """Test creating HealthState from ConfigMap data with values."""
        data = {
            "consecutive_failures": "3",
            "last_restart_times": "1700000000,1700001000,1700002000",
            "alert_sent_for_incident": "true",
        }
        state = HealthState.from_configmap_data(data)
        assert state.consecutive_failures == 3
        assert state.last_restart_times == [1700000000, 1700001000, 1700002000]
        assert state.alert_sent_for_incident is True

    def test_from_configmap_data_with_invalid_timestamps(self) -> None:
        """Test that invalid timestamps are ignored."""
        data = {
            "last_restart_times": "1700000000,invalid,1700002000,,",
        }
        state = HealthState.from_configmap_data(data)
        assert state.last_restart_times == [1700000000, 1700002000]

    def test_to_configmap_data(self) -> None:
        """Test converting HealthState to ConfigMap data."""
        state = HealthState(
            consecutive_failures=2,
            last_restart_times=[1700000000, 1700001000],
            alert_sent_for_incident=True,
        )
        data = state.to_configmap_data()
        assert data["consecutive_failures"] == "2"
        assert data["last_restart_times"] == "1700000000,1700001000"
        assert data["alert_sent_for_incident"] == "true"

    def test_restarts_in_window(self) -> None:
        """Test counting restarts within time window."""
        now = int(time.time())
        state = HealthState(
            consecutive_failures=0,
            last_restart_times=[
                now - 7200,  # 2 hours ago (outside window)
                now - 1800,  # 30 min ago (inside window)
                now - 300,   # 5 min ago (inside window)
            ],
            alert_sent_for_incident=False,
        )
        assert state.restarts_in_window(3600) == 2  # last hour
        assert state.restarts_in_window(600) == 1   # last 10 min
        assert state.restarts_in_window(60) == 0    # last minute

    def test_add_restart_timestamp(self) -> None:
        """Test adding restart timestamp with retention."""
        now = int(time.time())
        state = HealthState(
            consecutive_failures=0,
            last_restart_times=[now - 10000, now - 5000],
            alert_sent_for_incident=False,
        )
        state.add_restart_timestamp(now, 7200)  # 2 hour retention

        # Old timestamp should be pruned, new one added
        assert now - 10000 not in state.last_restart_times
        assert now in state.last_restart_times


class TestHealthCheckResult:
    """Tests for HealthCheckResult model."""

    def test_is_healthy_true(self) -> None:
        """Test is_healthy property when healthy."""
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            metrics=HealthMetrics(),
        )
        assert result.is_healthy is True

    def test_is_healthy_false(self) -> None:
        """Test is_healthy property when unhealthy."""
        result = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            reason=UnhealthyReason.API_UNRESPONSIVE,
            metrics=HealthMetrics(),
        )
        assert result.is_healthy is False


class TestRestartDecision:
    """Tests for RestartDecision model."""

    def test_default_values(self) -> None:
        """Test default values for RestartDecision."""
        decision = RestartDecision(should_restart=True, reason="test")
        assert decision.should_restart is True
        assert decision.reason == "test"
        assert decision.should_alert is False
        assert decision.circuit_breaker_triggered is False
        assert decision.node_unavailable is False
