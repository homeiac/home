#!/usr/bin/env python3
"""
GPU passthrough configuration for Proxmox VMs.

Handles:
- IOMMU group detection
- VFIO module configuration
- PCI device mapping creation
- GPU availability verification

All operations are idempotent and safe to re-run.
"""

import glob
import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GPUPassthroughManager:
    """Manages GPU passthrough configuration for Proxmox VMs."""

    def __init__(self, proxmox_client: Any, node: str):
        """
        Initialize GPU passthrough manager.

        Args:
            proxmox_client: ProxmoxAPI client instance
            node: Proxmox node name (e.g., 'pumped-piglet')
        """
        self.proxmox = proxmox_client
        self.node = node
        self.logger = logger

    def detect_nvidia_gpu(self) -> Optional[Dict[str, str]]:
        """
        Find NVIDIA GPU PCI address and details.

        Returns:
            Dictionary with GPU info:
            {
                'pci_address': str (e.g., '0000:b3:00.0'),
                'short_address': str (e.g., 'b3:00.0'),
                'description': str,
                'device_id': str
            }
            or None if no NVIDIA GPU found
        """
        try:
            result = subprocess.run(
                ["ssh", f"root@{self.node}.maas", "lspci", "-nn"],
                capture_output=True,
                text=True,
                check=True,
            )

            for line in result.stdout.splitlines():
                if "NVIDIA" in line and "VGA" in line:
                    # Parse line like: "b3:00.0 VGA compatible controller [0300]: NVIDIA Corporation..."
                    match = re.match(r"([0-9a-f:\.]+)\s", line)
                    if match:
                        short_addr = match.group(1)
                        pci_addr = f"0000:{short_addr}"

                        # Extract device description
                        desc_match = re.search(r"\[([0-9a-f]{4}:[0-9a-f]{4})\]", line)
                        device_id = desc_match.group(1) if desc_match else "unknown"

                        description = line.split(":", 2)[2].strip()

                        self.logger.info(f"Found NVIDIA GPU: {description} at {pci_addr}")
                        return {
                            "pci_address": pci_addr,
                            "short_address": short_addr,
                            "description": description,
                            "device_id": device_id,
                        }

            self.logger.warning("No NVIDIA GPU found via lspci")
            return None

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error detecting GPU: {e}")
            return None

    def detect_nvidia_audio(self, gpu_short_addr: str) -> Optional[str]:
        """
        Find NVIDIA audio device (usually at same bus, function .1).

        Args:
            gpu_short_addr: Short PCI address of GPU (e.g., 'b3:00.0')

        Returns:
            Full PCI address of audio device or None
        """
        # NVIDIA audio is typically at same bus, function 1
        # E.g., if GPU is b3:00.0, audio is b3:00.1
        bus_dev = gpu_short_addr.rsplit(".", 1)[0]  # Get 'b3:00'
        audio_short = f"{bus_dev}.1"
        audio_full = f"0000:{audio_short}"

        try:
            result = subprocess.run(
                ["ssh", f"root@{self.node}.maas", "lspci", "-s", audio_short],
                capture_output=True,
                text=True,
            )

            if "Audio" in result.stdout and "NVIDIA" in result.stdout:
                self.logger.info(f"Found NVIDIA audio device at {audio_full}")
                return audio_full

            return None
        except subprocess.CalledProcessError:
            return None

    def get_iommu_group(self, pci_addr: str) -> Optional[int]:
        """
        Get IOMMU group for PCI device.

        Args:
            pci_addr: PCI address (e.g., '0000:b3:00.0')

        Returns:
            IOMMU group number or None if not found
        """
        short_addr = pci_addr.split(":", 1)[1] if ":" in pci_addr else pci_addr

        try:
            result = subprocess.run(
                [
                    "ssh",
                    f"root@{self.node}.maas",
                    f"readlink /sys/bus/pci/devices/0000:{short_addr}/iommu_group",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                # Output looks like: ../../../kernel/iommu_groups/1
                group_match = re.search(r"iommu_groups/(\d+)", result.stdout)
                if group_match:
                    group_num = int(group_match.group(1))
                    self.logger.debug(f"IOMMU group for {pci_addr}: {group_num}")
                    return group_num

            return None
        except (subprocess.CalledProcessError, ValueError):
            return None

    def vfio_modules_loaded(self) -> bool:
        """
        Check if VFIO modules are loaded.

        Returns:
            True if all required VFIO modules are loaded
        """
        required_modules = ["vfio", "vfio_pci", "vfio_iommu_type1"]

        try:
            result = subprocess.run(
                ["ssh", f"root@{self.node}.maas", "lsmod"],
                capture_output=True,
                text=True,
                check=True,
            )

            loaded = all(mod in result.stdout for mod in required_modules)

            if loaded:
                self.logger.info("✅ All VFIO modules are loaded")
            else:
                missing = [m for m in required_modules if m not in result.stdout]
                self.logger.info(f"⚠️  Missing VFIO modules: {', '.join(missing)}")

            return loaded
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error checking VFIO modules: {e}")
            return False

    def ensure_vfio_modules(self) -> bool:
        """
        Ensure VFIO modules are configured in /etc/modules.

        Returns:
            True if modules were added (reboot required), False if already present
        """
        modules_to_add = ["vfio", "vfio_iommu_type1", "vfio_pci", "vfio_virqfd"]

        try:
            # Read current /etc/modules
            result = subprocess.run(
                ["ssh", f"root@{self.node}.maas", "cat", "/etc/modules"],
                capture_output=True,
                text=True,
                check=True,
            )
            existing_content = result.stdout

            # Check which modules need to be added
            to_add = [m for m in modules_to_add if m not in existing_content]

            if not to_add:
                self.logger.info("✅ All VFIO modules already in /etc/modules")
                return False

            # Add missing modules
            self.logger.info(f"📝 Adding VFIO modules to /etc/modules: {', '.join(to_add)}")
            for mod in to_add:
                subprocess.run(
                    [
                        "ssh",
                        f"root@{self.node}.maas",
                        f"echo '{mod}' >> /etc/modules",
                    ],
                    check=True,
                    shell=True,
                )

            # Blacklist nouveau driver
            self.blacklist_nouveau()

            # Update initramfs
            self.logger.info("🔧 Updating initramfs...")
            subprocess.run(
                [
                    "ssh",
                    f"root@{self.node}.maas",
                    "update-initramfs",
                    "-u",
                    "-k",
                    "all",
                ],
                check=True,
                capture_output=True,
            )

            self.logger.warning("⚠️  VFIO modules configured - REBOOT REQUIRED!")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error configuring VFIO modules: {e}")
            raise

    def blacklist_nouveau(self) -> bool:
        """
        Blacklist nouveau driver (idempotent).

        Returns:
            True if blacklist was added, False if already present
        """
        blacklist_file = "/etc/modprobe.d/blacklist-nvidia-nouveau.conf"
        blacklist_content = "blacklist nouveau\noptions nouveau modeset=0\n"

        try:
            # Check if blacklist file exists
            result = subprocess.run(
                ["ssh", f"root@{self.node}.maas", "cat", blacklist_file],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0 and "blacklist nouveau" in result.stdout:
                self.logger.info("✅ Nouveau driver already blacklisted")
                return False

            # Create blacklist file
            self.logger.info("📝 Blacklisting nouveau driver")
            subprocess.run(
                [
                    "ssh",
                    f"root@{self.node}.maas",
                    f"echo '{blacklist_content}' > {blacklist_file}",
                ],
                check=True,
                shell=True,
            )
            return True

        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Could not blacklist nouveau: {e}")
            return False

    def create_hostpci_config(self, gpu_pci: str, audio_pci: Optional[str] = None) -> str:
        """
        Generate Proxmox hostpci configuration string.

        Args:
            gpu_pci: GPU PCI address
            audio_pci: Optional audio PCI address

        Returns:
            Proxmox hostpci config string
        """
        # Remove '0000:' prefix if present
        gpu_short = gpu_pci.replace("0000:", "")

        if audio_pci:
            audio_short = audio_pci.replace("0000:", "")
            config = f"{gpu_short};{audio_short},pcie=1,x-vga=1"
        else:
            config = f"{gpu_short},pcie=1,x-vga=1"

        return config

    def verify_gpu_passthrough(self, vm_id: int) -> bool:
        """
        Verify GPU is passed through to VM.

        Args:
            vm_id: Proxmox VM ID

        Returns:
            True if GPU passthrough is configured
        """
        try:
            vm_config = self.proxmox.nodes(self.node).qemu(vm_id).config.get()

            # Check for hostpci0 configuration
            has_hostpci = any(key.startswith("hostpci") for key in vm_config.keys())

            if has_hostpci:
                self.logger.info(f"✅ VM {vm_id} has GPU passthrough configured")
                return True
            else:
                self.logger.warning(f"⚠️  VM {vm_id} has no GPU passthrough")
                return False

        except Exception as e:
            self.logger.error(f"Error checking VM config: {e}")
            return False
