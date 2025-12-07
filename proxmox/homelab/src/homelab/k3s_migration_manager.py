#!/usr/bin/env python3
"""
K3s cluster node management and migration.

Handles:
- Node addition to existing cluster
- GPU verification in cluster nodes
- Workload migration from failed nodes
- Node labeling and tainting
- Cluster state verification

All operations are idempotent and safe to re-run.
"""

import json
import logging
import subprocess
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class K3sMigrationManager:
    """Manages K3s cluster node operations and migrations."""

    def __init__(self, vm_hostname: str, existing_node_ip: str):
        """
        Initialize K3s migration manager.

        Args:
            vm_hostname: Hostname of new VM (e.g., 'k3s-vm-pumped-piglet')
            existing_node_ip: IP of existing K3s node for join token
        """
        self.vm_hostname = vm_hostname
        self.existing_node_ip = existing_node_ip
        self.logger = logger

    def node_in_cluster(self, node_name: str) -> bool:
        """
        Check if node is already in K3s cluster.

        Args:
            node_name: K3s node name

        Returns:
            True if node is in cluster
        """
        try:
            result = subprocess.run(
                ["kubectl", "get", "nodes", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                self.logger.error(f"kubectl error: {result.stderr}")
                return False

            nodes_data = json.loads(result.stdout)
            node_names = [n["metadata"]["name"] for n in nodes_data.get("items", [])]

            exists = node_name in node_names
            if exists:
                self.logger.info(f"✅ Node {node_name} already in cluster")
            else:
                self.logger.info(f"Node {node_name} not in cluster")

            return exists

        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as e:
            self.logger.error(f"Error checking cluster membership: {e}")
            return False

    def get_node_status(self, node_name: str) -> Optional[Dict[str, str]]:
        """
        Get K3s node status.

        Args:
            node_name: K3s node name

        Returns:
            Dictionary with node status or None
        """
        try:
            result = subprocess.run(
                ["kubectl", "get", "node", node_name, "-o", "json"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return None

            node_data = json.loads(result.stdout)
            conditions = node_data.get("status", {}).get("conditions", [])

            # Find Ready condition
            ready_condition = next(
                (c for c in conditions if c["type"] == "Ready"), None
            )

            return {
                "name": node_data["metadata"]["name"],
                "status": ready_condition["status"] if ready_condition else "Unknown",
                "roles": ",".join(
                    node_data["metadata"].get("labels", {}).get(
                        "node-role.kubernetes.io", ""
                    ).split(",")
                ),
            }

        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as e:
            self.logger.error(f"Error getting node status: {e}")
            return None

    def get_join_token(self) -> str:
        """
        Get K3s join token from existing node.

        Returns:
            Join token string

        Raises:
            RuntimeError: If token cannot be retrieved
        """
        try:
            result = subprocess.run(
                [
                    "ssh",
                    f"ubuntu@{self.existing_node_ip}",
                    "sudo",
                    "cat",
                    "/var/lib/rancher/k3s/server/node-token",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            token = result.stdout.strip()
            self.logger.info(f"✅ Retrieved join token from {self.existing_node_ip}")
            return token

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error retrieving join token: {e.stderr}")
            raise RuntimeError(f"Failed to get join token: {e}")

    def k3s_installed(self) -> bool:
        """
        Check if K3s is already installed on target VM.

        Returns:
            True if K3s is installed
        """
        try:
            result = subprocess.run(
                ["ssh", f"ubuntu@{self.vm_hostname}", "which", "k3s"],
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False

    def bootstrap_k3s(
        self,
        token: str,
        master_url: str,
        node_labels: Optional[Dict[str, str]] = None,
        disable_components: Optional[List[str]] = None,
    ) -> bool:
        """
        Bootstrap K3s on new node (idempotent).

        Args:
            token: K3s join token
            master_url: URL of existing K3s server (e.g., 'https://192.168.4.238:6443')
            node_labels: Optional node labels
            disable_components: Optional components to disable

        Returns:
            True if K3s was installed, False if already installed
        """
        if self.k3s_installed():
            self.logger.info(f"✅ K3s already installed on {self.vm_hostname}")
            return False

        # Build install command
        labels = []
        if node_labels:
            labels = [f"--node-label={k}={v}" for k, v in node_labels.items()]

        disable = []
        if disable_components is None:
            disable_components = []  # Don't disable any components by default
        for component in disable_components:
            disable.append(f"--disable={component}")

        install_cmd = (
            f"curl -sfL https://get.k3s.io | "
            f"K3S_TOKEN={token} "
            f"K3S_URL={master_url} "
            f"sh -s - server "
            f"--write-kubeconfig-mode 644 "
            f"{' '.join(disable)} "
            f"{' '.join(labels)} "
            f"--kubelet-arg='feature-gates=DevicePlugins=true'"
        )

        self.logger.info(f"🚀 Installing K3s on {self.vm_hostname}")
        try:
            subprocess.run(
                ["ssh", f"ubuntu@{self.vm_hostname}", install_cmd],
                check=True,
                capture_output=True,
                timeout=300,  # 5 minutes
            )

            # Wait for K3s to be ready
            self._wait_for_k3s_ready()

            self.logger.info(f"✅ K3s installed successfully on {self.vm_hostname}")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error installing K3s: {e.stderr}")
            raise
        except subprocess.TimeoutExpired:
            self.logger.error("K3s installation timed out")
            raise

    def _wait_for_k3s_ready(self, timeout: int = 120) -> None:
        """
        Wait for K3s to be ready.

        Args:
            timeout: Maximum wait time in seconds
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                result = subprocess.run(
                    [
                        "ssh",
                        f"ubuntu@{self.vm_hostname}",
                        "sudo",
                        "k3s",
                        "kubectl",
                        "get",
                        "nodes",
                    ],
                    capture_output=True,
                    timeout=10,
                )

                if result.returncode == 0:
                    self.logger.info("✅ K3s is ready")
                    return

            except subprocess.TimeoutExpired:
                pass

            time.sleep(5)

        raise TimeoutError(f"K3s did not become ready within {timeout}s")

    def verify_gpu_available(self) -> bool:
        """
        Verify GPU is visible in the VM.

        Returns:
            True if nvidia-smi succeeds
        """
        try:
            result = subprocess.run(
                ["ssh", f"ubuntu@{self.vm_hostname}", "nvidia-smi"],
                capture_output=True,
                timeout=30,
            )

            if result.returncode == 0:
                self.logger.info(f"✅ GPU is accessible on {self.vm_hostname}")
                # Log GPU info
                self.logger.debug(f"nvidia-smi output:\n{result.stdout.decode()}")
                return True
            else:
                self.logger.warning(f"⚠️  nvidia-smi failed on {self.vm_hostname}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error("nvidia-smi command timed out")
            return False

    def label_node(self, node_name: str, labels: Dict[str, str]) -> None:
        """
        Apply labels to K3s node (idempotent).

        Args:
            node_name: K3s node name
            labels: Dictionary of labels to apply
        """
        for key, value in labels.items():
            try:
                subprocess.run(
                    [
                        "kubectl",
                        "label",
                        "node",
                        node_name,
                        f"{key}={value}",
                        "--overwrite",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                self.logger.info(f"✅ Applied label {key}={value} to {node_name}")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Error applying label {key}={value}: {e.stderr}")

    def taint_node(
        self, node_name: str, key: str, value: str, effect: str = "NoSchedule"
    ) -> None:
        """
        Apply taint to K3s node (idempotent).

        Args:
            node_name: K3s node name
            key: Taint key
            value: Taint value
            effect: Taint effect (NoSchedule, PreferNoSchedule, NoExecute)
        """
        taint_str = f"{key}={value}:{effect}"
        try:
            subprocess.run(
                ["kubectl", "taint", "node", node_name, taint_str, "--overwrite"],
                check=True,
                capture_output=True,
                timeout=30,
            )
            self.logger.info(f"✅ Applied taint {taint_str} to {node_name}")
        except subprocess.CalledProcessError as e:
            # Ignore error if taint already exists
            if "already has" in e.stderr.decode():
                self.logger.info(f"✅ Taint {taint_str} already exists on {node_name}")
            else:
                self.logger.error(f"Error applying taint: {e.stderr}")

    def cordon_node(self, node_name: str) -> bool:
        """
        Cordon node to prevent new pod scheduling.

        Args:
            node_name: K3s node name

        Returns:
            True if node was cordoned, False if already cordoned
        """
        try:
            # Check if already cordoned
            node_status = self.get_node_status(node_name)
            if node_status:
                # Check if node has unschedulable spec
                result = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "node",
                        node_name,
                        "-o",
                        "jsonpath={.spec.unschedulable}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.stdout.strip() == "true":
                    self.logger.info(f"✅ Node {node_name} already cordoned")
                    return False

            # Cordon the node
            subprocess.run(
                ["kubectl", "cordon", node_name],
                check=True,
                capture_output=True,
                timeout=30,
            )
            self.logger.info(f"✅ Cordoned node {node_name}")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error cordoning node: {e.stderr}")
            raise

    def delete_stuck_pods(self, node_name: str) -> List[str]:
        """
        Delete pods stuck in Terminating or Pending state on a node.

        Args:
            node_name: K3s node name

        Returns:
            List of deleted pod names
        """
        try:
            # Get all pods on the node
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "pods",
                    "-A",
                    "--field-selector",
                    f"spec.nodeName={node_name}",
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            pods_data = json.loads(result.stdout)
            deleted_pods = []

            for pod in pods_data.get("items", []):
                namespace = pod["metadata"]["namespace"]
                name = pod["metadata"]["name"]
                phase = pod["status"].get("phase", "Unknown")

                # Delete if Terminating or Pending
                if phase in ["Terminating", "Pending", "Unknown"]:
                    self.logger.info(f"Deleting stuck pod {namespace}/{name} ({phase})")
                    subprocess.run(
                        [
                            "kubectl",
                            "delete",
                            "pod",
                            "-n",
                            namespace,
                            name,
                            "--force",
                            "--grace-period=0",
                        ],
                        capture_output=True,
                        timeout=60,
                    )
                    deleted_pods.append(f"{namespace}/{name}")

            self.logger.info(f"✅ Deleted {len(deleted_pods)} stuck pods from {node_name}")
            return deleted_pods

        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            self.logger.error(f"Error deleting stuck pods: {e}")
            return []
