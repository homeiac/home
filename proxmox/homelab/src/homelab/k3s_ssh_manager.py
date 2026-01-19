"""K3s VM SSH configuration management.

This module provides utilities to manage SSH password authentication
on K3s VMs running Ubuntu cloud images, which have conflicting SSH
configuration files that disable password auth by default.
"""

import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VMConfig:
    """Configuration for a K3s VM."""

    host: str
    vmid: str


# Type alias for VM mapping dictionary
VMMapping = dict[str, VMConfig]


def _get_default_vm_mapping() -> VMMapping:
    """Get default K3s VM mapping.

    Returns:
        Dictionary mapping VM names to their VMConfig.
    """
    return {
        "k3s-vm-chief-horse": VMConfig(host="chief-horse", vmid="109"),
        "k3s-vm-pumped-piglet-gpu": VMConfig(host="pumped-piglet", vmid="105"),
        "k3s-vm-pve": VMConfig(host="pve", vmid="107"),
        "k3s-vm-still-fawn": VMConfig(host="still-fawn", vmid="108"),
    }


class K3sSSHManager:
    """Manages SSH configuration for K3s VMs.

    Fixes the issue where Ubuntu cloud images have conflicting SSH
    configuration files: 50-cloud-init.conf enables password auth,
    but 60-cloudimg-settings.conf (loaded later) disables it.
    """

    def __init__(self, vm_mapping: Optional[VMMapping] = None) -> None:
        """Initialize K3s SSH manager.

        Args:
            vm_mapping: Dict mapping VM names to their VMConfig.
                       If None, uses default mapping.
        """
        self.vm_mapping = vm_mapping or _get_default_vm_mapping()

    def enable_password_auth(
        self, vm_name: Optional[str] = None
    ) -> dict[str, bool]:
        """Enable SSH password authentication on K3s VMs.

        Fixes the issue where 60-cloudimg-settings.conf disables password auth
        after cloud-init enables it.

        Args:
            vm_name: Specific VM name to fix, or None to fix all VMs.

        Returns:
            Dict mapping VM names to success status.
        """
        results: dict[str, bool] = {}
        vms_to_fix = [vm_name] if vm_name else list(self.vm_mapping.keys())

        for vm in vms_to_fix:
            if vm not in self.vm_mapping:
                logger.warning("Unknown VM: %s", vm)
                results[vm] = False
                continue

            config = self.vm_mapping[vm]
            logger.info(
                "Enabling password auth on %s (host=%s, vmid=%s)",
                vm,
                config.host,
                config.vmid,
            )

            results[vm] = self._enable_password_auth_for_vm(vm, config)

        return results

    def _enable_password_auth_for_vm(
        self, vm_name: str, config: VMConfig
    ) -> bool:
        """Enable password auth for a single VM.

        Args:
            vm_name: Name of the VM for logging.
            config: VM configuration with host and vmid.

        Returns:
            True if successful, False otherwise.
        """
        try:
            # Check current config
            check_cmd = [
                "ssh",
                f"root@{config.host}.maas",
                f"qm guest exec {config.vmid} -- grep '^PasswordAuthentication' "
                "/etc/ssh/sshd_config.d/60-cloudimg-settings.conf",
            ]

            check_result = subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # If already set to yes, skip
            if "PasswordAuthentication yes" in check_result.stdout:
                logger.info("%s: Password auth already enabled", vm_name)
                return True

            # Fix the configuration
            fix_cmd = [
                "ssh",
                f"root@{config.host}.maas",
                f"qm guest exec {config.vmid} -- bash -c \"sed -i "
                "'s/^PasswordAuthentication no/PasswordAuthentication yes/' "
                "/etc/ssh/sshd_config.d/60-cloudimg-settings.conf && "
                "systemctl restart ssh\"",
            ]

            subprocess.run(
                fix_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            logger.info("%s: Password auth enabled and SSH restarted", vm_name)
            return True

        except subprocess.TimeoutExpired:
            logger.error("%s: Timeout while configuring SSH", vm_name)
            return False
        except subprocess.CalledProcessError as e:
            logger.error("%s: Failed to configure SSH: %s", vm_name, e.stderr)
            return False

    def validate_password_auth(
        self, vm_name: Optional[str] = None
    ) -> dict[str, bool]:
        """Validate that password authentication is enabled on K3s VMs.

        Args:
            vm_name: Specific VM name to check, or None to check all VMs.

        Returns:
            Dict mapping VM names to validation status (True = enabled).
        """
        results: dict[str, bool] = {}
        vms_to_check = [vm_name] if vm_name else list(self.vm_mapping.keys())

        for vm in vms_to_check:
            if vm not in self.vm_mapping:
                logger.warning("Unknown VM: %s", vm)
                results[vm] = False
                continue

            config = self.vm_mapping[vm]
            results[vm] = self._validate_password_auth_for_vm(vm, config)

        return results

    def _validate_password_auth_for_vm(
        self, vm_name: str, config: VMConfig
    ) -> bool:
        """Validate password auth for a single VM.

        Args:
            vm_name: Name of the VM for logging.
            config: VM configuration with host and vmid.

        Returns:
            True if password auth is enabled, False otherwise.
        """
        try:
            # Check final effective config (last occurrence wins)
            check_cmd = [
                "ssh",
                f"root@{config.host}.maas",
                f"qm guest exec {config.vmid} -- bash -c \"grep '^PasswordAuthentication' "
                "/etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null | "
                "tail -1\"",
            ]

            check_result = subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            is_enabled = "PasswordAuthentication yes" in check_result.stdout

            if is_enabled:
                logger.info("%s: Password auth is enabled", vm_name)
            else:
                logger.warning("%s: Password auth is disabled", vm_name)

            return is_enabled

        except subprocess.TimeoutExpired:
            logger.error("%s: Timeout while checking SSH config", vm_name)
            return False

    def get_vm_ips(self) -> dict[str, Optional[str]]:
        """Get IP addresses of all K3s VMs.

        Returns:
            Dict mapping VM names to their IP addresses (None if unavailable).
        """
        ips: dict[str, Optional[str]] = {}

        for vm_name, config in self.vm_mapping.items():
            ips[vm_name] = self._get_vm_ip(vm_name, config)

        return ips

    def _get_vm_ip(self, vm_name: str, config: VMConfig) -> Optional[str]:
        """Get IP address for a single VM.

        Args:
            vm_name: Name of the VM for logging.
            config: VM configuration with host and vmid.

        Returns:
            IP address string or None if unavailable.
        """
        try:
            cmd = [
                "ssh",
                f"root@{config.host}.maas",
                f"qm guest exec {config.vmid} -- hostname -I",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and result.stdout.strip():
                # Get first IP from output
                return result.stdout.strip().split()[0]
            return None

        except subprocess.TimeoutExpired:
            logger.error("%s: Timeout while getting IP", vm_name)
            return None
