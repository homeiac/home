#!/usr/bin/env python3
"""
Proxmox Cluster Management - Config-driven node operations.

Handles procedural cluster operations that cannot be managed declaratively:
- Removing nodes from cluster (required before reinstall rejoin)
- Adding nodes to cluster (after reinstall)
- Configuring GPU passthrough on hosts
- Updating certificates across nodes

Configuration: config/cluster.yaml

These operations are intentionally NOT in Crossplane because:
1. They are procedural with strict ordering requirements
2. They involve multi-node coordination
3. They have side effects (certificate distribution, kernel changes)
4. They are one-time operations, not continuous reconciliation

References:
- https://forum.proxmox.com/threads/how-to-re-join-same-node-to-the-cluster-proxmox-8.138448/
- https://pve.proxmox.com/wiki/Cluster_Manager
"""

import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Default config path relative to homelab package
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "cluster.yaml"


class ClusterOperationError(Exception):
    """Raised when a cluster operation fails."""

    pass


class NodeState(Enum):
    """Possible states of a cluster node."""

    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"
    NOT_IN_CLUSTER = "not_in_cluster"


@dataclass
class GPUPassthroughConfig:
    """GPU passthrough configuration for a node."""

    enabled: bool = False
    gpu_type: str = ""
    gpu_ids: str = ""
    kernel_modules: List[str] = field(default_factory=list)
    grub_cmdline: str = ""
    blacklist_drivers: List[str] = field(default_factory=list)


@dataclass
class StorageConfig:
    """Storage configuration for a node."""

    name: str
    type: str
    pool: str = ""
    path: str = ""
    content: List[str] = field(default_factory=list)


@dataclass
class NodeConfig:
    """Configuration for a Proxmox node."""

    name: str
    ip: str
    fqdn: str
    role: str = "compute"
    enabled: bool = True
    gpu_passthrough: GPUPassthroughConfig = field(
        default_factory=GPUPassthroughConfig
    )
    storage: List[StorageConfig] = field(default_factory=list)


@dataclass
class ClusterConfig:
    """Complete cluster configuration."""

    name: str
    primary_node: str
    nodes: List[NodeConfig]
    version: str = "1.0"

    @classmethod
    def from_yaml(cls, config_path: Path) -> "ClusterConfig":
        """Load cluster configuration from YAML file."""
        with open(config_path) as f:
            data = yaml.safe_load(f)

        cluster_data = data.get("cluster", {})
        nodes_data = data.get("nodes", [])

        nodes = []
        for node_data in nodes_data:
            gpu_data = node_data.get("gpu_passthrough", {})
            gpu_config = GPUPassthroughConfig(
                enabled=gpu_data.get("enabled", False),
                gpu_type=gpu_data.get("gpu_type", ""),
                gpu_ids=gpu_data.get("gpu_ids", ""),
                kernel_modules=gpu_data.get("kernel_modules", []),
                grub_cmdline=gpu_data.get("grub_cmdline", ""),
                blacklist_drivers=gpu_data.get("blacklist_drivers", []),
            )

            storage_configs = []
            for storage_data in node_data.get("storage", []):
                storage_configs.append(
                    StorageConfig(
                        name=storage_data.get("name", ""),
                        type=storage_data.get("type", ""),
                        pool=storage_data.get("pool", ""),
                        path=storage_data.get("path", ""),
                        content=storage_data.get("content", []),
                    )
                )

            nodes.append(
                NodeConfig(
                    name=node_data.get("name", ""),
                    ip=node_data.get("ip", ""),
                    fqdn=node_data.get("fqdn", ""),
                    role=node_data.get("role", "compute"),
                    enabled=node_data.get("enabled", True),
                    gpu_passthrough=gpu_config,
                    storage=storage_configs,
                )
            )

        return cls(
            name=cluster_data.get("name", "homelab"),
            primary_node=cluster_data.get("primary_node", ""),
            nodes=nodes,
            version=data.get("metadata", {}).get("version", "1.0"),
        )

    def get_node(self, name: str) -> Optional[NodeConfig]:
        """Get node config by name."""
        for node in self.nodes:
            if node.name == name:
                return node
        return None

    def get_primary_node(self) -> Optional[NodeConfig]:
        """Get the primary node config."""
        return self.get_node(self.primary_node)


@dataclass
class ClusterStatus:
    """Current cluster status from pvecm."""

    name: str
    nodes: List[Dict[str, Any]]
    quorate: bool
    expected_votes: int
    total_votes: int


class ClusterManager:
    """
    Config-driven Proxmox cluster manager.

    All operations are driven by config/cluster.yaml.
    Executes operations via SSH to cluster nodes.
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        ssh_user: str = "root",
        ssh_timeout: int = 30,
    ):
        """
        Initialize cluster manager.

        Args:
            config_path: Path to cluster.yaml config file
            ssh_user: SSH user for connecting to nodes
            ssh_timeout: SSH command timeout in seconds
        """
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.ssh_user = ssh_user
        self.ssh_timeout = ssh_timeout
        self._config: Optional[ClusterConfig] = None

    @property
    def config(self) -> ClusterConfig:
        """Lazy-load configuration."""
        if self._config is None:
            self._config = ClusterConfig.from_yaml(self.config_path)
        return self._config

    def reload_config(self) -> None:
        """Force reload of configuration."""
        self._config = ClusterConfig.from_yaml(self.config_path)

    def _run_ssh(
        self, host: str, command: str, check: bool = True
    ) -> subprocess.CompletedProcess:
        """Execute command on remote host via SSH."""
        ssh_cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-o", "BatchMode=yes",
            f"{self.ssh_user}@{host}",
            command,
        ]

        logger.debug(f"SSH to {host}: {command}")

        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=self.ssh_timeout,
                check=check,
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"SSH command failed on {host}: {e.stderr}")
            raise ClusterOperationError(f"SSH command failed: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise ClusterOperationError(f"SSH timeout connecting to {host}")

    def get_cluster_status(self, via_node: Optional[str] = None) -> ClusterStatus:
        """
        Get current cluster status.

        Args:
            via_node: Node name to query from (uses primary_node if not specified)
        """
        node_name = via_node or self.config.primary_node
        node = self.config.get_node(node_name)
        if not node:
            raise ClusterOperationError(f"Node '{node_name}' not found in config")

        host = node.fqdn
        logger.info(f"Getting cluster status via {host}")

        result = self._run_ssh(host, "pvecm status", check=False)

        if result.returncode != 0:
            if "no cluster defined" in result.stderr.lower():
                return ClusterStatus(
                    name="", nodes=[], quorate=False, expected_votes=0, total_votes=0
                )
            raise ClusterOperationError(f"Failed to get cluster status: {result.stderr}")

        lines = result.stdout.strip().split("\n")
        cluster_name = ""
        quorate = False
        expected_votes = 0

        for line in lines:
            if "Name:" in line and "Cluster" not in line:
                cluster_name = line.split(":")[-1].strip()
            if "Quorate:" in line:
                quorate = "Yes" in line
            if "Expected votes:" in line:
                expected_votes = int(line.split(":")[-1].strip())

        # Get node list
        nodes_result = self._run_ssh(host, "pvecm nodes", check=False)
        nodes = []
        total_votes = 0

        if nodes_result.returncode == 0:
            for line in nodes_result.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 3 and parts[0].isdigit():
                    node_id = int(parts[0])
                    votes = int(parts[1])
                    name = parts[2]
                    total_votes += votes
                    nodes.append({
                        "name": name,
                        "node_id": node_id,
                        "votes": votes,
                        "is_local": "(local)" in line,
                    })

        return ClusterStatus(
            name=cluster_name,
            nodes=nodes,
            quorate=quorate,
            expected_votes=expected_votes,
            total_votes=total_votes,
        )

    def node_in_cluster(self, node_name: str) -> bool:
        """Check if node exists in cluster."""
        status = self.get_cluster_status()
        return any(n["name"] == node_name for n in status.nodes)

    def remove_node(self, node_name: str, force: bool = False) -> Dict[str, Any]:
        """
        Remove a node from the cluster.

        Uses primary_node from config to execute the operation.
        """
        primary = self.config.get_primary_node()
        if not primary:
            raise ClusterOperationError("No primary node configured")

        logger.info(f"Removing node '{node_name}' via {primary.fqdn}")

        if not self.node_in_cluster(node_name):
            return {"status": "skipped", "message": f"Node '{node_name}' not in cluster"}

        cmd = f"pvecm delnode {node_name}"
        if force:
            cmd = f"pvecm delnode {node_name} 2>/dev/null || pvecm delnode {node_name}"

        try:
            self._run_ssh(primary.fqdn, cmd)
        except ClusterOperationError as e:
            if "still online" in str(e).lower():
                raise ClusterOperationError(
                    f"Cannot remove '{node_name}': node is still online"
                )
            raise

        # Clean up node directory
        cleanup_cmd = f"rm -rf /etc/pve/nodes/{node_name}"
        try:
            self._run_ssh(primary.fqdn, cleanup_cmd)
        except ClusterOperationError:
            logger.warning(f"Could not clean up /etc/pve/nodes/{node_name}")

        return {"status": "success", "message": f"Node '{node_name}' removed"}

    def prepare_node_for_join(self, node_name: str) -> Dict[str, Any]:
        """Prepare a fresh node to join cluster."""
        node = self.config.get_node(node_name)
        if not node:
            raise ClusterOperationError(f"Node '{node_name}' not in config")

        logger.info(f"Preparing {node.fqdn} for cluster join")

        commands = [
            "systemctl stop pve-cluster",
            "systemctl stop corosync",
            "pmxcfs -l",
            "rm -f /etc/pve/corosync.conf",
            "rm -rf /etc/corosync/*",
            "rm -rf /var/lib/corosync/*",
            "killall pmxcfs 2>/dev/null || true",
            "systemctl start pve-cluster",
        ]

        for cmd in commands:
            try:
                self._run_ssh(node.fqdn, cmd, check=False)
            except ClusterOperationError:
                pass  # Some commands may fail, that's OK

        return {"status": "success", "message": f"Node {node_name} prepared"}

    def join_node(self, node_name: str) -> Dict[str, Any]:
        """Join a node to the cluster using primary_node."""
        node = self.config.get_node(node_name)
        primary = self.config.get_primary_node()

        if not node:
            raise ClusterOperationError(f"Node '{node_name}' not in config")
        if not primary:
            raise ClusterOperationError("No primary node configured")

        logger.info(f"Joining {node.fqdn} to cluster via {primary.fqdn}")

        # Join command runs on the NEW node
        # --use_ssh allows non-interactive join using SSH keys
        join_cmd = f"pvecm add {primary.fqdn} --use_ssh"

        try:
            self._run_ssh(node.fqdn, join_cmd)
        except ClusterOperationError as e:
            raise ClusterOperationError(f"Failed to join cluster: {e}")

        # Update certificates
        try:
            self._run_ssh(node.fqdn, "pvecm updatecerts")
        except ClusterOperationError:
            logger.warning("Could not update certificates")

        return {"status": "success", "message": f"Node {node_name} joined cluster"}

    def configure_gpu_passthrough(self, node_name: str) -> Dict[str, Any]:
        """
        Configure GPU passthrough on a node based on config.

        This modifies:
        - /etc/default/grub (IOMMU flags)
        - /etc/modules (VFIO modules)
        - /etc/modprobe.d/blacklist-gpu.conf (driver blacklist)
        - /etc/modprobe.d/vfio.conf (GPU binding)
        """
        node = self.config.get_node(node_name)
        if not node:
            raise ClusterOperationError(f"Node '{node_name}' not in config")

        gpu = node.gpu_passthrough
        if not gpu.enabled:
            return {"status": "skipped", "message": "GPU passthrough not enabled"}

        logger.info(f"Configuring GPU passthrough on {node.fqdn}")
        changes = []

        # 1. Update GRUB
        grub_cmd = f"""
            if ! grep -q '{gpu.grub_cmdline}' /etc/default/grub; then
                sed -i 's/quiet/quiet {gpu.grub_cmdline}/' /etc/default/grub
                update-grub
                echo "GRUB updated"
            else
                echo "GRUB already configured"
            fi
        """
        result = self._run_ssh(node.fqdn, grub_cmd, check=False)
        changes.append(f"GRUB: {result.stdout.strip()}")

        # 2. Load VFIO modules
        modules_content = "\n".join(gpu.kernel_modules)
        modules_cmd = f"""
            echo '{modules_content}' > /etc/modules-load.d/vfio.conf
            echo "Modules configured"
        """
        self._run_ssh(node.fqdn, modules_cmd, check=False)
        changes.append("Modules: configured")

        # 3. Blacklist drivers
        blacklist_content = "\n".join(
            [f"blacklist {driver}" for driver in gpu.blacklist_drivers]
        )
        blacklist_cmd = f"""
            echo '{blacklist_content}' > /etc/modprobe.d/blacklist-gpu.conf
            echo "Blacklist configured"
        """
        self._run_ssh(node.fqdn, blacklist_cmd, check=False)
        changes.append("Blacklist: configured")

        # 4. VFIO PCI binding
        vfio_cmd = f"""
            echo 'options vfio-pci ids={gpu.gpu_ids} disable_vga=1' > /etc/modprobe.d/vfio.conf
            update-initramfs -u
            echo "VFIO configured"
        """
        self._run_ssh(node.fqdn, vfio_cmd, check=False)
        changes.append("VFIO: configured")

        return {
            "status": "success",
            "message": f"GPU passthrough configured on {node_name}",
            "changes": changes,
            "reboot_required": True,
        }

    def rejoin_node(self, node_name: str) -> Dict[str, Any]:
        """
        Complete workflow to rejoin a reinstalled node.

        Steps:
        1. Remove old node entry from cluster
        2. Prepare new node
        3. Join cluster
        4. Configure GPU passthrough (if enabled)
        """
        logger.info(f"=== Rejoining reinstalled node: {node_name} ===")
        results = []

        # Step 1: Remove old entry
        logger.info("Step 1: Removing old node entry...")
        remove_result = self.remove_node(node_name, force=True)
        results.append(("remove_old_entry", remove_result))

        # Step 2: Prepare node
        logger.info("Step 2: Preparing node...")
        prep_result = self.prepare_node_for_join(node_name)
        results.append(("prepare_node", prep_result))

        # Step 3: Join cluster
        logger.info("Step 3: Joining cluster...")
        join_result = self.join_node(node_name)
        results.append(("join_cluster", join_result))

        # Step 4: Configure GPU (if enabled)
        node = self.config.get_node(node_name)
        if node and node.gpu_passthrough.enabled:
            logger.info("Step 4: Configuring GPU passthrough...")
            gpu_result = self.configure_gpu_passthrough(node_name)
            results.append(("gpu_passthrough", gpu_result))

        logger.info(f"=== Rejoin complete for {node_name} ===")
        return {
            "status": "success",
            "message": f"Node {node_name} successfully rejoined",
            "results": results,
        }

    def apply(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Apply cluster configuration - ensure all nodes are in cluster.

        This is idempotent - only makes changes if needed.
        """
        logger.info("Applying cluster configuration...")
        results = []

        current_status = self.get_cluster_status()
        current_nodes = {n["name"] for n in current_status.nodes}

        for node in self.config.nodes:
            if not node.enabled:
                logger.info(f"Skipping disabled node: {node.name}")
                continue

            if node.name in current_nodes:
                logger.info(f"Node {node.name} already in cluster")
                results.append({
                    "node": node.name,
                    "action": "none",
                    "message": "Already in cluster",
                })
            else:
                logger.info(f"Node {node.name} needs to join cluster")
                if dry_run:
                    results.append({
                        "node": node.name,
                        "action": "would_join",
                        "message": "Would join cluster (dry-run)",
                    })
                else:
                    try:
                        join_result = self.rejoin_node(node.name)
                        results.append({
                            "node": node.name,
                            "action": "joined",
                            "message": join_result["message"],
                        })
                    except ClusterOperationError as e:
                        results.append({
                            "node": node.name,
                            "action": "failed",
                            "message": str(e),
                        })

        return {
            "status": "success",
            "dry_run": dry_run,
            "results": results,
        }


def main() -> None:
    """CLI entry point for cluster operations."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: cluster_manager.py <command> [args]")
        print("Commands:")
        print("  status                    - Show cluster status")
        print("  remove <node_name>        - Remove node from cluster")
        print("  rejoin <node_name>        - Rejoin reinstalled node")
        print("  gpu <node_name>           - Configure GPU passthrough")
        print("  apply [--dry-run]         - Apply cluster config")
        sys.exit(1)

    manager = ClusterManager()
    command = sys.argv[1]

    if command == "status":
        status = manager.get_cluster_status()
        print(f"Cluster: {status.name}")
        print(f"Quorate: {status.quorate}")
        print(f"Votes: {status.total_votes}/{status.expected_votes}")
        print("Nodes:")
        for node in status.nodes:
            local = " (local)" if node.get("is_local") else ""
            print(f"  - {node['name']} (ID: {node['node_id']}){local}")

    elif command == "remove":
        if len(sys.argv) < 3:
            print("Usage: cluster_manager.py remove <node_name>")
            sys.exit(1)
        result = manager.remove_node(sys.argv[2])
        print(f"Result: {result}")

    elif command == "rejoin":
        if len(sys.argv) < 3:
            print("Usage: cluster_manager.py rejoin <node_name>")
            sys.exit(1)
        result = manager.rejoin_node(sys.argv[2])
        print(f"Result: {result}")

    elif command == "gpu":
        if len(sys.argv) < 3:
            print("Usage: cluster_manager.py gpu <node_name>")
            sys.exit(1)
        result = manager.configure_gpu_passthrough(sys.argv[2])
        print(f"Result: {result}")

    elif command == "apply":
        dry_run = "--dry-run" in sys.argv
        result = manager.apply(dry_run=dry_run)
        print(f"Result: {result}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
