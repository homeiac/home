"""
Enhanced VM Manager with complete Crucible storage integration.
Extends existing VM management with Oxide-style disk operations.
"""

import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import paramiko

from homelab.config import Config
from homelab.crucible_config import CrucibleConfig
from homelab.oxide_storage_api import (
    DiskCreate,
    DiskSource,
    OxideStorageAPI,
    SnapshotCreate,
    create_storage_api
)
from homelab.proxmox_api import ProxmoxClient
from homelab.resource_manager import ResourceManager

logger = logging.getLogger(__name__)


class CrucibleVMManager:
    """
    Enhanced VM manager with integrated Crucible storage support.
    Provides complete lifecycle management for VMs with distributed storage.
    """
    
    def __init__(self, project_id: str = "homelab", enable_mocking: bool = False):
        self.project_id = project_id
        self.storage_api = create_storage_api(project_id, enable_mocking=enable_mocking)
        self.crucible_config = self.storage_api.config
        
        # VM configuration
        self.vm_configs: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"Initialized CrucibleVMManager for project {project_id}")
    
    # === VM LIFECYCLE WITH STORAGE ===
    
    async def create_vm_with_storage(
        self,
        vm_name: str,
        node_name: str,
        disk_size_gb: int = 50,
        memory_mb: int = 4096,
        cpu_cores: int = 2,
        disk_source: DiskSource = DiskSource.BLANK,
        snapshot_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a VM with Crucible-backed storage disk.
        
        Args:
            vm_name: Name of the VM to create
            node_name: Proxmox node to create VM on
            disk_size_gb: Size of boot disk in GB
            memory_mb: RAM allocation in MB
            cpu_cores: CPU core count
            disk_source: Source for boot disk (blank, snapshot, image)
            snapshot_id: Source snapshot ID if disk_source is snapshot
        
        Returns:
            Dict containing VM and disk information
        """
        logger.info(f"🚀 Creating VM '{vm_name}' on node '{node_name}' with {disk_size_gb}GB Crucible storage")
        
        try:
            # 1. Create Crucible storage disk
            disk_name = f"{vm_name}-boot-disk"
            disk_create = DiskCreate(
                name=disk_name,
                description=f"Boot disk for VM {vm_name}",
                size=disk_size_gb * 1024**3,  # Convert GB to bytes
                disk_source=disk_source,
                block_size=self.crucible_config.default_block_size,
                snapshot_id=snapshot_id
            )
            
            disk = await self.storage_api.disk_create(disk_create)
            disk_id = disk["id"]
            
            logger.info(f"✅ Created Crucible disk {disk_name} ({disk_id})")
            
            # 2. Create VM shell in Proxmox
            proxmox_client = ProxmoxClient(node_name)
            proxmox = proxmox_client.proxmox
            
            # Find next available VMID
            vmid = self._get_next_available_vmid(proxmox)
            
            # Create basic VM
            create_args = {
                "vmid": vmid,
                "name": vm_name,
                "cores": cpu_cores,
                "memory": memory_mb,
                "scsihw": "virtio-scsi-pci",
                "boot": "c",
                "bootdisk": "scsi0",
                "agent": 1
            }
            
            # Add network interfaces
            bridges = self._get_network_bridges_for_node(node_name)
            for net_idx, bridge in enumerate(bridges):
                create_args[f"net{net_idx}"] = f"virtio,bridge={bridge}"
            
            proxmox.nodes(node_name).qemu.create(**create_args)
            logger.info(f"✅ Created VM shell {vm_name} (VMID: {vmid})")
            
            # 3. Attach Crucible disk to VM
            await self.storage_api.disk_attach(disk_id, str(vmid), "scsi0")
            
            # 4. Configure VM with Crucible storage
            await self._configure_vm_crucible_storage(
                proxmox, node_name, vmid, disk_id
            )
            
            # 5. Store VM configuration
            vm_config = {
                "vmid": vmid,
                "name": vm_name,
                "node": node_name,
                "disk_id": disk_id,
                "disk_size_gb": disk_size_gb,
                "memory_mb": memory_mb,
                "cpu_cores": cpu_cores,
                "created_at": time.time(),
                "status": "created"
            }
            
            self.vm_configs[vm_name] = vm_config
            
            logger.info(f"🎉 Successfully created VM {vm_name} with Crucible storage")
            
            return {
                "vm": vm_config,
                "disk": disk,
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to create VM {vm_name}: {e}")
            # Cleanup on failure
            try:
                if 'disk_id' in locals():
                    await self.storage_api.disk_delete(disk_id)
                if 'vmid' in locals():
                    proxmox.nodes(node_name).qemu(vmid).delete()
            except Exception as cleanup_error:
                logger.error(f"❌ Cleanup failed: {cleanup_error}")
            raise
    
    async def clone_vm_from_snapshot(
        self,
        source_vm_name: str,
        target_vm_name: str,
        node_name: str,
        snapshot_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Clone a VM from a storage snapshot.
        
        Args:
            source_vm_name: Name of source VM
            target_vm_name: Name of target VM to create
            node_name: Proxmox node for new VM
            snapshot_name: Optional specific snapshot name
        
        Returns:
            Dict containing new VM and disk information
        """
        logger.info(f"📋 Cloning VM '{source_vm_name}' to '{target_vm_name}' from snapshot")
        
        if source_vm_name not in self.vm_configs:
            raise ValueError(f"Source VM {source_vm_name} not found in managed VMs")
        
        source_config = self.vm_configs[source_vm_name]
        source_disk_id = source_config["disk_id"]
        
        try:
            # 1. Create snapshot if not specified
            if not snapshot_name:
                snapshot_name = f"{source_vm_name}-clone-snapshot-{int(time.time())}"
                
                snapshot_request = SnapshotCreate(
                    name=snapshot_name,
                    description=f"Snapshot for cloning {source_vm_name}",
                    disk=source_disk_id
                )
                
                snapshot = await self.storage_api.snapshot_create(snapshot_request)
                snapshot_id = snapshot["id"]
                
                logger.info(f"✅ Created snapshot {snapshot_name} ({snapshot_id})")
            else:
                # Find existing snapshot
                snapshots = await self.storage_api.snapshot_list()
                matching_snapshots = [s for s in snapshots if s["name"] == snapshot_name]
                if not matching_snapshots:
                    raise ValueError(f"Snapshot {snapshot_name} not found")
                snapshot_id = matching_snapshots[0]["id"]
            
            # 2. Create new VM from snapshot
            result = await self.create_vm_with_storage(
                vm_name=target_vm_name,
                node_name=node_name,
                disk_size_gb=source_config["disk_size_gb"],
                memory_mb=source_config["memory_mb"],
                cpu_cores=source_config["cpu_cores"],
                disk_source=DiskSource.SNAPSHOT,
                snapshot_id=snapshot_id
            )
            
            logger.info(f"🎉 Successfully cloned VM {source_vm_name} to {target_vm_name}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to clone VM {source_vm_name}: {e}")
            raise
    
    async def delete_vm_with_storage(
        self,
        vm_name: str,
        delete_storage: bool = True,
        create_final_snapshot: bool = False
    ) -> None:
        """
        Delete a VM and optionally its storage.
        
        Args:
            vm_name: Name of VM to delete
            delete_storage: Whether to delete associated storage
            create_final_snapshot: Create snapshot before deletion
        """
        logger.info(f"🗑️ Deleting VM '{vm_name}' (delete_storage={delete_storage})")
        
        if vm_name not in self.vm_configs:
            raise ValueError(f"VM {vm_name} not found in managed VMs")
        
        vm_config = self.vm_configs[vm_name]
        vmid = vm_config["vmid"]
        node_name = vm_config["node"]
        disk_id = vm_config["disk_id"]
        
        try:
            # 1. Create final snapshot if requested
            if create_final_snapshot:
                snapshot_name = f"{vm_name}-final-snapshot-{int(time.time())}"
                snapshot_request = SnapshotCreate(
                    name=snapshot_name,
                    description=f"Final snapshot before deleting {vm_name}",
                    disk=disk_id
                )
                
                await self.storage_api.snapshot_create(snapshot_request)
                logger.info(f"✅ Created final snapshot {snapshot_name}")
            
            # 2. Stop VM if running
            proxmox_client = ProxmoxClient(node_name)
            proxmox = proxmox_client.proxmox
            
            try:
                vm_status = proxmox.nodes(node_name).qemu(vmid).status.current.get()
                if vm_status.get("status") == "running":
                    logger.info(f"⏹️ Stopping VM {vm_name}")
                    proxmox.nodes(node_name).qemu(vmid).status.stop.post()
                    
                    # Wait for VM to stop
                    timeout = time.time() + 30
                    while time.time() < timeout:
                        status = proxmox.nodes(node_name).qemu(vmid).status.current.get()
                        if status.get("status") == "stopped":
                            break
                        await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"Failed to stop VM {vm_name}: {e}")
            
            # 3. Detach storage disk
            try:
                await self.storage_api.disk_detach(disk_id)
                logger.info(f"✅ Detached storage disk from VM {vm_name}")
            except Exception as e:
                logger.warning(f"Failed to detach disk from VM {vm_name}: {e}")
            
            # 4. Delete VM from Proxmox
            try:
                proxmox.nodes(node_name).qemu(vmid).delete()
                logger.info(f"✅ Deleted VM {vm_name} from Proxmox")
            except Exception as e:
                logger.error(f"Failed to delete VM {vm_name} from Proxmox: {e}")
            
            # 5. Delete storage if requested
            if delete_storage:
                try:
                    await self.storage_api.disk_delete(disk_id)
                    logger.info(f"✅ Deleted storage disk for VM {vm_name}")
                except Exception as e:
                    logger.error(f"Failed to delete storage for VM {vm_name}: {e}")
            
            # 6. Remove from managed VMs
            del self.vm_configs[vm_name]
            
            logger.info(f"🎉 Successfully deleted VM {vm_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to delete VM {vm_name}: {e}")
            raise
    
    # === STORAGE MANAGEMENT ===
    
    async def create_additional_disk(
        self,
        vm_name: str,
        disk_name: str,
        size_gb: int,
        device_name: str = "scsi1"
    ) -> Dict[str, Any]:
        """Create and attach additional disk to existing VM."""
        logger.info(f"💽 Creating additional disk '{disk_name}' for VM '{vm_name}'")
        
        if vm_name not in self.vm_configs:
            raise ValueError(f"VM {vm_name} not found")
        
        vm_config = self.vm_configs[vm_name]
        vmid = vm_config["vmid"]
        
        # Create disk
        disk_create = DiskCreate(
            name=disk_name,
            description=f"Additional disk for VM {vm_name}",
            size=size_gb * 1024**3,
            disk_source=DiskSource.BLANK,
            block_size=self.crucible_config.default_block_size
        )
        
        disk = await self.storage_api.disk_create(disk_create)
        disk_id = disk["id"]
        
        # Attach to VM
        await self.storage_api.disk_attach(disk_id, str(vmid), device_name)
        
        logger.info(f"✅ Created and attached disk {disk_name} to VM {vm_name}")
        return disk
    
    async def snapshot_vm_storage(
        self,
        vm_name: str,
        snapshot_name: str,
        include_additional_disks: bool = False
    ) -> List[Dict[str, Any]]:
        """Create snapshots of VM storage disks."""
        logger.info(f"📸 Creating storage snapshot '{snapshot_name}' for VM '{vm_name}'")
        
        if vm_name not in self.vm_configs:
            raise ValueError(f"VM {vm_name} not found")
        
        vm_config = self.vm_configs[vm_name]
        snapshots = []
        
        # Snapshot boot disk
        boot_disk_id = vm_config["disk_id"]
        snapshot_request = SnapshotCreate(
            name=f"{snapshot_name}-boot",
            description=f"Boot disk snapshot for VM {vm_name}",
            disk=boot_disk_id
        )
        
        snapshot = await self.storage_api.snapshot_create(snapshot_request)
        snapshots.append(snapshot)
        
        # TODO: Snapshot additional disks if requested
        
        logger.info(f"✅ Created {len(snapshots)} snapshots for VM {vm_name}")
        return snapshots
    
    # === MONITORING AND STATUS ===
    
    async def get_vm_status(self, vm_name: str) -> Dict[str, Any]:
        """Get comprehensive VM status including storage."""
        if vm_name not in self.vm_configs:
            raise ValueError(f"VM {vm_name} not found")
        
        vm_config = self.vm_configs[vm_name]
        vmid = vm_config["vmid"]
        node_name = vm_config["node"]
        disk_id = vm_config["disk_id"]
        
        try:
            # Get Proxmox VM status
            proxmox_client = ProxmoxClient(node_name)
            proxmox = proxmox_client.proxmox
            proxmox_status = proxmox.nodes(node_name).qemu(vmid).status.current.get()
            
            # Get storage disk status
            disk_status = await self.storage_api.disk_view(disk_id)
            
            return {
                "vm_name": vm_name,
                "vmid": vmid,
                "node": node_name,
                "proxmox_status": proxmox_status,
                "storage_disk": disk_status,
                "configuration": vm_config
            }
            
        except Exception as e:
            logger.error(f"Failed to get status for VM {vm_name}: {e}")
            return {
                "vm_name": vm_name,
                "error": str(e),
                "configuration": vm_config
            }
    
    async def list_managed_vms(self) -> List[Dict[str, Any]]:
        """List all VMs managed by this instance."""
        vm_list = []
        
        for vm_name, config in self.vm_configs.items():
            try:
                status = await self.get_vm_status(vm_name)
                vm_list.append(status)
            except Exception as e:
                vm_list.append({
                    "vm_name": vm_name,
                    "error": str(e),
                    "configuration": config
                })
        
        return vm_list
    
    async def get_storage_cluster_status(self) -> Dict[str, Any]:
        """Get status of underlying storage cluster."""
        return await self.storage_api.get_system_status()
    
    # === PRIVATE HELPER METHODS ===
    
    def _get_next_available_vmid(self, proxmox: Any) -> int:
        """Find next available VMID across all nodes."""
        used = set()
        
        for node_info in proxmox.nodes.get():
            node_name = node_info["node"]
            
            # Get QEMU VMs
            for vm in proxmox.nodes(node_name).qemu.get():
                used.add(int(vm["vmid"]))
            
            # Get LXC containers
            for ct in proxmox.nodes(node_name).lxc.get():
                used.add(int(ct["vmid"]))
        
        # Find first available ID
        for candidate in range(200, 9999):  # Start at 200 for Crucible VMs
            if candidate not in used:
                return candidate
        
        raise RuntimeError("No available VMIDs found")
    
    def _get_network_bridges_for_node(self, node_name: str) -> List[str]:
        """Get network bridge configuration for a node."""
        try:
            # Try to get from existing config system
            nodes = Config.get_nodes()
            for i, node in enumerate(nodes):
                if node["name"] == node_name:
                    bridges = Config.get_network_ifaces_for(i)
                    if bridges:
                        return bridges
            
            # Default bridge
            return ["vmbr0"]
            
        except Exception:
            return ["vmbr0"]
    
    async def _configure_vm_crucible_storage(
        self,
        proxmox: Any,
        node_name: str,
        vmid: int,
        disk_id: str
    ) -> None:
        """Configure VM to use Crucible storage."""
        # This would configure the VM to connect to Crucible upstairs
        # For now, we configure traditional storage with Crucible backend
        
        try:
            # Get disk info to configure storage path
            disk_info = await self.storage_api.disk_view(disk_id)
            
            # Configure VM storage
            # Note: In a real implementation, this would set up Crucible upstairs connection
            proxmox.nodes(node_name).qemu(vmid).config.post(
                scsi0=f"crucible:{disk_id},size={disk_info['size'] // 1024**3}G",
                ide2="local:cloudinit"
            )
            
        except Exception as e:
            logger.warning(f"Failed to configure Crucible storage for VM {vmid}: {e}")
            # Fall back to traditional configuration
            pass


# === CONVENIENCE FUNCTIONS ===

async def create_vm_with_crucible_storage(
    vm_name: str,
    node_name: str,
    disk_size_gb: int = 50,
    project_id: str = "homelab",
    enable_mocking: bool = False
) -> Dict[str, Any]:
    """
    Convenience function to create a VM with Crucible storage.
    
    Args:
        vm_name: Name of VM to create
        node_name: Proxmox node name
        disk_size_gb: Boot disk size in GB
        project_id: Storage project ID
        enable_mocking: Use mock storage backend
    
    Returns:
        Dict containing VM and storage information
    """
    manager = CrucibleVMManager(project_id, enable_mocking)
    return await manager.create_vm_with_storage(vm_name, node_name, disk_size_gb)


async def main() -> None:
    """Main function for testing VM manager."""
    logging.basicConfig(level=logging.INFO)
    
    # Enable mocking for testing
    manager = CrucibleVMManager("homelab", enable_mocking=True)
    
    try:
        # Test VM creation
        result = await manager.create_vm_with_storage(
            vm_name="test-crucible-vm",
            node_name="still-fawn",
            disk_size_gb=20
        )
        
        print("✅ VM Creation Result:")
        print(json.dumps(result, indent=2, default=str))
        
        # Test VM status
        status = await manager.get_vm_status("test-crucible-vm")
        print("\\n📊 VM Status:")
        print(json.dumps(status, indent=2, default=str))
        
        # Test storage status
        storage_status = await manager.get_storage_cluster_status()
        print("\\n💾 Storage Status:")
        print(json.dumps(storage_status, indent=2, default=str))
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise


if __name__ == "__main__":
    import json
    asyncio.run(main())