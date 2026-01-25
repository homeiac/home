"""Core health checking logic for Frigate."""

import json
import re
import time

import structlog

from .config import Settings
from .kubernetes_client import KubernetesClient
from .models import (
    HealthCheckResult,
    HealthMetrics,
    HealthState,
    HealthStatus,
    RestartDecision,
    UnhealthyReason,
)

logger = structlog.get_logger()


class HealthChecker:
    """Performs health checks on Frigate NVR."""

    def __init__(self, settings: Settings, k8s_client: KubernetesClient) -> None:
        """Initialize health checker."""
        self.settings = settings
        self.k8s = k8s_client

    def check_health(self) -> HealthCheckResult:
        """Perform health check on Frigate.

        Simple checks:
        1. Pod exists
        2. API accessible
        3. Cameras have frames (camera_fps > 0)

        Skip cameras in SKIP_CAMERAS list (e.g., doorbell on flaky WiFi).
        """
        metrics = HealthMetrics()

        # Check 1: Pod exists
        pod = self.k8s.get_frigate_pod()
        if not pod:
            logger.warning("No Frigate pod found")
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                reason=UnhealthyReason.NO_POD,
                metrics=metrics,
                message="No Frigate pod running",
            )

        pod_name = pod.metadata.name if pod.metadata else "unknown"
        metrics.pod_name = pod_name
        metrics.node_name = self.k8s.get_pod_node_name(pod)

        # Check 2: API responsiveness
        stats = self._get_frigate_stats(pod_name)
        if stats is None:
            logger.warning("Frigate API unresponsive", pod=pod_name)
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                reason=UnhealthyReason.API_UNRESPONSIVE,
                metrics=metrics,
                message="Frigate API unresponsive",
            )

        metrics.api_responsive = True

        # Check 3: Camera FPS - are frames actually coming in?
        # This is the most important check - if no frames, nothing works
        cameras_without_frames = self._check_camera_fps(stats)
        if cameras_without_frames:
            camera_list = ", ".join(cameras_without_frames)
            logger.warning(
                "Cameras have no frames",
                cameras=cameras_without_frames,
            )
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                reason=UnhealthyReason.NO_FRAMES,
                metrics=metrics,
                message=f"No frames from: {camera_list}",
            )

        # Extract inference speed for logging (but don't fail on it)
        inference_speed = self._extract_inference_speed(stats)
        metrics.inference_speed_ms = inference_speed

        logger.info(
            "Frigate is healthy",
            inference_ms=inference_speed,
            cameras_ok=self._get_camera_count(stats),
        )
        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            metrics=metrics,
            message="All health checks passed",
        )

    def _check_camera_fps(self, stats: dict[str, object]) -> list[str]:
        """Check which cameras have no frames (camera_fps < 1).

        Returns list of camera names with no frames, excluding skipped cameras.
        """
        # Cameras to skip (on flaky networks, etc.)
        skip_cameras = (
            self.settings.skip_cameras
            if hasattr(self.settings, "skip_cameras")
            else ["reolink_doorbell"]
        )

        cameras_without_frames = []
        cameras = stats.get("cameras")
        if not isinstance(cameras, dict):
            return ["unknown"]  # Can't parse cameras = unhealthy

        for camera_name, camera_stats in cameras.items():
            if camera_name in skip_cameras:
                continue
            if not isinstance(camera_stats, dict):
                continue

            camera_fps = camera_stats.get("camera_fps", 0)
            try:
                fps = float(camera_fps)
            except (TypeError, ValueError):
                fps = 0

            if fps < 1:
                cameras_without_frames.append(f"{camera_name}(fps={fps})")

        return cameras_without_frames

    def _get_camera_count(self, stats: dict[str, object]) -> int:
        """Get count of cameras with frames."""
        cameras = stats.get("cameras")
        if not isinstance(cameras, dict):
            return 0
        count = 0
        for camera_stats in cameras.values():
            if isinstance(camera_stats, dict):
                fps = camera_stats.get("camera_fps", 0)
                if isinstance(fps, int | float) and fps >= 1:
                    count += 1
        return count

    def _get_frigate_stats(self, pod_name: str) -> dict[str, object] | None:
        """Get Frigate stats from API."""
        command = [
            "curl",
            "-s",
            "--max-time",
            str(self.settings.api_timeout_seconds),
            f"http://localhost:{self.settings.frigate_api_port}/api/stats",
        ]
        output, success = self.k8s.exec_in_pod(
            pod_name, command, timeout=self.settings.api_timeout_seconds + 5
        )

        if not success or not output:
            return None

        try:
            # The stream() function returns a string, but we need to ensure
            # it's properly decoded. Log the type and first chars for debugging.
            logger.debug(
                "Raw exec output",
                output_type=type(output).__name__,
                output_repr=repr(output[:200]) if len(output) > 200 else repr(output),
            )

            # Handle case where output might already be a dict (shouldn't happen but defensive)
            if isinstance(output, dict):
                return output

            # Ensure output is a string
            if not isinstance(output, str):
                output = str(output)

            # Strip any leading/trailing whitespace
            output = output.strip()

            stats: dict[str, object] = json.loads(output)
            if not stats or stats == {}:
                return None
            return stats
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse Frigate stats JSON",
                error=str(e),
                output_type=type(output).__name__,
                output_preview=repr(output[:200]) if len(output) > 200 else repr(output),
            )
            return None

    def _extract_inference_speed(self, stats: dict[str, object]) -> float | None:
        """Extract Coral inference speed from stats."""
        try:
            detectors = stats.get("detectors")
            if not isinstance(detectors, dict):
                return None
            coral = detectors.get("coral")
            if not isinstance(coral, dict):
                return None
            speed = coral.get("inference_speed")
            if speed is not None:
                return float(speed)
            return None
        except (KeyError, TypeError, ValueError):
            return None

    def _count_pattern(self, text: str, pattern: str) -> int:
        """Count occurrences of a regex pattern in text."""
        return len(re.findall(pattern, text))


class RestartManager:
    """Manages restart decisions and execution."""

    def __init__(self, settings: Settings, k8s_client: KubernetesClient) -> None:
        """Initialize restart manager."""
        self.settings = settings
        self.k8s = k8s_client

    def load_state(self) -> HealthState:
        """Load health state from ConfigMap."""
        data = self.k8s.get_configmap_data(self.settings.configmap_name)
        return HealthState.from_configmap_data(data)

    def save_state(self, state: HealthState) -> bool:
        """Save health state to ConfigMap."""
        return self.k8s.patch_configmap(
            self.settings.configmap_name,
            state.to_configmap_data(),
        )

    def evaluate_restart(
        self,
        health_result: HealthCheckResult,
        state: HealthState,
    ) -> RestartDecision:
        """Evaluate whether a restart should be triggered."""
        # If healthy, no restart needed
        if health_result.is_healthy:
            return RestartDecision(
                should_restart=False,
                reason="Frigate is healthy",
            )

        # Increment failure count
        new_failures = state.consecutive_failures + 1

        # Check if we have enough consecutive failures
        if new_failures < self.settings.consecutive_failures_required:
            return RestartDecision(
                should_restart=False,
                reason=f"Waiting for confirmation ({new_failures}/{self.settings.consecutive_failures_required} failures)",
            )

        # Check circuit breaker (max restarts per hour)
        recent_restarts = state.restarts_in_window(3600)
        if recent_restarts >= self.settings.max_restarts_per_hour:
            return RestartDecision(
                should_restart=False,
                reason=f"Circuit breaker: {recent_restarts} restarts in last hour",
                circuit_breaker_triggered=True,
            )

        # Check node availability
        node_name = health_result.metrics.node_name
        if node_name and not self.k8s.is_node_ready(node_name):
            logger.warning("Node not ready, skipping restart", node=node_name)
            return RestartDecision(
                should_restart=False,
                reason=f"Node {node_name} is not Ready",
                node_unavailable=True,
            )

        # All checks passed, should restart
        return RestartDecision(
            should_restart=True,
            reason=health_result.message,
            should_alert=not state.alert_sent_for_incident,
        )

    def execute_restart(self, state: HealthState) -> bool:
        """Execute the restart and update state."""
        success = self.k8s.restart_deployment(self.settings.deployment_name)

        if success:
            now = int(time.time())
            state.add_restart_timestamp(now, self.settings.restart_history_hours * 3600)
            state.consecutive_failures = 0
            logger.info("Restart executed successfully")

        return success

    def handle_healthy(self, state: HealthState) -> None:
        """Handle transition to healthy state."""
        if state.consecutive_failures > 0 or state.alert_sent_for_incident:
            state.consecutive_failures = 0
            state.alert_sent_for_incident = False
            self.save_state(state)
            logger.info("Reset health state after recovery")

    def handle_unhealthy(
        self,
        health_result: HealthCheckResult,
        state: HealthState,
        decision: RestartDecision,
    ) -> None:
        """Handle unhealthy state based on restart decision."""
        if decision.should_restart:
            success = self.execute_restart(state)
            if success and decision.should_alert:
                state.alert_sent_for_incident = True
            self.save_state(state)
        else:
            # Just update failure count
            state.consecutive_failures += 1
            self.save_state(state)
            logger.info(
                "Updated failure count",
                failures=state.consecutive_failures,
                reason=decision.reason,
            )
