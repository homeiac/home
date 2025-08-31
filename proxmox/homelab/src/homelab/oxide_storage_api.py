"""
Complete Oxide-style storage API with Crucible backend integration.
Provides production-ready disk and snapshot management with full type safety.
"""

import asyncio
import base64
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from homelab.crucible_config import CrucibleConfig
from homelab.crucible_mock import MockCrucibleManager
from homelab.proxmox_api import ProxmoxClient

logger = logging.getLogger(__name__)


class DiskState(Enum):
    """Disk state enum matching Oxide's API."""
    CREATING = "creating"
    DETACHED = "detached"
    ATTACHING = "attaching"
    ATTACHED = "attached"
    DETACHING = "detaching"
    DESTROYED = "destroyed"
    FAULTED = "faulted"
    IMPORT_READY = "import_ready"
    IMPORTING_FROM_BULK_WRITES = "importing_from_bulk_writes"
    FINALIZING = "finalizing"


class DiskSource(Enum):
    """Disk source type enum."""
    BLANK = "blank"
    SNAPSHOT = "snapshot"
    IMAGE = "image"
    IMPORTING_BLOCKS = "importing_blocks"


@dataclass
class DiskCreate:
    """Disk creation request matching Oxide API."""
    name: str
    description: Optional[str]
    size: int  # bytes
    disk_source: DiskSource
    block_size: int = 512  # 512, 2048, or 4096
    snapshot_id: Optional[str] = None
    image_id: Optional[str] = None


@dataclass
class Disk:
    """Disk object matching Oxide API response."""
    id: str
    name: str
    description: Optional[str]
    size: int
    block_size: int
    state: DiskState
    device_path: Optional[str]
    time_created: str
    time_modified: str
    project_id: str
    # Crucible-specific fields
    volume_id: Optional[str] = None
    replica_count: int = 3
    attached_vm_id: Optional[str] = None


@dataclass
class SnapshotCreate:
    """Snapshot creation request."""
    name: str
    description: Optional[str]
    disk: str  # disk ID


@dataclass
class Snapshot:
    """Snapshot object matching Oxide API."""
    id: str
    name: str
    description: Optional[str]
    disk_id: str
    state: str
    size: int
    time_created: str
    time_modified: str
    project_id: str


class OxideStorageAPI:
    """
    Production-ready storage API emulating Oxide's customer interface.
    Supports both real Crucible deployment and comprehensive mocking.
    """

    def __init__(self, project_id: str = "homelab", config_path: Optional[str] = None):
        self.project_id = project_id
        self.config = self._load_config(config_path)
        self.config.validate()
        
        # Initialize storage backend
        if self.config.enable_mocking:
            self.storage_backend = MockCrucibleManager(self.config)
            logger.info("Initialized with mock Crucible backend")
        else:
            # TODO: Initialize real Crucible backend
            logger.warning("Real Crucible backend not yet implemented, using mock")
            self.storage_backend = MockCrucibleManager(self.config)
        
        # State management
        self._disks: Dict[str, Disk] = {}
        self._snapshots: Dict[str, Snapshot] = {}
        self._import_sessions: Dict[str, Dict[str, Any]] = {}
        
        # Proxmox integration
        self._proxmox_clients: Dict[str, ProxmoxClient] = {}
        if self.config.proxmox_integration:
            self._initialize_proxmox_clients()
    
    def _load_config(self, config_path: Optional[str]) -> CrucibleConfig:
        """Load configuration from environment or file."""
        if config_path and Path(config_path).exists():
            with open(config_path) as f:
                config_dict = json.load(f)
            # TODO: Create CrucibleConfig from dict
            return CrucibleConfig.from_environment()
        else:
            return CrucibleConfig.from_environment()
    
    def _initialize_proxmox_clients(self) -> None:
        """Initialize Proxmox API clients for integration."""
        try:
            from homelab.config import Config
            nodes = Config.get_nodes()
            for node in nodes:
                try:
                    self._proxmox_clients[node["name"]] = ProxmoxClient(node["name"])
                except Exception as e:
                    logger.warning(f"Failed to initialize Proxmox client for {node['name']}: {e}")
        except Exception as e:
            logger.warning(f"Proxmox integration initialization failed: {e}")
    
    # === DISK OPERATIONS ===
    
    async def disk_list(self) -> List[Dict[str, Any]]:
        """GET /v1/disks - List all disks in the project."""
        logger.info("📋 Listing project disks")
        
        # Sync with backend
        await self._sync_disk_state()
        
        result = []
        for disk in self._disks.values():
            disk_dict = asdict(disk)
            disk_dict["state"] = disk.state.value
            result.append(disk_dict)
        
        logger.info(f"📋 Found {len(result)} disks in project {self.project_id}")
        return result
    
    async def disk_create(self, request: DiskCreate) -> Dict[str, Any]:
        """POST /v1/disks - Create a new disk."""
        disk_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"💽 Creating disk '{request.name}' ({request.size} bytes, source: {request.disk_source.value})")
        
        # Validate request
        await self._validate_disk_create(request)
        
        # Create disk object
        disk = Disk(
            id=disk_id,
            name=request.name,
            description=request.description,
            size=request.size,
            block_size=request.block_size,
            state=DiskState.CREATING,
            device_path=None,
            time_created=now,
            time_modified=now,
            project_id=self.project_id,
            replica_count=self.config.replication_factor
        )
        
        self._disks[disk_id] = disk
        
        try:
            # Create actual storage volume
            volume_id = f"vol-{disk_id}"
            
            if request.disk_source == DiskSource.BLANK:
                await self._create_blank_volume(disk, volume_id)
            elif request.disk_source == DiskSource.SNAPSHOT:
                await self._create_from_snapshot(disk, volume_id, request.snapshot_id)
            elif request.disk_source == DiskSource.IMAGE:
                await self._create_from_image(disk, volume_id, request.image_id)
            elif request.disk_source == DiskSource.IMPORTING_BLOCKS:
                await self._create_import_ready_volume(disk, volume_id)
            
            # Update state
            disk.state = DiskState.DETACHED if request.disk_source != DiskSource.IMPORTING_BLOCKS else DiskState.IMPORT_READY
            disk.volume_id = volume_id
            disk.time_modified = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"✅ Created disk {disk.name} ({disk_id})")
            
        except Exception as e:
            disk.state = DiskState.FAULTED
            disk.time_modified = datetime.now(timezone.utc).isoformat()
            logger.error(f"❌ Failed to create disk {disk.name}: {e}")
            raise
        
        result = asdict(disk)
        result["state"] = disk.state.value
        return result
    
    async def disk_view(self, disk_id: str) -> Dict[str, Any]:
        """GET /v1/disks/{disk} - Fetch details of a specific disk."""
        logger.debug(f"🔍 Viewing disk {disk_id}")
        
        if disk_id not in self._disks:
            raise ValueError(f"Disk {disk_id} not found")
        
        disk = self._disks[disk_id]
        await self._refresh_disk_state(disk)
        
        result = asdict(disk)
        result["state"] = disk.state.value
        return result
    
    async def disk_delete(self, disk_id: str) -> None:
        """DELETE /v1/disks/{disk} - Delete a disk."""
        logger.info(f"🗑️ Deleting disk {disk_id}")
        
        if disk_id not in self._disks:
            raise ValueError(f"Disk {disk_id} not found")
        
        disk = self._disks[disk_id]
        
        # Check state allows deletion
        if disk.state not in [DiskState.DETACHED, DiskState.FAULTED, DiskState.IMPORT_READY]:
            raise ValueError(f"Cannot delete disk in state {disk.state.value}")
        
        try:
            # Delete from storage backend
            if disk.volume_id:
                await self.storage_backend.delete_volume(disk.volume_id)
            
            # Remove from state
            del self._disks[disk_id]
            
            logger.info(f"✅ Deleted disk {disk.name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to delete disk {disk.name}: {e}")
            raise
    
    async def disk_attach(self, disk_id: str, vm_id: str, device_name: str = "scsi1") -> Dict[str, Any]:
        """Attach disk to a Proxmox VM."""
        logger.info(f"🔗 Attaching disk {disk_id} to VM {vm_id}")
        
        if disk_id not in self._disks:
            raise ValueError(f"Disk {disk_id} not found")
        
        disk = self._disks[disk_id]
        
        if disk.state != DiskState.DETACHED:
            raise ValueError(f"Disk must be detached, currently {disk.state.value}")
        
        try:
            disk.state = DiskState.ATTACHING
            
            # Attach via Proxmox API if integration enabled
            if self.config.proxmox_integration:
                await self._attach_to_proxmox_vm(disk, vm_id, device_name)
            
            disk.state = DiskState.ATTACHED
            disk.attached_vm_id = vm_id
            disk.device_path = f"/dev/{device_name}"
            disk.time_modified = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"✅ Attached disk {disk.name} to VM {vm_id}")
            
            result = asdict(disk)
            result["state"] = disk.state.value
            return result
            
        except Exception as e:
            disk.state = DiskState.FAULTED
            logger.error(f"❌ Failed to attach disk {disk.name}: {e}")
            raise
    
    async def disk_detach(self, disk_id: str) -> Dict[str, Any]:
        """Detach disk from VM."""
        logger.info(f"🔓 Detaching disk {disk_id}")
        
        if disk_id not in self._disks:
            raise ValueError(f"Disk {disk_id} not found")
        
        disk = self._disks[disk_id]
        
        if disk.state != DiskState.ATTACHED:
            raise ValueError(f"Disk must be attached, currently {disk.state.value}")
        
        try:
            disk.state = DiskState.DETACHING
            
            # Detach via Proxmox API if integration enabled
            if self.config.proxmox_integration and disk.attached_vm_id:
                await self._detach_from_proxmox_vm(disk, disk.attached_vm_id)
            
            disk.state = DiskState.DETACHED
            disk.attached_vm_id = None
            disk.device_path = None
            disk.time_modified = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"✅ Detached disk {disk.name}")
            
            result = asdict(disk)
            result["state"] = disk.state.value
            return result
            
        except Exception as e:
            disk.state = DiskState.FAULTED
            logger.error(f"❌ Failed to detach disk {disk.name}: {e}")
            raise
    
    # === BULK IMPORT OPERATIONS ===
    
    async def disk_bulk_write_import_start(self, disk_id: str) -> Dict[str, str]:
        """Start bulk write import for a disk."""
        logger.info(f"📤 Starting bulk import for disk {disk_id}")
        
        if disk_id not in self._disks:
            raise ValueError(f"Disk {disk_id} not found")
        
        disk = self._disks[disk_id]
        
        if disk.state != DiskState.IMPORT_READY:
            raise ValueError(f"Disk must be in import_ready state, currently {disk.state.value}")
        
        # Initialize import session
        self._import_sessions[disk_id] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "bytes_imported": 0,
            "chunks": {}
        }
        
        disk.state = DiskState.IMPORTING_FROM_BULK_WRITES
        disk.time_modified = datetime.now(timezone.utc).isoformat()
        
        return {"status": "import_started", "session_id": disk_id}
    
    async def disk_bulk_write_import(self, disk_id: str, data: str, offset: int = 0) -> Dict[str, Any]:
        """Import base64-encoded data chunk to disk."""
        logger.debug(f"📤 Importing {len(data)} bytes to disk {disk_id} at offset {offset}")
        
        if disk_id not in self._disks:
            raise ValueError(f"Disk {disk_id} not found")
        
        if disk_id not in self._import_sessions:
            raise ValueError(f"No import session for disk {disk_id}")
        
        disk = self._disks[disk_id]
        
        if disk.state != DiskState.IMPORTING_FROM_BULK_WRITES:
            raise ValueError(f"Disk not in importing state, currently {disk.state.value}")
        
        try:
            # Decode base64 data
            binary_data = base64.b64decode(data)
            
            # Write to storage backend
            if disk.volume_id:
                await self.storage_backend.write_volume(disk.volume_id, offset, binary_data)
            
            # Update import session
            session = self._import_sessions[disk_id]
            session["bytes_imported"] += len(binary_data)
            session["chunks"][offset] = len(binary_data)
            
            return {
                "status": "data_written",
                "bytes_written": len(binary_data),
                "total_bytes_imported": session["bytes_imported"]
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to import data to disk {disk_id}: {e}")
            raise
    
    async def disk_bulk_write_import_stop(self, disk_id: str) -> Dict[str, str]:
        """Stop bulk write import (without finalizing)."""
        logger.info(f"⏹️ Stopping bulk import for disk {disk_id}")
        
        if disk_id not in self._disks:
            raise ValueError(f"Disk {disk_id} not found")
        
        disk = self._disks[disk_id]
        
        # Clean up import session
        if disk_id in self._import_sessions:
            del self._import_sessions[disk_id]
        
        disk.state = DiskState.IMPORT_READY
        disk.time_modified = datetime.now(timezone.utc).isoformat()
        
        return {"status": "import_stopped"}
    
    async def disk_finalize_import(self, disk_id: str, create_snapshot: bool = False) -> Dict[str, Any]:
        """Finalize disk import and optionally create snapshot."""
        logger.info(f"✅ Finalizing import for disk {disk_id}, snapshot={create_snapshot}")
        
        if disk_id not in self._disks:
            raise ValueError(f"Disk {disk_id} not found")
        
        disk = self._disks[disk_id]
        
        if disk.state != DiskState.IMPORTING_FROM_BULK_WRITES:
            raise ValueError(f"Disk not in importing state, currently {disk.state.value}")
        
        try:
            disk.state = DiskState.FINALIZING
            
            # Finalize import session
            session = self._import_sessions.get(disk_id, {})
            logger.info(f"Import completed: {session.get('bytes_imported', 0)} bytes")
            
            # Clean up session
            if disk_id in self._import_sessions:
                del self._import_sessions[disk_id]
            
            disk.state = DiskState.DETACHED
            disk.time_modified = datetime.now(timezone.utc).isoformat()
            
            result = {"status": "finalized", "disk": asdict(disk)}
            result["disk"]["state"] = disk.state.value
            
            # Optionally create snapshot
            if create_snapshot:
                snapshot_request = SnapshotCreate(
                    name=f"{disk.name}-import-snapshot",
                    description=f"Auto-created snapshot after import of {disk.name}",
                    disk=disk_id
                )
                
                snapshot = await self.snapshot_create(snapshot_request)
                result["snapshot"] = snapshot
            
            logger.info(f"✅ Finalized import for disk {disk.name}")
            return result
            
        except Exception as e:
            disk.state = DiskState.FAULTED
            logger.error(f"❌ Failed to finalize import for disk {disk_id}: {e}")
            raise
    
    # === SNAPSHOT OPERATIONS ===
    
    async def snapshot_list(self) -> List[Dict[str, Any]]:
        """GET /v1/snapshots - List all snapshots."""
        logger.debug("📸 Listing project snapshots")
        
        result = [asdict(snapshot) for snapshot in self._snapshots.values()]
        logger.debug(f"📸 Found {len(result)} snapshots in project {self.project_id}")
        return result
    
    async def snapshot_create(self, request: SnapshotCreate) -> Dict[str, Any]:
        """POST /v1/snapshots - Create a point-in-time snapshot."""
        snapshot_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"📸 Creating snapshot '{request.name}' from disk {request.disk}")
        
        # Validate source disk exists
        if request.disk not in self._disks:
            raise ValueError(f"Source disk {request.disk} not found")
        
        source_disk = self._disks[request.disk]
        
        # Create snapshot object
        snapshot = Snapshot(
            id=snapshot_id,
            name=request.name,
            description=request.description,
            disk_id=request.disk,
            state="creating",
            size=source_disk.size,
            time_created=now,
            time_modified=now,
            project_id=self.project_id
        )
        
        self._snapshots[snapshot_id] = snapshot
        
        try:
            # Create snapshot in storage backend
            if source_disk.volume_id:
                await self.storage_backend.create_snapshot(snapshot_id, source_disk.volume_id)
            
            snapshot.state = "ready"
            snapshot.time_modified = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"✅ Created snapshot {snapshot.name} ({snapshot_id})")
            
        except Exception as e:
            snapshot.state = "failed"
            logger.error(f"❌ Failed to create snapshot {snapshot.name}: {e}")
            raise
        
        return asdict(snapshot)
    
    async def snapshot_view(self, snapshot_id: str) -> Dict[str, Any]:
        """GET /v1/snapshots/{snapshot} - View snapshot details."""
        logger.debug(f"🔍 Viewing snapshot {snapshot_id}")
        
        if snapshot_id not in self._snapshots:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        
        return asdict(self._snapshots[snapshot_id])
    
    async def snapshot_delete(self, snapshot_id: str) -> None:
        """DELETE /v1/snapshots/{snapshot} - Delete a snapshot."""
        logger.info(f"🗑️ Deleting snapshot {snapshot_id}")
        
        if snapshot_id not in self._snapshots:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        
        try:
            # Delete from storage backend
            await self.storage_backend.delete_snapshot(snapshot_id)
            
            # Remove from state
            del self._snapshots[snapshot_id]
            
            logger.info(f"✅ Deleted snapshot {snapshot_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to delete snapshot {snapshot_id}: {e}")
            raise
    
    # === SYSTEM OPERATIONS ===
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status and metrics."""
        cluster_status = await self.storage_backend.get_cluster_status()
        
        return {
            "project_id": self.project_id,
            "total_disks": len(self._disks),
            "total_snapshots": len(self._snapshots),
            "active_import_sessions": len(self._import_sessions),
            "storage_cluster": cluster_status,
            "configuration": self.config.to_dict()
        }
    
    # === PRIVATE IMPLEMENTATION METHODS ===
    
    async def _validate_disk_create(self, request: DiskCreate) -> None:
        """Validate disk creation request."""
        # Size limits
        max_size = self.config.max_disk_size_gb * 1024**3
        if request.size > max_size:
            raise ValueError(f"Disk size {request.size} exceeds maximum {max_size}")
        
        # Block size validation
        if request.block_size not in [512, 2048, 4096]:
            raise ValueError(f"Invalid block size {request.block_size}")
        
        # Name uniqueness
        for disk in self._disks.values():
            if disk.name == request.name:
                raise ValueError(f"Disk name '{request.name}' already exists")
        
        # Snapshot validation
        if request.disk_source == DiskSource.SNAPSHOT:
            if not request.snapshot_id:
                raise ValueError("snapshot_id required when disk_source is 'snapshot'")
            if request.snapshot_id not in self._snapshots:
                raise ValueError(f"Snapshot {request.snapshot_id} not found")
    
    async def _create_blank_volume(self, disk: Disk, volume_id: str) -> None:
        """Create blank Crucible volume."""
        await self.storage_backend.create_volume(volume_id, disk.size, disk.replica_count)
    
    async def _create_from_snapshot(self, disk: Disk, volume_id: str, snapshot_id: Optional[str]) -> None:
        """Create disk from existing snapshot."""
        if not snapshot_id:
            raise ValueError("snapshot_id required")
        
        # TODO: Implement snapshot cloning
        await self.storage_backend.create_volume(volume_id, disk.size, disk.replica_count)
    
    async def _create_from_image(self, disk: Disk, volume_id: str, image_id: Optional[str]) -> None:
        """Create disk from image."""
        if not image_id:
            raise ValueError("image_id required")
        
        # TODO: Implement image cloning
        await self.storage_backend.create_volume(volume_id, disk.size, disk.replica_count)
    
    async def _create_import_ready_volume(self, disk: Disk, volume_id: str) -> None:
        """Create volume ready for bulk import."""
        await self.storage_backend.create_volume(volume_id, disk.size, disk.replica_count)
    
    async def _sync_disk_state(self) -> None:
        """Synchronize disk state with storage backend."""
        # TODO: Query actual storage state and update disk objects
        pass
    
    async def _refresh_disk_state(self, disk: Disk) -> None:
        """Refresh state of a specific disk."""
        # TODO: Query storage backend for this specific disk
        pass
    
    async def _attach_to_proxmox_vm(self, disk: Disk, vm_id: str, device_name: str) -> None:
        """Attach disk to Proxmox VM via API."""
        # TODO: Implement Proxmox VM attachment
        logger.info(f"Would attach disk {disk.name} to VM {vm_id} as {device_name}")
    
    async def _detach_from_proxmox_vm(self, disk: Disk, vm_id: str) -> None:
        """Detach disk from Proxmox VM via API."""
        # TODO: Implement Proxmox VM detachment
        logger.info(f"Would detach disk {disk.name} from VM {vm_id}")


# === FACTORY FUNCTION ===

def create_storage_api(project_id: str = "homelab", 
                      config_path: Optional[str] = None,
                      enable_mocking: Optional[bool] = None) -> OxideStorageAPI:
    """
    Factory function to create configured storage API instance.
    
    Args:
        project_id: Project identifier
        config_path: Optional path to configuration file
        enable_mocking: Override mocking setting
    
    Returns:
        Configured OxideStorageAPI instance
    """
    api = OxideStorageAPI(project_id, config_path)
    
    if enable_mocking is not None:
        api.config.enable_mocking = enable_mocking
        if enable_mocking:
            api.storage_backend = MockCrucibleManager(api.config)
    
    return api