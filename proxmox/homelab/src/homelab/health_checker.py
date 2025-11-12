"""VM and K3s health checking."""

import logging
from dataclasses import dataclass
from typing import Any, List

logger = logging.getLogger(__name__)


@dataclass
class VMHealthStatus:
    """Health status of a VM."""

    is_healthy: bool
    should_delete: bool
    reason: str


class VMHealthChecker:
    """Check VM health and determine if recreation needed."""

    def __init__(self, proxmox: Any, node_name: str):
        """Initialize VM health checker.

        Args:
            proxmox: Proxmox API client instance
            node_name: Name of the Proxmox node to check VMs on
        """
        self.proxmox = proxmox
        self.node_name = node_name

    def check_vm_health(self, vmid: int) -> VMHealthStatus:
        """Check if VM is healthy or needs recreation.

        Args:
            vmid: VM ID to check

        Returns:
            VMHealthStatus with health status and reason
        """
        try:
            status = self.proxmox.nodes(self.node_name).qemu(vmid).status.current.get()
            vm_status = status.get("status", "unknown")

            # Running VMs are healthy
            if vm_status == "running":
                return VMHealthStatus(is_healthy=True, should_delete=False, reason="VM is running")

            # Stopped VMs should be deleted and recreated
            if vm_status == "stopped":
                return VMHealthStatus(is_healthy=False, should_delete=True, reason="VM is stopped")

            # Paused VMs should be deleted and recreated
            if vm_status == "paused":
                return VMHealthStatus(is_healthy=False, should_delete=True, reason="VM is paused")

            # Unknown state - don't delete
            return VMHealthStatus(is_healthy=False, should_delete=False, reason=f"VM in unknown state: {vm_status}")

        except Exception as e:
            logger.error(f"Error checking VM {vmid}: {e}")
            return VMHealthStatus(is_healthy=False, should_delete=False, reason=f"Error: {e}")

    def validate_network_bridges(self, required_bridges: List[str]) -> bool:
        """Validate that all required network bridges exist on the node.

        Args:
            required_bridges: List of bridge names that must exist (e.g., ['vmbr0', 'vmbr1'])

        Returns:
            True if all required bridges exist, False otherwise
        """
        if not required_bridges:
            return True

        try:
            network_interfaces = self.proxmox.nodes(self.node_name).network.get()
            existing_bridges = {iface["iface"] for iface in network_interfaces if iface.get("type") == "bridge"}

            for bridge in required_bridges:
                if bridge not in existing_bridges:
                    logger.warning(f"Required bridge {bridge} not found on node {self.node_name}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating network bridges on {self.node_name}: {e}")
            return False
