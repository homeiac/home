"""Kubernetes client wrapper for Frigate Health Checker."""

from datetime import UTC
from typing import Any, cast

import structlog
from kubernetes import client, config  # type: ignore[import-untyped]
from kubernetes.client.exceptions import ApiException  # type: ignore[import-untyped]
from kubernetes.stream import stream  # type: ignore[import-untyped]

from .config import Settings

logger = structlog.get_logger()


class KubernetesClient:
    """Wrapper for Kubernetes API operations."""

    def __init__(self, settings: Settings) -> None:
        """Initialize Kubernetes client."""
        self.settings = settings
        self._load_config()
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()

    def _load_config(self) -> None:
        """Load Kubernetes configuration."""
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            config.load_kube_config()
            logger.info("Loaded local Kubernetes config")

    def get_frigate_pod(self) -> client.V1Pod | None:
        """Get the Frigate pod."""
        try:
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.settings.namespace,
                label_selector=self.settings.pod_label_selector,
            )
            if pods.items:
                return pods.items[0]
            return None
        except ApiException as e:
            logger.error("Failed to list pods", error=str(e))
            return None

    def get_pod_node_name(self, pod: client.V1Pod) -> str | None:
        """Get the node name where a pod is running."""
        return pod.spec.node_name if pod.spec else None

    def is_node_ready(self, node_name: str) -> bool:
        """Check if a node is in Ready state."""
        try:
            node = self.core_v1.read_node(name=node_name)
            if node.status and node.status.conditions:
                for condition in node.status.conditions:
                    if condition.type == "Ready":
                        return cast(bool, condition.status == "True")
            return False
        except ApiException as e:
            logger.error("Failed to get node status", node=node_name, error=str(e))
            return False

    def exec_in_pod(self, pod_name: str, command: list[str], timeout: int = 10) -> tuple[str, bool]:
        """Execute a command in a pod and return output."""
        try:
            result = stream(
                self.core_v1.connect_get_namespaced_pod_exec,
                pod_name,
                self.settings.namespace,
                command=command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
                _request_timeout=timeout,
            )
            # stream() returns a WSClient that reads all output as a string
            # Ensure we have a proper string
            if result is None:
                return "", False
            output = str(result) if not isinstance(result, str) else result
            return output, True
        except ApiException as e:
            logger.error("Failed to exec in pod", pod=pod_name, error=str(e))
            return str(e), False

    def get_pod_logs(self, pod_name: str, since_seconds: int) -> str:
        """Get pod logs from the last N seconds."""
        try:
            return cast(
                str,
                self.core_v1.read_namespaced_pod_log(
                    name=pod_name,
                    namespace=self.settings.namespace,
                    since_seconds=since_seconds,
                ),
            )
        except ApiException as e:
            logger.error("Failed to get pod logs", pod=pod_name, error=str(e))
            return ""

    def get_configmap_data(self, name: str) -> dict[str, str]:
        """Get ConfigMap data."""
        try:
            cm = self.core_v1.read_namespaced_config_map(
                name=name,
                namespace=self.settings.namespace,
            )
            return cm.data or {}
        except ApiException as e:
            logger.error("Failed to read ConfigMap", name=name, error=str(e))
            return {}

    def patch_configmap(self, name: str, data: dict[str, str]) -> bool:
        """Patch ConfigMap data."""
        try:
            body = {"data": data}
            self.core_v1.patch_namespaced_config_map(
                name=name,
                namespace=self.settings.namespace,
                body=body,
            )
            logger.info("Patched ConfigMap", name=name, data=data)
            return True
        except ApiException as e:
            logger.error("Failed to patch ConfigMap", name=name, error=str(e))
            return False

    def restart_deployment(self, name: str) -> bool:
        """Trigger a rolling restart of a deployment."""
        try:
            # Patch the deployment with a restart annotation
            from datetime import datetime

            now = datetime.now(UTC).isoformat()
            body: dict[str, Any] = {
                "spec": {
                    "template": {
                        "metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": now}}
                    }
                }
            }
            self.apps_v1.patch_namespaced_deployment(
                name=name,
                namespace=self.settings.namespace,
                body=body,
            )
            logger.info("Restarted deployment", name=name)
            return True
        except ApiException as e:
            logger.error("Failed to restart deployment", name=name, error=str(e))
            return False
