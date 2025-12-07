"""K3s cluster management for VM provisioning."""

import json
import logging
import subprocess

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
                    "-o",
                    "StrictHostKeyChecking=no",
                    f"ubuntu@{existing_node_ip}",
                    "sudo",
                    "cat",
                    "/var/lib/rancher/k3s/server/node-token",
                ],
                capture_output=True,
                check=True,
                timeout=30,
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
                ["kubectl", "get", "nodes", "-o", "json"], capture_output=True, text=True, timeout=30
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

    def install_k3s(self, vm_hostname: str, token: str, server_url: str) -> bool:
        """
        Install k3s on VM and join to cluster.

        Args:
            vm_hostname: Hostname of VM to install k3s on
            token: K3s join token
            server_url: URL of k3s server (e.g., https://192.168.4.212:6443)

        Returns:
            True if installation succeeded

        Raises:
            RuntimeError: If installation fails
        """
        install_cmd = (
            f"curl -sfL https://get.k3s.io | "
            f"K3S_TOKEN={token} "
            f"K3S_URL={server_url} "
            f"sh -s - server "
            f"--write-kubeconfig-mode 644"
        )

        logger.info(f"🚀 Installing k3s on {vm_hostname}")

        try:
            subprocess.run(
                ["ssh", "-o", "StrictHostKeyChecking=no", f"ubuntu@{vm_hostname}", install_cmd],
                check=True,
                capture_output=True,
                timeout=300,  # 5 minutes
            )

            logger.info(f"✅ K3s installed on {vm_hostname}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"K3s installation failed: {e.stderr.decode()}")
            raise RuntimeError(f"Failed to install k3s: {e}")
        except subprocess.TimeoutExpired:
            logger.error("K3s installation timeout")
            raise RuntimeError("K3s installation timeout")
