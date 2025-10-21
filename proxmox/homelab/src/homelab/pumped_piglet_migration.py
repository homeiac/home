#!/usr/bin/env python3
"""
Orchestrates the complete still-fawn → pumped-piglet migration.

This is the main entry point for the idempotent migration process.
Handles:
- State persistence (resume from failures)
- Step validation
- Comprehensive logging
- K3s VM creation with GPU passthrough
- Storage setup (2TB NVMe + 20TB HDD import)
- K3s cluster join
- Workload migration

Usage:
    poetry run python -m homelab.pumped_piglet_migration

To start from a specific phase:
    poetry run python -m homelab.pumped_piglet_migration --start-from=gpu
"""

import argparse
import json
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from homelab.config import Config
from homelab.gpu_passthrough_manager import GPUPassthroughManager
from homelab.k3s_migration_manager import K3sMigrationManager
from homelab.proxmox_api import ProxmoxClient
from homelab.storage_manager import StorageManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(f"/tmp/pumped_piglet_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class MigrationState:
    """Persistent state for migration progress."""

    def __init__(self, state_file: Path):
        """
        Initialize migration state.

        Args:
            state_file: Path to JSON state file
        """
        self.state_file = state_file
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load state from file or create new state."""
        if self.state_file.exists():
            with open(self.state_file) as f:
                return json.load(f)

        return {
            "started_at": datetime.now().isoformat(),
            "steps": {},
            "vm_info": {},
            "gpu_info": {},
            "storage_info": {},
        }

    def save(self) -> None:
        """Save current state to file."""
        self.state["last_updated"] = datetime.now().isoformat()
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def mark_step_complete(self, step_name: str, result: Any) -> None:
        """
        Mark a step as complete.

        Args:
            step_name: Name of the step
            result: Result data from the step
        """
        self.state["steps"][step_name] = {
            "completed_at": datetime.now().isoformat(),
            "result": result,
        }
        self.save()

    def is_step_complete(self, step_name: str) -> bool:
        """
        Check if step is complete.

        Args:
            step_name: Name of the step

        Returns:
            True if step is complete
        """
        return step_name in self.state["steps"]

    def get_step_result(self, step_name: str) -> Optional[Any]:
        """
        Get result from completed step.

        Args:
            step_name: Name of the step

        Returns:
            Step result or None if not complete
        """
        step_data = self.state["steps"].get(step_name)
        return step_data.get("result") if step_data else None

    def store_vm_info(self, vm_id: int, vm_ip: str) -> None:
        """Store VM information."""
        self.state["vm_info"] = {"vmid": vm_id, "ip": vm_ip}
        self.save()

    def store_gpu_info(self, gpu_info: Dict[str, str]) -> None:
        """Store GPU information."""
        self.state["gpu_info"] = gpu_info
        self.save()

    def store_storage_info(self, storage_info: Dict[str, Any]) -> None:
        """Store storage information."""
        self.state["storage_info"] = storage_info
        self.save()


class PumpedPigletMigration:
    """Main migration orchestrator for pumped-piglet."""

    # Migration configuration
    NODE = "pumped-piglet"
    VM_NAME = "k3s-vm-pumped-piglet"
    VM_CORES = 10  # Leave 2 threads for host
    VM_MEMORY_MB = 49152  # 48GB
    VM_DISK_SIZE_GB = 1800  # 1.8TB on 2TB NVMe

    # Storage configuration
    NVME_DEVICE = "/dev/nvme1n1"
    NVME_POOL = "local-2TB-zfs"
    HDD_DEVICE = "/dev/sda"
    HDD_POOL = "local-20TB-zfs"

    # K3s configuration
    EXISTING_K3S_NODE = "192.168.4.238"  # k3s-vm-pve
    K3S_MASTER_URL = "https://192.168.4.238:6443"

    def __init__(self, state_file: str = "/tmp/pumped_piglet_migration.json"):
        """
        Initialize migration orchestrator.

        Args:
            state_file: Path to state file
        """
        self.state = MigrationState(Path(state_file))
        self.logger = logger

        # Initialize Proxmox client
        self.proxmox = ProxmoxClient.from_env()

        # Initialize managers
        self.storage_mgr = StorageManager(self.proxmox, self.NODE)
        self.gpu_mgr = GPUPassthroughManager(self.proxmox, self.NODE)
        self.k3s_mgr: Optional[K3sMigrationManager] = None  # Created after VM

    def run_step(self, step_name: str, step_func, *args, **kwargs) -> Any:
        """
        Execute step with idempotency and state tracking.

        Args:
            step_name: Name of the step
            step_func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Result from step function
        """
        if self.state.is_step_complete(step_name):
            self.logger.info(f"⏭️  Step '{step_name}' already complete, skipping")
            return self.state.get_step_result(step_name)

        self.logger.info(f"▶️  Running step: {step_name}")
        result = step_func(*args, **kwargs)
        self.state.mark_step_complete(step_name, result)
        self.logger.info(f"✅ Step '{step_name}' completed")
        return result

    # ==================== PHASE 1: STORAGE SETUP ====================

    def phase1_storage_setup(self) -> Dict[str, Any]:
        """
        Phase 1: Configure ZFS pools on pumped-piglet.

        Returns:
            Dictionary with storage setup results
        """
        self.logger.info("=" * 60)
        self.logger.info("PHASE 1: Storage Setup")
        self.logger.info("=" * 60)

        # Step 1.1: Create 2TB NVMe pool
        nvme_result = self.run_step(
            "create_2tb_nvme_pool",
            self.storage_mgr.create_or_import_pool,
            pool_name=self.NVME_POOL,
            device=self.NVME_DEVICE,
            import_if_exists=False,  # Fresh pool
        )

        # Step 1.2: Register 2TB with Proxmox
        self.run_step(
            "register_2tb_storage",
            self.storage_mgr.register_with_proxmox,
            pool_name=self.NVME_POOL,
            storage_id=self.NVME_POOL,
            content_types=["images", "rootdir"],
        )

        # Step 1.3: Import 20TB pool
        hdd_result = self.run_step(
            "import_20tb_pool",
            self.storage_mgr.create_or_import_pool,
            pool_name=self.HDD_POOL,
            device=self.HDD_DEVICE,
            import_if_exists=True,  # Import existing
        )

        # Step 1.4: Register 20TB with Proxmox
        self.run_step(
            "register_20tb_storage",
            self.storage_mgr.register_with_proxmox,
            pool_name=self.HDD_POOL,
            storage_id=self.HDD_POOL,
            content_types=["images", "rootdir", "vztmpl"],
        )

        storage_info = {
            "nvme_pool": nvme_result,
            "hdd_pool": hdd_result,
        }
        self.state.store_storage_info(storage_info)

        return storage_info

    # ==================== PHASE 2: GPU PASSTHROUGH ====================

    def phase2_gpu_passthrough(self) -> Dict[str, Any]:
        """
        Phase 2: Configure GPU passthrough.

        Returns:
            Dictionary with GPU setup results
        """
        self.logger.info("=" * 60)
        self.logger.info("PHASE 2: GPU Passthrough Setup")
        self.logger.info("=" * 60)

        # Step 2.1: Detect GPU
        gpu_info = self.run_step("detect_gpu", self.gpu_mgr.detect_nvidia_gpu)

        if not gpu_info:
            raise RuntimeError("❌ NVIDIA GPU not found on pumped-piglet!")

        self.logger.info(f"Found GPU: {gpu_info['description']}")
        self.state.store_gpu_info(gpu_info)

        # Step 2.2: Detect audio device
        audio_info = self.run_step(
            "detect_gpu_audio",
            self.gpu_mgr.detect_nvidia_audio,
            gpu_info["short_address"],
        )

        # Step 2.3: Ensure VFIO modules
        vfio_added = self.run_step("configure_vfio", self.gpu_mgr.ensure_vfio_modules)

        if vfio_added:
            self.logger.error("=" * 60)
            self.logger.error("⚠️  REBOOT REQUIRED!")
            self.logger.error("=" * 60)
            self.logger.error("VFIO modules have been configured.")
            self.logger.error("Please reboot pumped-piglet and run this script again.")
            self.logger.error("")
            self.logger.error("Command: ssh root@pumped-piglet.maas reboot")
            raise SystemExit(1)

        # Check if modules are loaded
        if not self.gpu_mgr.vfio_modules_loaded():
            self.logger.warning("⚠️  VFIO modules not loaded - may need reboot")

        return {
            "gpu": gpu_info,
            "audio": audio_info,
            "vfio_configured": True,
        }

    # ==================== PHASE 3: VM CREATION ====================

    def phase3_create_vm(self) -> Dict[str, Any]:
        """
        Phase 3: Create K3s VM with GPU passthrough.

        Returns:
            Dictionary with VM creation results
        """
        self.logger.info("=" * 60)
        self.logger.info("PHASE 3: K3s VM Creation")
        self.logger.info("=" * 60)

        # Get GPU info from state
        gpu_info = self.state.state.get("gpu_info", {})
        if not gpu_info:
            raise RuntimeError("GPU info not found in state - run phase2 first")

        # Step 3.1: Get next available VMID
        from homelab.vm_manager import VMManager

        vmid = self.run_step(
            "get_next_vmid", VMManager.get_next_available_vmid, self.proxmox
        )

        self.logger.info(f"Using VMID: {vmid}")

        # Step 3.2: Check if VM already exists
        vm_exists = self.run_step(
            "check_vm_exists", self._check_vm_exists_by_name, self.VM_NAME
        )

        if vm_exists:
            self.logger.info(f"✅ VM {self.VM_NAME} already exists (VMID: {vm_exists})")
            vmid = vm_exists
        else:
            # Step 3.3: Create VM
            vmid = self.run_step(
                "create_vm",
                self._create_vm_with_gpu,
                vmid,
                gpu_info["pci_address"],
                self.state.state.get("gpu_info", {}).get("audio"),
            )

        # Step 3.4: Get VM IP
        vm_ip = self.run_step("get_vm_ip", self._wait_for_vm_ip, vmid)

        self.state.store_vm_info(vmid, vm_ip)

        return {"vmid": vmid, "ip": vm_ip, "hostname": self.VM_NAME}

    def _check_vm_exists_by_name(self, vm_name: str) -> Optional[int]:
        """Check if VM exists by name."""
        try:
            vms = self.proxmox.nodes(self.NODE).qemu.get()
            for vm in vms:
                if vm.get("name") == vm_name:
                    return int(vm["vmid"])
            return None
        except Exception as e:
            self.logger.error(f"Error checking VM existence: {e}")
            return None

    def _create_vm_with_gpu(
        self, vmid: int, gpu_pci: str, audio_pci: Optional[str]
    ) -> int:
        """Create VM with GPU passthrough."""
        self.logger.info(f"Creating VM {vmid} ({self.VM_NAME}) with GPU passthrough")

        # Download cloud image if needed
        img_path = "/tmp/noble-cloudimg.img"
        if not Path(img_path).exists():
            self.logger.info("Downloading Ubuntu cloud image...")
            subprocess.run(
                [
                    "wget",
                    "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img",
                    "-O",
                    img_path,
                ],
                check=True,
            )

        # Create VM via SSH commands
        commands = [
            # Create VM
            f"qm create {vmid} --name {self.VM_NAME} --memory {self.VM_MEMORY_MB} "
            f"--cores {self.VM_CORES} --cpu host --net0 virtio,bridge=vmbr0 "
            f"--serial0 socket --vga serial0 --agent enabled=1",
            # Import disk
            f"qm importdisk {vmid} {img_path} {self.NVME_POOL}",
            # Attach disk
            f"qm set {vmid} --scsi0 {self.NVME_POOL}:vm-{vmid}-disk-0",
            # Resize disk
            f"qm resize {vmid} scsi0 {self.VM_DISK_SIZE_GB}G",
            # Add cloud-init
            f"qm set {vmid} --ide2 {self.NVME_POOL}:cloudinit",
            # Configure boot
            f"qm set {vmid} --boot order=scsi0",
            # Cloud-init config
            f"qm set {vmid} --ipconfig0 ip=dhcp",
            f"qm set {vmid} --ciuser ubuntu",
            f"qm set {vmid} --sshkeys /root/.ssh/authorized_keys",
        ]

        # Add GPU passthrough
        hostpci_config = self.gpu_mgr.create_hostpci_config(gpu_pci, audio_pci)
        commands.append(f"qm set {vmid} --hostpci0 {hostpci_config}")

        # Start VM
        commands.append(f"qm start {vmid}")

        # Execute all commands
        for cmd in commands:
            self.logger.debug(f"Executing: {cmd}")
            subprocess.run(
                ["ssh", f"root@{self.NODE}.maas", cmd],
                check=True,
                capture_output=True,
            )

        return vmid

    def _wait_for_vm_ip(self, vmid: int, timeout: int = 180) -> str:
        """Wait for VM to get IP address."""
        self.logger.info(f"Waiting for VM {vmid} to get IP address...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                result = subprocess.run(
                    [
                        "ssh",
                        f"root@{self.NODE}.maas",
                        f"qm guest cmd {vmid} network-get-interfaces",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0:
                    import json

                    interfaces = json.loads(result.stdout)
                    for iface in interfaces:
                        if iface.get("name") == "eth0":
                            ip_addresses = iface.get("ip-addresses", [])
                            for addr in ip_addresses:
                                if addr.get("ip-address-type") == "ipv4":
                                    ip = addr.get("ip-address")
                                    if ip and not ip.startswith("127."):
                                        self.logger.info(f"✅ VM IP: {ip}")
                                        return ip

            except (subprocess.TimeoutExpired, json.JSONDecodeError):
                pass

            time.sleep(5)

        raise TimeoutError(f"VM {vmid} did not get IP within {timeout}s")

    # ==================== PHASE 4: K3S BOOTSTRAP ====================

    def phase4_k3s_bootstrap(self) -> Dict[str, Any]:
        """
        Phase 4: Bootstrap K3s on new node.

        Returns:
            Dictionary with K3s bootstrap results
        """
        self.logger.info("=" * 60)
        self.logger.info("PHASE 4: K3s Bootstrap")
        self.logger.info("=" * 60)

        # Get VM info from state
        vm_info = self.state.state.get("vm_info", {})
        if not vm_info:
            raise RuntimeError("VM info not found - run phase3 first")

        # Initialize K3s manager
        self.k3s_mgr = K3sMigrationManager(
            vm_hostname=self.VM_NAME, existing_node_ip=self.EXISTING_K3S_NODE
        )

        # Step 4.1: Get join token
        token = self.run_step("get_k3s_token", self.k3s_mgr.get_join_token)

        # Step 4.2: Bootstrap K3s
        installed = self.run_step(
            "bootstrap_k3s",
            self.k3s_mgr.bootstrap_k3s,
            token=token,
            master_url=self.K3S_MASTER_URL,
            node_labels={"gpu": "nvidia", "memory": "high"},
        )

        # Step 4.3: Verify GPU availability
        gpu_available = self.run_step("verify_gpu", self.k3s_mgr.verify_gpu_available)

        if not gpu_available:
            self.logger.warning("⚠️  GPU not available in VM - check passthrough")

        # Step 4.4: Wait for node to join cluster
        time.sleep(30)  # Give cluster time to register node

        node_in_cluster = self.run_step(
            "verify_node_in_cluster", self.k3s_mgr.node_in_cluster, self.VM_NAME
        )

        return {
            "installed": installed,
            "gpu_available": gpu_available,
            "in_cluster": node_in_cluster,
        }

    # ==================== PHASE 5: WORKLOAD MIGRATION ====================

    def phase5_migrate_workloads(self) -> Dict[str, Any]:
        """
        Phase 5: Migrate workloads from still-fawn.

        Returns:
            Dictionary with migration results
        """
        self.logger.info("=" * 60)
        self.logger.info("PHASE 5: Workload Migration")
        self.logger.info("=" * 60)

        # Cordon still-fawn (if it exists)
        try:
            self.run_step(
                "cordon_still_fawn", self.k3s_mgr.cordon_node, "k3s-vm-still-fawn"
            )
        except Exception as e:
            self.logger.warning(f"Could not cordon still-fawn: {e}")

        # Delete stuck pods
        deleted_pods = self.run_step(
            "delete_stuck_pods",
            self.k3s_mgr.delete_stuck_pods,
            "k3s-vm-still-fawn",
        )

        self.logger.info(f"Deleted {len(deleted_pods)} stuck pods")

        # Flux will automatically reschedule pods to available nodes

        return {"deleted_pods": deleted_pods}

    # ==================== MAIN EXECUTION ====================

    def execute(self, start_from: Optional[str] = None) -> None:
        """
        Execute complete migration.

        Args:
            start_from: Optional phase to start from ('storage', 'gpu', 'vm', 'k3s', 'migrate')
        """
        self.logger.info("=" * 60)
        self.logger.info("🚀 PUMPED-PIGLET MIGRATION ORCHESTRATOR")
        self.logger.info("=" * 60)
        self.logger.info(f"Target node: {self.NODE}")
        self.logger.info(f"State file: {self.state.state_file}")
        self.logger.info("")

        try:
            phases = ["storage", "gpu", "vm", "k3s", "migrate"]
            start_index = phases.index(start_from) if start_from else 0

            if start_index <= 0:
                self.phase1_storage_setup()

            if start_index <= 1:
                self.phase2_gpu_passthrough()

            if start_index <= 2:
                self.phase3_create_vm()

            if start_index <= 3:
                self.phase4_k3s_bootstrap()

            if start_index <= 4:
                self.phase5_migrate_workloads()

            self.logger.info("")
            self.logger.info("=" * 60)
            self.logger.info("✅ MIGRATION COMPLETED SUCCESSFULLY!")
            self.logger.info("=" * 60)

        except SystemExit:
            # Reboot required - this is expected
            raise
        except Exception as e:
            self.logger.error("")
            self.logger.error("=" * 60)
            self.logger.error("❌ MIGRATION FAILED")
            self.logger.error("=" * 60)
            self.logger.error(f"Error: {e}")
            self.logger.error("")
            self.logger.error("State has been saved. Fix the issue and re-run to resume.")
            raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Pumped-Piglet Migration Orchestrator")
    parser.add_argument(
        "--start-from",
        choices=["storage", "gpu", "vm", "k3s", "migrate"],
        help="Phase to start from (resume migration)",
    )
    parser.add_argument(
        "--state-file",
        default="/tmp/pumped_piglet_migration.json",
        help="Path to state file",
    )

    args = parser.parse_args()

    orchestrator = PumpedPigletMigration(state_file=args.state_file)
    orchestrator.execute(start_from=args.start_from)


if __name__ == "__main__":
    main()
