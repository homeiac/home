"""K3s cluster management for VM provisioning and kube-vip configuration."""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Default config path relative to homelab package
DEFAULT_K3S_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "k3s.yaml"


class K3sOperationError(Exception):
    """Raised when a K3s operation fails."""
    pass


@dataclass
class ControlPlaneNode:
    """Configuration for a K3s control plane node."""
    name: str
    proxmox_host: str
    vmid: str
    ip: str
    is_primary: bool = False
    gpu_enabled: bool = False


@dataclass
class KubeVipConfig:
    """kube-vip configuration."""
    enabled: bool = True
    version: str = "v0.8.7"
    mode: str = "arp"
    leader_election: bool = True


@dataclass
class K3sClusterConfig:
    """Complete K3s cluster configuration."""
    name: str
    control_plane_vip: str
    vip_interface: str
    api_port: int
    kube_vip: KubeVipConfig
    control_plane_nodes: List[ControlPlaneNode]
    tls_san: List[str]
    server_config: Dict[str, Any]
    version: str = "1.0"

    @classmethod
    def from_yaml(cls, config_path: Path) -> "K3sClusterConfig":
        """Load K3s cluster configuration from YAML file."""
        with open(config_path) as f:
            data = yaml.safe_load(f)

        cluster_data = data.get("cluster", {})
        kube_vip_data = data.get("kube_vip", {})
        nodes_data = data.get("control_plane_nodes", [])

        kube_vip = KubeVipConfig(
            enabled=kube_vip_data.get("enabled", True),
            version=kube_vip_data.get("version", "v0.8.7"),
            mode=kube_vip_data.get("mode", "arp"),
            leader_election=kube_vip_data.get("leader_election", True),
        )

        nodes = []
        for node_data in nodes_data:
            nodes.append(
                ControlPlaneNode(
                    name=node_data.get("name", ""),
                    proxmox_host=node_data.get("proxmox_host", ""),
                    vmid=str(node_data.get("vmid", "")),
                    ip=node_data.get("ip", ""),
                    is_primary=node_data.get("is_primary", False),
                    gpu_enabled=node_data.get("gpu_enabled", False),
                )
            )

        return cls(
            name=cluster_data.get("name", "homelab-k3s"),
            control_plane_vip=cluster_data.get("control_plane_vip", ""),
            vip_interface=cluster_data.get("vip_interface", "eth0"),
            api_port=cluster_data.get("api_port", 6443),
            kube_vip=kube_vip,
            control_plane_nodes=nodes,
            tls_san=data.get("tls_san", []),
            server_config=data.get("server_config", {}),
            version=data.get("metadata", {}).get("version", "1.0"),
        )

    def get_node(self, name: str) -> Optional[ControlPlaneNode]:
        """Get node config by name."""
        for node in self.control_plane_nodes:
            if node.name == name:
                return node
        return None

    def get_primary_node(self) -> Optional[ControlPlaneNode]:
        """Get the primary node config."""
        for node in self.control_plane_nodes:
            if node.is_primary:
                return node
        return self.control_plane_nodes[0] if self.control_plane_nodes else None


class K3sManager:
    """
    Config-driven K3s cluster manager.

    Handles:
    - K3s installation and cluster joining
    - TLS-SAN configuration for kube-vip
    - API server certificate rotation
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        ssh_user: str = "root",
        ssh_timeout: int = 60,
    ):
        """
        Initialize K3s manager.

        Args:
            config_path: Path to k3s.yaml config file
            ssh_user: SSH user for connecting to Proxmox hosts
            ssh_timeout: SSH command timeout in seconds
        """
        self.config_path = config_path or DEFAULT_K3S_CONFIG_PATH
        self.ssh_user = ssh_user
        self.ssh_timeout = ssh_timeout
        self._config: Optional[K3sClusterConfig] = None

    @property
    def config(self) -> K3sClusterConfig:
        """Lazy-load configuration."""
        if self._config is None:
            self._config = K3sClusterConfig.from_yaml(self.config_path)
        return self._config

    def reload_config(self) -> None:
        """Force reload of configuration."""
        self._config = K3sClusterConfig.from_yaml(self.config_path)

    def _run_qm_exec(
        self, proxmox_host: str, vmid: str, command: str, check: bool = True
    ) -> subprocess.CompletedProcess:
        """Execute command inside VM via qm guest exec."""
        # Escape quotes in command for nested execution
        escaped_cmd = command.replace("'", "'\"'\"'")

        ssh_cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            f"{self.ssh_user}@{proxmox_host}.maas",
            f"qm guest exec {vmid} -- bash -c '{escaped_cmd}'",
        ]

        logger.debug(f"qm exec on {proxmox_host}/{vmid}: {command}")

        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=self.ssh_timeout,
            )

            # Parse qm guest exec JSON output
            if result.returncode == 0 and result.stdout:
                try:
                    output = json.loads(result.stdout)
                    if output.get("exitcode", 0) != 0 and check:
                        raise K3sOperationError(
                            f"Command failed with exit code {output.get('exitcode')}: "
                            f"{output.get('err-data', '')}"
                        )
                    # Create a synthetic CompletedProcess with the actual output
                    return subprocess.CompletedProcess(
                        args=ssh_cmd,
                        returncode=output.get("exitcode", 0),
                        stdout=output.get("out-data", ""),
                        stderr=output.get("err-data", ""),
                    )
                except json.JSONDecodeError:
                    pass

            return result

        except subprocess.TimeoutExpired:
            raise K3sOperationError(f"Timeout executing command on {proxmox_host}/{vmid}")

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
            logger.info(f"Retrieved k3s token from {existing_node_ip}")
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
                logger.info(f"Node {node_name} in cluster")
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

        logger.info(f"Installing k3s on {vm_hostname}")

        try:
            subprocess.run(
                ["ssh", "-o", "StrictHostKeyChecking=no", f"ubuntu@{vm_hostname}", install_cmd],
                check=True,
                capture_output=True,
                timeout=300,  # 5 minutes
            )

            logger.info(f"K3s installed on {vm_hostname}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"K3s installation failed: {e.stderr.decode()}")
            raise RuntimeError(f"Failed to install k3s: {e}")
        except subprocess.TimeoutExpired:
            logger.error("K3s installation timeout")
            raise RuntimeError("K3s installation timeout")

    def get_current_tls_san(self, node: ControlPlaneNode) -> List[str]:
        """Get current TLS-SAN entries from a node's K3s config."""
        try:
            result = self._run_qm_exec(
                node.proxmox_host,
                node.vmid,
                "cat /etc/rancher/k3s/config.yaml 2>/dev/null || echo 'no-config'",
                check=False,
            )

            if "no-config" in result.stdout or not result.stdout.strip():
                return []

            config = yaml.safe_load(result.stdout)
            return config.get("tls-san", []) if config else []

        except Exception as e:
            logger.warning(f"Could not read TLS-SAN from {node.name}: {e}")
            return []

    def configure_tls_san(
        self, node_name: Optional[str] = None, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Configure TLS-SAN on control plane nodes for kube-vip.

        This updates /etc/rancher/k3s/config.yaml with the required tls-san entries,
        including the control plane VIP.

        Args:
            node_name: Specific node to configure, or None for all nodes
            dry_run: If True, only show what would be changed

        Returns:
            Dict with status and changes per node
        """
        results = {"status": "success", "nodes": {}}

        nodes_to_configure = (
            [self.config.get_node(node_name)] if node_name
            else self.config.control_plane_nodes
        )

        # Build the desired config
        desired_tls_san = list(self.config.tls_san)
        if self.config.control_plane_vip not in desired_tls_san:
            desired_tls_san.insert(0, self.config.control_plane_vip)

        desired_config = {
            "tls-san": desired_tls_san,
        }

        # Add server_config options (like disable: [servicelb])
        if self.config.server_config.get("disable"):
            desired_config["disable"] = self.config.server_config["disable"]
        if self.config.server_config.get("write_kubeconfig_mode"):
            desired_config["write-kubeconfig-mode"] = self.config.server_config["write_kubeconfig_mode"]

        for node in nodes_to_configure:
            if node is None:
                continue

            logger.info(f"Configuring TLS-SAN on {node.name}")

            current_san = self.get_current_tls_san(node)
            # Only update if VIP is missing - don't re-rotate for other SAN differences
            vip_in_current = self.config.control_plane_vip in current_san
            needs_update = not vip_in_current

            node_result = {
                "current_tls_san": current_san,
                "desired_tls_san": desired_tls_san,
                "needs_update": needs_update,
            }

            if not needs_update:
                logger.info(f"  {node.name}: TLS-SAN already configured correctly")
                node_result["action"] = "none"

            elif dry_run:
                logger.info(f"  {node.name}: Would update TLS-SAN (dry-run)")
                node_result["action"] = "would_update"

            else:
                # Write the new config
                config_yaml = yaml.dump(desired_config, default_flow_style=False)

                # Create config directory and write file
                write_cmd = f"""
                    mkdir -p /etc/rancher/k3s
                    cat > /etc/rancher/k3s/config.yaml << 'EOFCONFIG'
{config_yaml}EOFCONFIG
                    echo 'Config written'
                """

                try:
                    result = self._run_qm_exec(
                        node.proxmox_host,
                        node.vmid,
                        write_cmd,
                        check=True
                    )
                    logger.info(f"  {node.name}: TLS-SAN configured")
                    node_result["action"] = "updated"
                    node_result["requires_restart"] = True

                except K3sOperationError as e:
                    logger.error(f"  {node.name}: Failed to configure TLS-SAN: {e}")
                    node_result["action"] = "failed"
                    node_result["error"] = str(e)
                    results["status"] = "partial"

            results["nodes"][node.name] = node_result

        return results

    def rotate_api_certificates(
        self, node_name: Optional[str] = None, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Rotate API server certificates to include new TLS-SAN entries.

        This deletes the current serving cert and restarts K3s, which
        regenerates the cert with current config.yaml TLS-SAN entries.

        WARNING: Do this one node at a time to avoid cluster downtime!

        Args:
            node_name: Specific node to rotate, or None for all (sequential)
            dry_run: If True, only show what would be done

        Returns:
            Dict with status and results per node
        """
        results = {"status": "success", "nodes": {}}

        nodes_to_rotate = (
            [self.config.get_node(node_name)] if node_name
            else self.config.control_plane_nodes
        )

        for node in nodes_to_rotate:
            if node is None:
                continue

            logger.info(f"Rotating API certificate on {node.name}")

            node_result = {}

            if dry_run:
                logger.info(f"  {node.name}: Would rotate certificate (dry-run)")
                node_result["action"] = "would_rotate"

            else:
                # Delete the serving cert and restart K3s
                rotate_cmd = """
                    rm -f /var/lib/rancher/k3s/server/tls/serving-kube-apiserver.crt
                    rm -f /var/lib/rancher/k3s/server/tls/serving-kube-apiserver.key
                    systemctl restart k3s
                    echo 'Certificate rotated, K3s restarting'
                """

                try:
                    result = self._run_qm_exec(
                        node.proxmox_host,
                        node.vmid,
                        rotate_cmd,
                        check=True
                    )
                    logger.info(f"  {node.name}: Certificate rotated, waiting for K3s...")
                    node_result["action"] = "rotated"

                    # Wait for K3s to come back up
                    import time
                    time.sleep(10)

                    # Verify new cert has VIP in SAN
                    verify_cmd = """
                        openssl x509 -in /var/lib/rancher/k3s/server/tls/serving-kube-apiserver.crt -noout -text 2>/dev/null | grep -A1 'Subject Alternative Name' || echo 'Cert not ready'
                    """
                    verify_result = self._run_qm_exec(
                        node.proxmox_host,
                        node.vmid,
                        verify_cmd,
                        check=False
                    )
                    node_result["new_san"] = verify_result.stdout.strip()

                    if self.config.control_plane_vip in verify_result.stdout:
                        logger.info(f"  {node.name}: VIP {self.config.control_plane_vip} confirmed in certificate")
                        node_result["vip_in_cert"] = True
                    else:
                        logger.warning(f"  {node.name}: VIP not found in certificate yet")
                        node_result["vip_in_cert"] = False

                except K3sOperationError as e:
                    logger.error(f"  {node.name}: Failed to rotate certificate: {e}")
                    node_result["action"] = "failed"
                    node_result["error"] = str(e)
                    results["status"] = "partial"

            results["nodes"][node.name] = node_result

        return results

    def prepare_for_kube_vip(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Complete workflow to prepare cluster for kube-vip.

        Steps:
        1. Configure TLS-SAN on all control plane nodes
        2. Rotate certificates one node at a time
        3. Verify VIP is in all certificates

        Args:
            dry_run: If True, only show what would be done

        Returns:
            Dict with complete workflow results
        """
        logger.info("=== Preparing cluster for kube-vip ===")
        logger.info(f"Control plane VIP: {self.config.control_plane_vip}")

        workflow_results = {
            "vip": self.config.control_plane_vip,
            "steps": {},
        }

        # Step 1: Configure TLS-SAN
        logger.info("\nStep 1: Configuring TLS-SAN on all nodes...")
        san_results = self.configure_tls_san(dry_run=dry_run)
        workflow_results["steps"]["configure_tls_san"] = san_results

        if dry_run:
            logger.info("\nDry run complete. No changes made.")
            workflow_results["status"] = "dry_run"
            return workflow_results

        # Check if any node needs certificate rotation
        needs_rotation = any(
            node_info.get("action") == "updated"
            for node_info in san_results.get("nodes", {}).values()
        )

        if not needs_rotation:
            logger.info("\nNo certificate rotation needed - TLS-SAN already configured.")
            workflow_results["status"] = "success"
            workflow_results["steps"]["rotate_certificates"] = {"action": "skipped"}
            return workflow_results

        # Step 2: Rotate certificates ONLY for nodes that were updated
        logger.info("\nStep 2: Rotating certificates (only for nodes that need it)...")
        rotate_results = {"nodes": {}}

        # Get list of nodes that actually need rotation
        nodes_needing_rotation = [
            node_name for node_name, node_info in san_results.get("nodes", {}).items()
            if node_info.get("action") == "updated"
        ]

        for node in self.config.control_plane_nodes:
            if node.name not in nodes_needing_rotation:
                logger.info(f"\n  Skipping {node.name} (VIP already in cert)")
                rotate_results["nodes"][node.name] = {"action": "skipped", "vip_in_cert": True}
                continue

            logger.info(f"\n  Processing {node.name}...")
            node_result = self.rotate_api_certificates(node_name=node.name)
            rotate_results["nodes"][node.name] = node_result["nodes"].get(node.name, {})

            # Wait between nodes to ensure cluster stability
            if node != self.config.control_plane_nodes[-1]:
                logger.info("  Waiting 15 seconds before next node...")
                import time
                time.sleep(15)

        workflow_results["steps"]["rotate_certificates"] = rotate_results

        # Step 3: Summary
        all_success = all(
            node_info.get("vip_in_cert", False)
            for node_info in rotate_results.get("nodes", {}).values()
        )

        if all_success:
            logger.info("\n=== Cluster ready for kube-vip! ===")
            logger.info(f"VIP {self.config.control_plane_vip} is now in all API server certificates.")
            logger.info("Next step: Deploy kube-vip via Flux")
            workflow_results["status"] = "success"
        else:
            logger.warning("\n=== Some nodes may need attention ===")
            workflow_results["status"] = "partial"

        return workflow_results

    def status(self) -> Dict[str, Any]:
        """Get current K3s cluster and kube-vip readiness status."""
        status = {
            "config": {
                "control_plane_vip": self.config.control_plane_vip,
                "kube_vip_enabled": self.config.kube_vip.enabled,
                "tls_san": self.config.tls_san,
            },
            "nodes": {},
        }

        for node in self.config.control_plane_nodes:
            node_status = {
                "ip": node.ip,
                "proxmox_host": node.proxmox_host,
                "vmid": node.vmid,
                "is_primary": node.is_primary,
            }

            # Check current TLS-SAN
            current_san = self.get_current_tls_san(node)
            node_status["current_tls_san"] = current_san
            node_status["vip_in_san"] = self.config.control_plane_vip in current_san

            status["nodes"][node.name] = node_status

        return status


def main() -> None:
    """CLI entry point for K3s operations."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)8s] %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: k3s_manager.py <command> [args]")
        print("Commands:")
        print("  status                      - Show K3s cluster and kube-vip readiness")
        print("  configure-tls-san [--dry-run] - Configure TLS-SAN on all nodes")
        print("  rotate-certs [--dry-run]    - Rotate API certificates")
        print("  prepare-kube-vip [--dry-run] - Full workflow to prepare for kube-vip")
        sys.exit(1)

    manager = K3sManager()
    command = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    if command == "status":
        status = manager.status()
        print(f"\nControl Plane VIP: {status['config']['control_plane_vip']}")
        print(f"kube-vip Enabled: {status['config']['kube_vip_enabled']}")
        print("\nNodes:")
        for name, info in status["nodes"].items():
            vip_status = "YES" if info["vip_in_san"] else "NO"
            print(f"  {name}:")
            print(f"    IP: {info['ip']}")
            print(f"    VIP in cert: {vip_status}")
            print(f"    Current TLS-SAN: {info['current_tls_san']}")

    elif command == "configure-tls-san":
        result = manager.configure_tls_san(dry_run=dry_run)
        print(f"\nResult: {json.dumps(result, indent=2)}")

    elif command == "rotate-certs":
        result = manager.rotate_api_certificates(dry_run=dry_run)
        print(f"\nResult: {json.dumps(result, indent=2)}")

    elif command == "prepare-kube-vip":
        result = manager.prepare_for_kube_vip(dry_run=dry_run)
        print(f"\nResult: {json.dumps(result, indent=2)}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
