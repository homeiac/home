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
class NetworkInterfaceConfig:
    """Network interface configuration."""

    interface: str
    ip: str = ""
    bridge: str = ""
    gateway: str = ""
    speed: int = 1000  # Mbps
    enabled: bool = True


@dataclass
class NetworkConfig:
    """Network configuration for a node."""

    primary: Optional[NetworkInterfaceConfig] = None
    secondary: Optional[NetworkInterfaceConfig] = None


@dataclass
class NodeConfig:
    """Configuration for a Proxmox node."""

    name: str
    ip: str
    fqdn: str
    role: str = "compute"
    enabled: bool = True
    network: Optional[NetworkConfig] = None
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

            # Parse network configuration
            network_config = None
            network_data = node_data.get("network", {})
            if network_data:
                primary_data = network_data.get("primary", {})
                secondary_data = network_data.get("secondary", {})

                primary_iface = None
                if primary_data:
                    primary_iface = NetworkInterfaceConfig(
                        interface=primary_data.get("interface", ""),
                        ip=primary_data.get("ip", ""),
                        bridge=primary_data.get("bridge", ""),
                        gateway=primary_data.get("gateway", ""),
                        speed=primary_data.get("speed", 1000),
                        enabled=primary_data.get("enabled", True),
                    )

                secondary_iface = None
                if secondary_data and secondary_data.get("enabled", True):
                    secondary_iface = NetworkInterfaceConfig(
                        interface=secondary_data.get("interface", ""),
                        ip=secondary_data.get("ip", ""),
                        bridge=secondary_data.get("bridge", ""),
                        gateway=secondary_data.get("gateway", ""),
                        speed=secondary_data.get("speed", 1000),
                        enabled=secondary_data.get("enabled", True),
                    )

                network_config = NetworkConfig(
                    primary=primary_iface,
                    secondary=secondary_iface,
                )

            nodes.append(
                NodeConfig(
                    name=node_data.get("name", ""),
                    ip=node_data.get("ip", ""),
                    fqdn=node_data.get("fqdn", ""),
                    role=node_data.get("role", "compute"),
                    enabled=node_data.get("enabled", True),
                    network=network_config,
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

    def setup_ssh_keys(self, node_name: str, password: Optional[str] = None) -> Dict[str, Any]:
        """
        Set up SSH key authentication to a virgin node.

        For fresh Proxmox installs that don't have SSH keys yet.
        Uses sshpass if password provided, otherwise prompts interactively.
        """
        node = self.config.get_node(node_name)
        if not node:
            raise ClusterOperationError(f"Node '{node_name}' not in config")

        logger.info(f"Setting up SSH keys for {node.fqdn}")

        # Check if SSH already works
        test_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                    f"{self.ssh_user}@{node.fqdn}", "echo ok"]
        try:
            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                logger.info(f"SSH keys already working for {node.fqdn}")
                return {"status": "skipped", "message": "SSH keys already configured"}
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass  # SSH not working, proceed with key setup

        # Get local public key - prefer id_ed25519_pve for Proxmox hosts (matches ssh_config)
        pub_key_paths = [
            Path.home() / ".ssh" / "id_ed25519_pve.pub",  # Primary for *.maas hosts
            Path.home() / ".ssh" / "id_ed25519.pub",
            Path.home() / ".ssh" / "id_rsa.pub",
        ]
        pub_key = None
        for path in pub_key_paths:
            if path.exists():
                pub_key = path.read_text().strip()
                logger.info(f"Using SSH key: {path}")
                break

        if not pub_key:
            raise ClusterOperationError("No SSH public key found in ~/.ssh/")

        if password:
            # Use sshpass for non-interactive key copy
            # Proxmox uses /etc/pve/priv/authorized_keys (symlinked from ~/.ssh/authorized_keys)
            # We add to BOTH locations to handle pre-cluster and post-cluster states
            remote_cmd = (
                f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
                # Remove symlink if it exists (virgin node won't have /etc/pve yet)
                f"rm -f ~/.ssh/authorized_keys 2>/dev/null; "
                # Add to ~/.ssh directly
                f"grep -qxF '{pub_key}' ~/.ssh/authorized_keys 2>/dev/null || "
                f"echo '{pub_key}' >> ~/.ssh/authorized_keys && "
                f"chmod 600 ~/.ssh/authorized_keys && "
                # Also add to /etc/pve/priv if it exists (for post-cluster)
                f"if [ -d /etc/pve/priv ]; then "
                f"grep -qxF '{pub_key}' /etc/pve/priv/authorized_keys 2>/dev/null || "
                f"echo '{pub_key}' >> /etc/pve/priv/authorized_keys; fi"
            )
            ssh_copy_cmd = [
                "sshpass", "-p", password,
                "ssh", "-o", "StrictHostKeyChecking=no",
                f"{self.ssh_user}@{node.fqdn}",
                remote_cmd
            ]
            logger.debug(f"Running: sshpass -p *** ssh ... {remote_cmd[:50]}...")
            try:
                result = subprocess.run(ssh_copy_cmd, capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    logger.error(f"sshpass stderr: {result.stderr}")
                    raise ClusterOperationError(f"Failed to copy SSH key: {result.stderr}")
                logger.info(f"SSH key copied to {node.fqdn}")
            except FileNotFoundError:
                raise ClusterOperationError("sshpass not installed. Run: brew install hudochenkov/sshpass/sshpass")
        else:
            # Interactive ssh-copy-id
            logger.info("Running ssh-copy-id interactively (will prompt for password)")
            ssh_copy_cmd = ["ssh-copy-id", "-o", "StrictHostKeyChecking=no",
                           f"{self.ssh_user}@{node.fqdn}"]
            try:
                # Run interactively - don't capture output
                result = subprocess.run(ssh_copy_cmd, timeout=60)
                if result.returncode != 0:
                    raise ClusterOperationError("ssh-copy-id failed")
            except subprocess.TimeoutExpired:
                raise ClusterOperationError("ssh-copy-id timed out")

        # Verify SSH works now
        try:
            self._run_ssh(node.fqdn, "echo 'SSH key setup successful'")
        except ClusterOperationError:
            raise ClusterOperationError("SSH key setup failed - still cannot connect")

        return {"status": "success", "message": f"SSH keys configured for {node.fqdn}"}

    def prepare_node_for_join(self, node_name: str, password: Optional[str] = None) -> Dict[str, Any]:
        """Prepare a fresh node to join cluster (with password for sshpass fallback)."""
        node = self.config.get_node(node_name)
        if not node:
            raise ClusterOperationError(f"Node '{node_name}' not in config")

        logger.info(f"Preparing {node.fqdn} for cluster join")

        # Single script to fully reset cluster state
        # This is destructive - removes ALL cluster config including cached nodes
        reset_script = """
            set -e
            systemctl stop pve-cluster corosync 2>/dev/null || true
            killall pmxcfs 2>/dev/null || true
            sleep 1

            # Remove cluster database and cache
            rm -rf /var/lib/pve-cluster/*
            rm -rf /etc/corosync/*
            rm -rf /var/lib/corosync/*

            # Start fresh pmxcfs in local mode to access /etc/pve
            pmxcfs -l &
            sleep 2

            # Clean up /etc/pve which is now a fresh local mount
            rm -f /etc/pve/corosync.conf 2>/dev/null || true
            rm -rf /etc/pve/nodes/* 2>/dev/null || true
            rm -rf /etc/pve/qemu-server/* 2>/dev/null || true
            rm -rf /etc/pve/lxc/* 2>/dev/null || true

            # Stop local-mode pmxcfs
            killall pmxcfs 2>/dev/null || true
            sleep 1

            # Start pve-cluster properly
            systemctl start pve-cluster

            # Wait for pve-cluster to be ready
            for i in 1 2 3 4 5 6 7 8 9 10; do
                if pvesh get /version >/dev/null 2>&1; then
                    echo "pve-cluster ready"
                    exit 0
                fi
                sleep 1
            done
            echo "pve-cluster not ready after 10s"
            exit 1
        """
        commands = [reset_script]

        for cmd in commands:
            try:
                self._run_ssh(node.fqdn, cmd, check=False)
            except ClusterOperationError:
                # Try with sshpass if SSH key auth fails
                if password:
                    try:
                        sshpass_cmd = [
                            "sshpass", "-p", password,
                            "ssh", "-o", "StrictHostKeyChecking=no",
                            f"{self.ssh_user}@{node.fqdn}",
                            cmd
                        ]
                        subprocess.run(sshpass_cmd, capture_output=True, timeout=30, check=False)
                    except Exception:
                        pass

        return {"status": "success", "message": f"Node {node_name} prepared"}

    def setup_inter_node_ssh(self, node_name: str) -> Dict[str, Any]:
        """
        Set up SSH keys between the new node and primary node.

        pvecm add --use_ssh requires the new node to SSH to the primary node.
        This copies the new node's public key to the primary's authorized_keys.
        """
        node = self.config.get_node(node_name)
        primary = self.config.get_primary_node()

        if not node:
            raise ClusterOperationError(f"Node '{node_name}' not in config")
        if not primary:
            raise ClusterOperationError("No primary node configured")

        logger.info(f"Setting up inter-node SSH: {node.name} -> {primary.name}")

        # Get the new node's public key
        try:
            result = self._run_ssh(node.fqdn, "cat /root/.ssh/id_rsa.pub")
            new_node_pubkey = result.stdout.strip()
        except ClusterOperationError:
            raise ClusterOperationError(f"Could not get public key from {node.name}")

        if not new_node_pubkey:
            raise ClusterOperationError(f"Empty public key from {node.name}")

        # Add to primary node's /etc/pve/priv/authorized_keys (cluster-shared)
        add_key_cmd = (
            f"grep -qxF '{new_node_pubkey}' /etc/pve/priv/authorized_keys 2>/dev/null || "
            f"echo '{new_node_pubkey}' >> /etc/pve/priv/authorized_keys"
        )
        try:
            self._run_ssh(primary.fqdn, add_key_cmd)
            logger.info(f"Added {node.name} SSH key to {primary.name}")
        except ClusterOperationError as e:
            raise ClusterOperationError(f"Could not add key to {primary.name}: {e}")

        return {"status": "success", "message": f"SSH key from {node.name} added to {primary.name}"}

    def join_node(self, node_name: str) -> Dict[str, Any]:
        """Join a node to the cluster using primary_node."""
        node = self.config.get_node(node_name)
        primary = self.config.get_primary_node()

        if not node:
            raise ClusterOperationError(f"Node '{node_name}' not in config")
        if not primary:
            raise ClusterOperationError("No primary node configured")

        # First set up inter-node SSH (new node -> primary)
        self.setup_inter_node_ssh(node_name)

        logger.info(f"Joining {node.fqdn} to cluster via {primary.fqdn}")

        # Join command runs on the NEW node
        # --use_ssh allows non-interactive join using SSH keys
        # Capture both stdout and stderr for debugging
        join_cmd = f"pvecm add {primary.fqdn} --use_ssh 2>&1"

        try:
            result = self._run_ssh(node.fqdn, join_cmd, check=False)
            if result.returncode != 0:
                logger.error(f"pvecm add failed with exit code {result.returncode}")
                logger.error(f"pvecm add output: {result.stdout}")
                if "virtual guests" in result.stdout:
                    raise ClusterOperationError(
                        f"Node has leftover guest config - prepare_node_for_join didn't clean up: {result.stdout}"
                    )
                elif "ssh ID" in result.stdout:
                    raise ClusterOperationError(
                        f"SSH key not set up between nodes: {result.stdout}"
                    )
                else:
                    raise ClusterOperationError(f"pvecm add failed: {result.stdout}")
            logger.info(f"pvecm add output: {result.stdout[:200]}...")
        except ClusterOperationError:
            raise
        except Exception as e:
            raise ClusterOperationError(f"Failed to join cluster: {e}")

        # Update certificates
        try:
            self._run_ssh(node.fqdn, "pvecm updatecerts")
        except ClusterOperationError:
            logger.warning("Could not update certificates")

        return {"status": "success", "message": f"Node {node_name} joined cluster"}

    def is_gpu_passthrough_configured(self, node_name: str) -> bool:
        """Check if GPU passthrough is already fully configured."""
        node = self.config.get_node(node_name)
        if not node or not node.gpu_passthrough.enabled:
            return True  # Nothing to configure

        gpu = node.gpu_passthrough

        try:
            # Check all four configurations
            check_cmd = f"""
                grep -q '{gpu.grub_cmdline}' /etc/default/grub && \
                test -f /etc/modules-load.d/vfio.conf && \
                test -f /etc/modprobe.d/blacklist-gpu.conf && \
                grep -q '{gpu.gpu_ids}' /etc/modprobe.d/vfio.conf && \
                echo "CONFIGURED"
            """
            result = self._run_ssh(node.fqdn, check_cmd, check=False)
            return "CONFIGURED" in result.stdout
        except ClusterOperationError:
            return False

    def configure_network(self, node_name: str) -> Dict[str, Any]:
        """
        Configure network interfaces on a node based on config.

        This is IDEMPOTENT - checks if already configured and skips if so.

        Modifies:
        - /etc/network/interfaces (secondary interface only)

        Note: Primary interface is configured during Proxmox install.
        This only adds the secondary interface for fast PBS restores.
        """
        node = self.config.get_node(node_name)
        if not node:
            raise ClusterOperationError(f"Node '{node_name}' not in config")

        if not node.network or not node.network.secondary:
            return {"status": "skipped", "message": "No secondary network in config"}

        secondary = node.network.secondary
        if not secondary.enabled:
            return {"status": "skipped", "message": "Secondary network disabled in config"}

        logger.info(f"Configuring secondary network interface on {node.fqdn}")

        # Check if already configured
        check_cmd = f"grep -q '{secondary.interface}' /etc/network/interfaces && grep -q '{secondary.ip}' /etc/network/interfaces"
        result = self._run_ssh(node.fqdn, check_cmd, check=False)
        if result.returncode == 0:
            logger.info(f"Secondary network already configured on {node.fqdn}")
            return {"status": "skipped", "message": "Secondary network already configured"}

        # Configure secondary interface (static IP, no bridge, no gateway)
        config_block = f"""
iface {secondary.interface} inet static
    address {secondary.ip}
"""
        # Update /etc/network/interfaces
        update_cmd = f"""
if grep -q 'iface {secondary.interface} inet manual' /etc/network/interfaces; then
    # Replace manual with static config
    sed -i '/iface {secondary.interface} inet manual/c\\{config_block.strip()}' /etc/network/interfaces
else
    # Append if not present
    echo '{config_block}' >> /etc/network/interfaces
fi
# Bring up the interface
ip link set {secondary.interface} up
ip addr add {secondary.ip} dev {secondary.interface} 2>/dev/null || true
echo "Secondary network configured"
"""
        result = self._run_ssh(node.fqdn, update_cmd, check=False)

        return {
            "status": "success",
            "message": f"Secondary network {secondary.interface} configured on {node_name}",
            "interface": secondary.interface,
            "ip": secondary.ip,
            "speed": secondary.speed,
        }

    def configure_gpu_passthrough(self, node_name: str) -> Dict[str, Any]:
        """
        Configure GPU passthrough on a node based on config.

        This is IDEMPOTENT - checks if already configured and skips if so.

        Modifies:
        - /etc/default/grub (IOMMU flags)
        - /etc/modules-load.d/vfio.conf (VFIO modules)
        - /etc/modprobe.d/blacklist-gpu.conf (driver blacklist)
        - /etc/modprobe.d/vfio.conf (GPU binding)
        """
        node = self.config.get_node(node_name)
        if not node:
            raise ClusterOperationError(f"Node '{node_name}' not in config")

        gpu = node.gpu_passthrough
        if not gpu.enabled:
            return {"status": "skipped", "message": "GPU passthrough not enabled in config"}

        # Check if already configured
        if self.is_gpu_passthrough_configured(node_name):
            logger.info(f"GPU passthrough already configured on {node.fqdn}")
            return {"status": "skipped", "message": "GPU passthrough already configured", "reboot_required": False}

        logger.info(f"Configuring GPU passthrough on {node.fqdn}")
        changes = []

        # 1. Update GRUB (idempotent)
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

        # 2. Load VFIO modules (idempotent - writes to file)
        modules_content = "\\n".join(gpu.kernel_modules)
        modules_cmd = f"""
            EXPECTED='{modules_content}'
            if [ -f /etc/modules-load.d/vfio.conf ] && [ "$(cat /etc/modules-load.d/vfio.conf)" = "$EXPECTED" ]; then
                echo "Modules already configured"
            else
                echo '{modules_content}' > /etc/modules-load.d/vfio.conf
                echo "Modules configured"
            fi
        """
        result = self._run_ssh(node.fqdn, modules_cmd, check=False)
        changes.append(f"Modules: {result.stdout.strip()}")

        # 3. Blacklist drivers (idempotent)
        blacklist_content = "\\n".join(
            [f"blacklist {driver}" for driver in gpu.blacklist_drivers]
        )
        blacklist_cmd = f"""
            EXPECTED='{blacklist_content}'
            if [ -f /etc/modprobe.d/blacklist-gpu.conf ] && [ "$(cat /etc/modprobe.d/blacklist-gpu.conf)" = "$EXPECTED" ]; then
                echo "Blacklist already configured"
            else
                echo '{blacklist_content}' > /etc/modprobe.d/blacklist-gpu.conf
                echo "Blacklist configured"
            fi
        """
        result = self._run_ssh(node.fqdn, blacklist_cmd, check=False)
        changes.append(f"Blacklist: {result.stdout.strip()}")

        # 4. VFIO PCI binding (idempotent)
        vfio_expected = f"options vfio-pci ids={gpu.gpu_ids} disable_vga=1"
        vfio_cmd = f"""
            if [ -f /etc/modprobe.d/vfio.conf ] && grep -q '{gpu.gpu_ids}' /etc/modprobe.d/vfio.conf; then
                echo "VFIO already configured"
            else
                echo '{vfio_expected}' > /etc/modprobe.d/vfio.conf
                update-initramfs -u
                echo "VFIO configured"
            fi
        """
        result = self._run_ssh(node.fqdn, vfio_cmd, check=False)
        changes.append(f"VFIO: {result.stdout.strip()}")

        return {
            "status": "success",
            "message": f"GPU passthrough configured on {node_name}",
            "changes": changes,
            "reboot_required": True,
        }

    def is_node_healthy_in_cluster(self, node_name: str) -> bool:
        """
        Check if a node is already properly joined to the cluster.

        Returns True if node is in cluster AND can communicate with cluster.
        """
        node = self.config.get_node(node_name)
        if not node:
            return False

        # Check if node appears in cluster membership
        if not self.node_in_cluster(node_name):
            return False

        # Check if the node itself can see the cluster (has corosync.conf)
        try:
            result = self._run_ssh(node.fqdn, "test -f /etc/pve/corosync.conf && pvecm status >/dev/null 2>&1 && echo OK", check=False)
            return "OK" in result.stdout
        except ClusterOperationError:
            return False

    def rejoin_node(self, node_name: str, password: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        """
        Complete workflow to rejoin a reinstalled node.

        This is IDEMPOTENT - if node is already healthy in cluster, returns early.
        Use force=True to rejoin even if already in cluster.

        Steps:
        0. Check if already healthy (skip if so)
        1. Set up SSH keys (for virgin nodes)
        2. Remove old node entry from cluster
        3. Prepare new node
        4. Join cluster
        5. Configure GPU passthrough (if enabled)

        Args:
            node_name: Name of node to rejoin
            password: Root password for virgin node (optional, loaded from .env)
            force: Force rejoin even if node appears healthy
        """
        logger.info(f"=== Rejoining reinstalled node: {node_name} ===")
        results = []

        # Step 0: Check if already healthy in cluster
        if not force and self.is_node_healthy_in_cluster(node_name):
            logger.info(f"Node {node_name} is already healthy in cluster, skipping cluster rejoin")
            # Still check and configure network/GPU if needed (idempotent)
            node = self.config.get_node(node_name)
            results = []
            if node and node.network and node.network.secondary:
                logger.info("Checking secondary network configuration...")
                net_result = self.configure_network(node_name)
                results.append(("network", net_result))
            if node and node.gpu_passthrough.enabled:
                logger.info("Checking GPU passthrough configuration...")
                gpu_result = self.configure_gpu_passthrough(node_name)
                results.append(("gpu_passthrough", gpu_result))
            return {
                "status": "skipped",
                "message": f"Node {node_name} already healthy in cluster (network/GPU config checked)",
                "results": results,
            }

        # Step 1: Set up SSH keys for virgin node
        logger.info("Step 1: Setting up SSH keys (initial)...")
        ssh_result = self.setup_ssh_keys(node_name, password)
        results.append(("ssh_keys_initial", ssh_result))

        # Step 2: Remove old entry from cluster
        logger.info("Step 2: Removing old node entry...")
        remove_result = self.remove_node(node_name, force=True)
        results.append(("remove_old_entry", remove_result))

        # Step 3: Prepare node (this may reset /etc/pve and recreate symlinks)
        logger.info("Step 3: Preparing node...")
        prep_result = self.prepare_node_for_join(node_name, password)
        results.append(("prepare_node", prep_result))

        # Step 4: Re-setup SSH keys (prepare_node may have reset authorized_keys symlink)
        logger.info("Step 4: Re-setting up SSH keys (post-prepare)...")
        ssh_result2 = self.setup_ssh_keys(node_name, password)
        results.append(("ssh_keys_post_prepare", ssh_result2))

        # Step 5: Join cluster (includes setting up inter-node SSH)
        logger.info("Step 5: Joining cluster...")
        join_result = self.join_node(node_name)
        results.append(("join_cluster", join_result))

        # Step 6: Configure secondary network (if configured)
        node = self.config.get_node(node_name)
        if node and node.network and node.network.secondary:
            logger.info("Step 6: Configuring secondary network...")
            net_result = self.configure_network(node_name)
            results.append(("network", net_result))

        # Step 7: Configure GPU (if enabled)
        if node and node.gpu_passthrough.enabled:
            logger.info("Step 7: Configuring GPU passthrough...")
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
    import getpass
    import os
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
    )

    # Load .env file from config directory
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

    if len(sys.argv) < 2:
        print("Usage: cluster_manager.py <command> [args]")
        print("Commands:")
        print("  status                        - Show cluster status")
        print("  remove <node_name>            - Remove node from cluster")
        print("  ssh-setup <node_name>         - Set up SSH keys on virgin node")
        print("  rejoin <node_name> [--force]  - Rejoin reinstalled node (idempotent)")
        print("  gpu <node_name>               - Configure GPU passthrough")
        print("  apply [--dry-run]             - Apply cluster config")
        print("")
        print("Options:")
        print("  --force   Force rejoin even if node appears healthy")
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

    elif command == "ssh-setup":
        if len(sys.argv) < 3:
            print("Usage: cluster_manager.py ssh-setup <node_name>")
            print("  Password loaded from .env (PVE_ROOT_PASSWORD)")
            sys.exit(1)
        password = os.environ.get("PVE_ROOT_PASSWORD")
        if not password:
            logger.warning("PVE_ROOT_PASSWORD not set in .env, will try interactive")
        result = manager.setup_ssh_keys(sys.argv[2], password)
        print(f"Result: {result}")

    elif command == "rejoin":
        if len(sys.argv) < 3:
            print("Usage: cluster_manager.py rejoin <node_name> [--force]")
            print("  Password loaded from .env (PVE_ROOT_PASSWORD)")
            print("  --force: Rejoin even if node appears healthy")
            sys.exit(1)
        password = os.environ.get("PVE_ROOT_PASSWORD")
        if not password:
            logger.warning("PVE_ROOT_PASSWORD not set in .env, will try interactive")
        force = "--force" in sys.argv
        result = manager.rejoin_node(sys.argv[2], password, force=force)
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
