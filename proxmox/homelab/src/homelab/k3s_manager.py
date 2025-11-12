"""K3s cluster management for VM provisioning."""
import json
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class K3sManager:
    """Manages k3s cluster operations for VM provisioning."""

    def get_cluster_token(self, existing_node_ip: str) -> str:
        """
        Get k3s join token from existing cluster node.

        Args:
            existing_node_ip: IP address of existing k3s node

        Returns:
            K3s join token string

        Raises:
            RuntimeError: If token cannot be retrieved
        """
        try:
            result = subprocess.run(
                [
                    "ssh",
                    "-o", "StrictHostKeyChecking=no",
                    f"ubuntu@{existing_node_ip}",
                    "sudo", "cat", "/var/lib/rancher/k3s/server/node-token"
                ],
                capture_output=True,
                check=True,
                timeout=30
            )

            token = result.stdout.decode().strip()
            logger.info(f"✅ Retrieved k3s token from {existing_node_ip}")
            return token

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to retrieve k3s token: {e.stderr.decode()}")
            raise RuntimeError(f"Failed to get k3s token: {e}")
        except subprocess.TimeoutExpired:
            logger.error("Timeout retrieving k3s token")
            raise RuntimeError("Timeout getting k3s token")

    def node_in_cluster(self, node_name: str) -> bool:
        """
        Check if node is already in k3s cluster.

        Args:
            node_name: K3s node name

        Returns:
            True if node exists in cluster
        """
        try:
            result = subprocess.run(
                ["kubectl", "get", "nodes", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.error(f"kubectl error: {result.stderr}")
                return False

            nodes_data = json.loads(result.stdout)
            node_names = [n["metadata"]["name"] for n in nodes_data.get("items", [])]

            exists = node_name in node_names
            if exists:
                logger.info(f"✅ Node {node_name} in cluster")
            else:
                logger.info(f"Node {node_name} not in cluster")

            return exists

        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error checking cluster: {e}")
            return False
