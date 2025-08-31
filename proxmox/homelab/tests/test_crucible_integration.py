"""
Comprehensive test suite for Crucible storage integration.
Tests all components with both unit and integration scenarios.
"""

import asyncio
import json
import pytest
import random
import string
import uuid
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

from homelab.crucible_config import CrucibleConfig, CrucibleStorageSled
from homelab.crucible_mock import MockCrucibleManager
from homelab.enhanced_vm_manager import CrucibleVMManager
from homelab.oxide_storage_api import (
    DiskCreate,
    DiskSource,
    DiskState,
    OxideStorageAPI,
    SnapshotCreate,
    create_storage_api
)


class TestCrucibleConfig:
    """Test configuration management."""
    
    def test_config_creation(self):
        """Test basic configuration creation."""
        config = CrucibleConfig()
        assert config.deployment_mode == "development"
        assert config.replication_factor == 3
        assert config.default_block_size == 512
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Valid configuration
        config = CrucibleConfig(storage_sleds=[
            CrucibleStorageSled("192.168.4.200", "sled1"),
            CrucibleStorageSled("192.168.4.201", "sled2"),
            CrucibleStorageSled("192.168.4.202", "sled3")
        ])
        config.validate()  # Should not raise
        
        # Invalid: no sleds
        config_no_sleds = CrucibleConfig(storage_sleds=[])
        with pytest.raises(ValueError, match="At least one storage sled"):
            config_no_sleds.validate()
        
        # Invalid: replication > sleds
        config_bad_replication = CrucibleConfig(
            storage_sleds=[CrucibleStorageSled("192.168.4.200", "sled1")],
            replication_factor=3
        )
        with pytest.raises(ValueError, match="Replication factor"):
            config_bad_replication.validate()
    
    def test_config_serialization(self):
        """Test configuration serialization."""
        config = CrucibleConfig(storage_sleds=[
            CrucibleStorageSled("192.168.4.200", "sled1")
        ])
        
        config_dict = config.to_dict()
        assert isinstance(config_dict, dict)
        assert "storage_sleds" in config_dict
        assert len(config_dict["storage_sleds"]) == 1


class TestMockCrucibleManager:
    """Test mock Crucible storage implementation."""
    
    @pytest.fixture
    async def mock_manager(self):
        """Create mock Crucible manager for testing."""
        config = CrucibleConfig(
            storage_sleds=[
                CrucibleStorageSled("192.168.4.200", "sled1"),
                CrucibleStorageSled("192.168.4.201", "sled2"),
                CrucibleStorageSled("192.168.4.202", "sled3")
            ],
            enable_mocking=True
        )
        return MockCrucibleManager(config)
    
    async def test_sled_discovery(self, mock_manager):
        """Test storage sled discovery."""
        sleds = await mock_manager.discover_sleds()
        assert len(sleds) == 3
        
        for sled_ip, sled_info in sleds.items():
            assert sled_info["is_online"] is True
            assert "total_capacity_bytes" in sled_info
            assert "used_capacity_bytes" in sled_info
    
    async def test_volume_lifecycle(self, mock_manager):
        """Test complete volume lifecycle."""
        volume_id = str(uuid.uuid4())
        size_bytes = 1024**3  # 1GB
        
        # Create volume
        volume_info = await mock_manager.create_volume(volume_id, size_bytes)
        assert volume_info["id"] == volume_id
        assert volume_info["size_bytes"] == size_bytes
        assert len(volume_info["replicas"]) == 3  # Default replication factor
        
        # Read/write data
        test_data = b"Hello Crucible!"
        await mock_manager.write_volume(volume_id, 0, test_data)
        read_data = await mock_manager.read_volume(volume_id, 0, len(test_data))
        assert len(read_data) == len(test_data)  # Mock returns zeros, but length matches
        
        # Get volume info
        info = await mock_manager.get_volume_info(volume_id)
        assert info["id"] == volume_id
        
        # Delete volume
        await mock_manager.delete_volume(volume_id)
        
        with pytest.raises(ValueError, match="not found"):
            await mock_manager.get_volume_info(volume_id)
    
    async def test_snapshot_lifecycle(self, mock_manager):
        """Test snapshot creation and deletion."""
        # Create volume first
        volume_id = str(uuid.uuid4())
        await mock_manager.create_volume(volume_id, 1024**3)
        
        # Create snapshot
        snapshot_id = str(uuid.uuid4())
        snapshot_info = await mock_manager.create_snapshot(snapshot_id, volume_id)
        assert snapshot_info["id"] == snapshot_id
        assert snapshot_info["volume_id"] == volume_id
        
        # List snapshots
        snapshots = await mock_manager.list_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0]["id"] == snapshot_id
        
        # Delete snapshot
        await mock_manager.delete_snapshot(snapshot_id)
        snapshots = await mock_manager.list_snapshots()
        assert len(snapshots) == 0
        
        # Cleanup
        await mock_manager.delete_volume(volume_id)
    
    async def test_sled_failure_simulation(self, mock_manager):
        """Test sled failure and recovery simulation."""
        # All sleds should be online initially
        status = await mock_manager.get_cluster_status()
        assert status["online_sleds"] == 3
        
        # Simulate sled failure
        await mock_manager.simulate_sled_failure("192.168.4.200")
        status = await mock_manager.get_cluster_status()
        assert status["online_sleds"] == 2
        assert status["offline_sleds"] == 1
        
        # Simulate sled recovery
        await mock_manager.simulate_sled_recovery("192.168.4.200")
        status = await mock_manager.get_cluster_status()
        assert status["online_sleds"] == 3
        assert status["offline_sleds"] == 0


class TestOxideStorageAPI:
    """Test Oxide-style storage API."""
    
    @pytest.fixture
    async def storage_api(self):
        """Create storage API with mocking enabled."""
        return create_storage_api("test-project", enable_mocking=True)
    
    @pytest.fixture
    def sample_disk_create(self):
        """Sample disk creation request."""
        return DiskCreate(
            name=f"test-disk-{self._random_suffix()}",
            description="Test disk for API validation",
            size=1024**3,  # 1GB
            disk_source=DiskSource.BLANK,
            block_size=512
        )
    
    def _random_suffix(self) -> str:
        """Generate random suffix for test names."""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    
    async def test_disk_creation_and_deletion(self, storage_api, sample_disk_create):
        """Test basic disk lifecycle."""
        # Create disk
        disk = await storage_api.disk_create(sample_disk_create)
        assert disk["name"] == sample_disk_create.name
        assert disk["size"] == sample_disk_create.size
        assert disk["state"] == DiskState.DETACHED.value
        
        disk_id = disk["id"]
        
        # View disk
        viewed_disk = await storage_api.disk_view(disk_id)
        assert viewed_disk["id"] == disk_id
        assert viewed_disk["name"] == sample_disk_create.name
        
        # List disks
        disks = await storage_api.disk_list()
        disk_names = [d["name"] for d in disks]
        assert sample_disk_create.name in disk_names
        
        # Delete disk
        await storage_api.disk_delete(disk_id)
        
        # Verify deletion
        with pytest.raises(ValueError, match="not found"):
            await storage_api.disk_view(disk_id)
    
    async def test_bulk_import_workflow(self, storage_api):
        """Test bulk import functionality."""
        # Create import-ready disk
        import_disk = DiskCreate(
            name=f"import-disk-{self._random_suffix()}",
            description="Test import disk",
            size=1024**2,  # 1MB
            disk_source=DiskSource.IMPORTING_BLOCKS
        )
        
        disk = await storage_api.disk_create(import_disk)
        disk_id = disk["id"]
        assert disk["state"] == DiskState.IMPORT_READY.value
        
        # Start import
        start_result = await storage_api.disk_bulk_write_import_start(disk_id)
        assert start_result["status"] == "import_started"
        
        # Import data
        import json
        test_data = {"message": "Hello Crucible Import!"}
        data_bytes = json.dumps(test_data).encode()
        import base64
        encoded_data = base64.b64encode(data_bytes).decode()
        
        import_result = await storage_api.disk_bulk_write_import(disk_id, encoded_data)
        assert import_result["status"] == "data_written"
        
        # Finalize import
        finalize_result = await storage_api.disk_finalize_import(disk_id, create_snapshot=True)
        assert finalize_result["status"] == "finalized"
        assert finalize_result["disk"]["state"] == DiskState.DETACHED.value
        assert "snapshot" in finalize_result
        
        # Cleanup
        await storage_api.snapshot_delete(finalize_result["snapshot"]["id"])
        await storage_api.disk_delete(disk_id)
    
    async def test_snapshot_operations(self, storage_api, sample_disk_create):
        """Test snapshot creation and management."""
        # Create source disk
        disk = await storage_api.disk_create(sample_disk_create)
        disk_id = disk["id"]
        
        # Create snapshot
        snapshot_request = SnapshotCreate(
            name=f"test-snapshot-{self._random_suffix()}",
            description="Test snapshot",
            disk=disk_id
        )
        
        snapshot = await storage_api.snapshot_create(snapshot_request)
        snapshot_id = snapshot["id"]
        assert snapshot["disk_id"] == disk_id
        assert snapshot["state"] == "ready"
        
        # List snapshots
        snapshots = await storage_api.snapshot_list()
        snapshot_names = [s["name"] for s in snapshots]
        assert snapshot_request.name in snapshot_names
        
        # View snapshot
        viewed_snapshot = await storage_api.snapshot_view(snapshot_id)
        assert viewed_snapshot["id"] == snapshot_id
        
        # Delete snapshot and disk
        await storage_api.snapshot_delete(snapshot_id)
        await storage_api.disk_delete(disk_id)
    
    async def test_error_handling(self, storage_api):
        """Test API error handling."""
        # Test disk size limits
        oversized_disk = DiskCreate(
            name="oversized-disk",
            description="Should fail",
            size=2000 * 1024**3,  # 2000 GB
            disk_source=DiskSource.BLANK
        )
        
        with pytest.raises(ValueError, match="exceeds maximum"):
            await storage_api.disk_create(oversized_disk)
        
        # Test invalid block size
        invalid_block_disk = DiskCreate(
            name="invalid-block",
            description="Should fail",
            size=1024**3,
            disk_source=DiskSource.BLANK,
            block_size=1024  # Invalid
        )
        
        with pytest.raises(ValueError, match="Invalid block size"):
            await storage_api.disk_create(invalid_block_disk)
    
    async def test_system_status(self, storage_api):
        """Test system status reporting."""
        status = await storage_api.get_system_status()
        
        assert "project_id" in status
        assert "total_disks" in status
        assert "storage_cluster" in status
        assert "configuration" in status
        
        cluster_status = status["storage_cluster"]
        assert "total_sleds" in cluster_status
        assert "online_sleds" in cluster_status


class TestCrucibleVMManager:
    """Test enhanced VM manager with Crucible integration."""
    
    @pytest.fixture
    async def vm_manager(self):
        """Create VM manager with mocking enabled."""
        return CrucibleVMManager("test-project", enable_mocking=True)
    
    @pytest.fixture
    def mock_proxmox_client(self):
        """Mock Proxmox client for testing."""
        mock_client = MagicMock()
        mock_proxmox = MagicMock()
        mock_client.proxmox = mock_proxmox
        
        # Mock node operations
        mock_proxmox.nodes.get.return_value = [{"node": "test-node"}]
        mock_proxmox.nodes.return_value.qemu.get.return_value = []
        mock_proxmox.nodes.return_value.lxc.get.return_value = []
        mock_proxmox.nodes.return_value.qemu.create = MagicMock()
        mock_proxmox.nodes.return_value.qemu.return_value.config.post = MagicMock()
        mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.return_value = {"status": "stopped"}
        
        return mock_client
    
    async def test_vm_creation_with_storage(self, vm_manager, mock_proxmox_client):
        """Test VM creation with Crucible storage."""
        with patch('homelab.enhanced_vm_manager.ProxmoxClient', return_value=mock_proxmox_client):
            result = await vm_manager.create_vm_with_storage(
                vm_name="test-crucible-vm",
                node_name="test-node",
                disk_size_gb=20,
                memory_mb=2048,
                cpu_cores=2
            )
            
            assert result["status"] == "success"
            assert "vm" in result
            assert "disk" in result
            
            vm_info = result["vm"]
            assert vm_info["name"] == "test-crucible-vm"
            assert vm_info["node"] == "test-node"
            assert vm_info["disk_size_gb"] == 20
            
            disk_info = result["disk"]
            assert disk_info["size"] == 20 * 1024**3  # GB to bytes
            assert disk_info["state"] == DiskState.ATTACHED.value
    
    async def test_vm_cloning_from_snapshot(self, vm_manager, mock_proxmox_client):
        """Test VM cloning from storage snapshot."""
        with patch('homelab.enhanced_vm_manager.ProxmoxClient', return_value=mock_proxmox_client):
            # First create source VM
            source_result = await vm_manager.create_vm_with_storage(
                vm_name="source-vm",
                node_name="test-node",
                disk_size_gb=10
            )
            
            # Clone VM
            clone_result = await vm_manager.clone_vm_from_snapshot(
                source_vm_name="source-vm",
                target_vm_name="clone-vm",
                node_name="test-node"
            )
            
            assert clone_result["status"] == "success"
            
            clone_vm = clone_result["vm"]
            assert clone_vm["name"] == "clone-vm"
            assert clone_vm["disk_size_gb"] == 10  # Same as source
    
    async def test_additional_disk_creation(self, vm_manager, mock_proxmox_client):
        """Test adding additional disks to existing VM."""
        with patch('homelab.enhanced_vm_manager.ProxmoxClient', return_value=mock_proxmox_client):
            # Create VM first
            await vm_manager.create_vm_with_storage(
                vm_name="test-vm",
                node_name="test-node",
                disk_size_gb=20
            )
            
            # Add additional disk
            additional_disk = await vm_manager.create_additional_disk(
                vm_name="test-vm",
                disk_name="test-vm-data-disk",
                size_gb=50,
                device_name="scsi1"
            )
            
            assert additional_disk["name"] == "test-vm-data-disk"
            assert additional_disk["size"] == 50 * 1024**3
    
    async def test_vm_storage_snapshot(self, vm_manager, mock_proxmox_client):
        """Test creating snapshots of VM storage."""
        with patch('homelab.enhanced_vm_manager.ProxmoxClient', return_value=mock_proxmox_client):
            # Create VM
            await vm_manager.create_vm_with_storage(
                vm_name="test-vm",
                node_name="test-node",
                disk_size_gb=20
            )
            
            # Create storage snapshot
            snapshots = await vm_manager.snapshot_vm_storage(
                vm_name="test-vm",
                snapshot_name="test-snapshot"
            )
            
            assert len(snapshots) >= 1
            boot_snapshot = snapshots[0]
            assert "test-snapshot-boot" in boot_snapshot["name"]
    
    async def test_vm_status_reporting(self, vm_manager, mock_proxmox_client):
        """Test VM status reporting."""
        with patch('homelab.enhanced_vm_manager.ProxmoxClient', return_value=mock_proxmox_client):
            # Create VM
            await vm_manager.create_vm_with_storage(
                vm_name="test-vm",
                node_name="test-node",
                disk_size_gb=20
            )
            
            # Get VM status
            status = await vm_manager.get_vm_status("test-vm")
            
            assert status["vm_name"] == "test-vm"
            assert "configuration" in status
            assert "storage_disk" in status
    
    async def test_managed_vm_listing(self, vm_manager, mock_proxmox_client):
        """Test listing all managed VMs."""
        with patch('homelab.enhanced_vm_manager.ProxmoxClient', return_value=mock_proxmox_client):
            # Create multiple VMs
            vm_names = ["test-vm-1", "test-vm-2"]
            for vm_name in vm_names:
                await vm_manager.create_vm_with_storage(
                    vm_name=vm_name,
                    node_name="test-node",
                    disk_size_gb=20
                )
            
            # List managed VMs
            vm_list = await vm_manager.list_managed_vms()
            
            assert len(vm_list) == 2
            listed_names = [vm["vm_name"] for vm in vm_list]
            for name in vm_names:
                assert name in listed_names
    
    async def test_storage_cluster_status(self, vm_manager):
        """Test storage cluster status reporting."""
        status = await vm_manager.get_storage_cluster_status()
        
        assert "project_id" in status
        assert "storage_cluster" in status
        
        cluster_info = status["storage_cluster"]
        assert "total_sleds" in cluster_info
        assert "online_sleds" in cluster_info


class TestIntegrationScenarios:
    """Integration tests for complete workflows."""
    
    @pytest.fixture
    async def full_setup(self):
        """Set up complete test environment."""
        vm_manager = CrucibleVMManager("integration-test", enable_mocking=True)
        storage_api = vm_manager.storage_api
        
        return {
            "vm_manager": vm_manager,
            "storage_api": storage_api
        }
    
    async def test_complete_vm_lifecycle_with_storage(self, full_setup):
        """Test complete VM lifecycle including storage operations."""
        vm_manager = full_setup["vm_manager"]
        storage_api = full_setup["storage_api"]
        
        with patch('homelab.enhanced_vm_manager.ProxmoxClient') as mock_client_class:
            # Mock Proxmox client
            mock_client = MagicMock()
            mock_proxmox = MagicMock()
            mock_client.proxmox = mock_proxmox
            mock_client_class.return_value = mock_client
            
            # Configure mock responses
            mock_proxmox.nodes.get.return_value = [{"node": "test-node"}]
            mock_proxmox.nodes.return_value.qemu.get.return_value = []
            mock_proxmox.nodes.return_value.lxc.get.return_value = []
            mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.return_value = {"status": "stopped"}
            
            vm_name = "integration-test-vm"
            
            # 1. Create VM with storage
            create_result = await vm_manager.create_vm_with_storage(
                vm_name=vm_name,
                node_name="test-node",
                disk_size_gb=30
            )
            
            assert create_result["status"] == "success"
            
            # 2. Create additional disk
            additional_disk = await vm_manager.create_additional_disk(
                vm_name=vm_name,
                disk_name=f"{vm_name}-data",
                size_gb=100
            )
            
            assert additional_disk["name"] == f"{vm_name}-data"
            
            # 3. Create storage snapshot
            snapshots = await vm_manager.snapshot_vm_storage(
                vm_name=vm_name,
                snapshot_name="integration-snapshot"
            )
            
            assert len(snapshots) >= 1
            
            # 4. Clone VM from snapshot
            clone_result = await vm_manager.clone_vm_from_snapshot(
                source_vm_name=vm_name,
                target_vm_name=f"{vm_name}-clone",
                node_name="test-node"
            )
            
            assert clone_result["status"] == "success"
            
            # 5. Verify both VMs exist
            vm_list = await vm_manager.list_managed_vms()
            vm_names_in_list = [vm["vm_name"] for vm in vm_list]
            assert vm_name in vm_names_in_list
            assert f"{vm_name}-clone" in vm_names_in_list
            
            # 6. Check storage cluster status
            cluster_status = await vm_manager.get_storage_cluster_status()
            assert cluster_status["storage_cluster"]["total_volumes"] >= 3  # Boot + data + clone boot
    
    async def test_failure_recovery_scenarios(self, full_setup):
        """Test failure handling and recovery."""
        vm_manager = full_setup["vm_manager"]
        storage_api = full_setup["storage_api"]
        
        # Simulate storage sled failure
        mock_manager = storage_api.storage_backend
        
        # Create volume on healthy cluster
        volume_id = str(uuid.uuid4())
        await mock_manager.create_volume(volume_id, 1024**3)
        
        # Simulate sled failure
        await mock_manager.simulate_sled_failure("192.168.4.200")
        
        # Verify cluster still operational
        cluster_status = await mock_manager.get_cluster_status()
        assert cluster_status["online_sleds"] == 2
        
        # Verify volume still readable (should work with remaining replicas)
        data = await mock_manager.read_volume(volume_id, 0, 1024)
        assert len(data) == 1024
        
        # Simulate sled recovery
        await mock_manager.simulate_sled_recovery("192.168.4.200")
        
        # Verify full cluster recovery
        cluster_status = await mock_manager.get_cluster_status()
        assert cluster_status["online_sleds"] == 3
        
        # Cleanup
        await mock_manager.delete_volume(volume_id)


# === PYTEST CONFIGURATION ===

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# === PERFORMANCE TESTS ===

class TestPerformanceCharacteristics:
    """Performance and load testing."""
    
    @pytest.mark.asyncio
    async def test_concurrent_disk_operations(self):
        """Test concurrent disk creation and deletion."""
        storage_api = create_storage_api("perf-test", enable_mocking=True)
        
        # Create multiple disks concurrently
        disk_count = 10
        tasks = []
        
        for i in range(disk_count):
            disk_request = DiskCreate(
                name=f"perf-disk-{i}",
                description="Performance test disk",
                size=100 * 1024**2,  # 100MB
                disk_source=DiskSource.BLANK
            )
            tasks.append(storage_api.disk_create(disk_request))
        
        # Execute all creations concurrently
        results = await asyncio.gather(*tasks)
        
        assert len(results) == disk_count
        for result in results:
            assert result["state"] == DiskState.DETACHED.value
        
        # Clean up all disks concurrently
        cleanup_tasks = [storage_api.disk_delete(result["id"]) for result in results]
        await asyncio.gather(*cleanup_tasks)
    
    @pytest.mark.asyncio
    async def test_large_data_import(self):
        """Test bulk import with larger data sets."""
        storage_api = create_storage_api("import-test", enable_mocking=True)
        
        # Create import disk
        disk_request = DiskCreate(
            name="large-import-disk",
            description="Large data import test",
            size=10 * 1024**2,  # 10MB
            disk_source=DiskSource.IMPORTING_BLOCKS
        )
        
        disk = await storage_api.disk_create(disk_request)
        disk_id = disk["id"]
        
        # Start import
        await storage_api.disk_bulk_write_import_start(disk_id)
        
        # Import data in chunks
        chunk_size = 1024  # 1KB chunks
        total_chunks = 100
        
        import base64
        
        for i in range(total_chunks):
            # Generate test data
            test_data = f"Chunk {i:03d}: " + "A" * (chunk_size - 12)
            encoded_data = base64.b64encode(test_data.encode()).decode()
            
            await storage_api.disk_bulk_write_import(
                disk_id, encoded_data, offset=i * chunk_size
            )
        
        # Finalize import
        result = await storage_api.disk_finalize_import(disk_id)
        assert result["status"] == "finalized"
        
        # Cleanup
        await storage_api.disk_delete(disk_id)