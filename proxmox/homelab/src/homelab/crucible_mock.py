"""
Mock implementation of Crucible storage for development and testing.
Provides complete API compatibility without requiring actual infrastructure.
"""

import asyncio
import base64
import json
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from unittest.mock import MagicMock

from homelab.crucible_config import CrucibleConfig, CrucibleStorageSled

logger = logging.getLogger(__name__)


class MockCrucibleSled:
    """Mock implementation of a Crucible storage sled."""
    
    def __init__(self, config: CrucibleStorageSled, crucible_config: CrucibleConfig):
        self.config = config
        self.crucible_config = crucible_config
        self.regions: Dict[str, Dict[str, Any]] = {}
        self.is_online = True
        self.total_capacity_bytes = 256 * 1024**3  # 256GB per sled
        self.used_capacity_bytes = 0
        self.performance_metrics = {
            "read_ops": 0,
            "write_ops": 0,
            "total_bytes_read": 0,
            "total_bytes_written": 0,
            "avg_latency_ms": crucible_config.mock_latency_ms
        }
    
    async def create_region(self, region_id: str, size_bytes: int) -> Dict[str, Any]:
        """Create a new storage region on this sled."""
        await self._simulate_latency()
        
        if not self.is_online:
            raise RuntimeError(f"Sled {self.config.ip} is offline")
        
        if size_bytes > (self.total_capacity_bytes - self.used_capacity_bytes):
            raise RuntimeError(f"Insufficient capacity on sled {self.config.ip}")
        
        region_info = {
            "id": region_id,
            "size_bytes": size_bytes,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "port": random.choice(self.config.ports),
            "path": f"/crucible/regions/{region_id}",
            "blocks": {},
            "status": "ready"
        }
        
        self.regions[region_id] = region_info
        self.used_capacity_bytes += size_bytes
        
        logger.debug(f"Created region {region_id} on sled {self.config.ip}")
        return region_info.copy()
    
    async def delete_region(self, region_id: str) -> None:
        """Delete a storage region from this sled."""
        await self._simulate_latency()
        
        if region_id not in self.regions:
            raise ValueError(f"Region {region_id} not found on sled {self.config.ip}")
        
        region = self.regions[region_id]
        self.used_capacity_bytes -= region["size_bytes"]
        del self.regions[region_id]
        
        logger.debug(f"Deleted region {region_id} from sled {self.config.ip}")
    
    async def read_blocks(self, region_id: str, offset: int, length: int) -> bytes:
        """Read data blocks from a region."""
        await self._simulate_latency()
        await self._check_failure_rate()
        
        if not self.is_online:
            raise RuntimeError(f"Sled {self.config.ip} is offline")
        
        if region_id not in self.regions:
            raise ValueError(f"Region {region_id} not found")
        
        region = self.regions[region_id]
        
        # Simulate reading from mock storage
        data = b"\x00" * length  # Return zeros for simplicity
        
        # Update metrics
        self.performance_metrics["read_ops"] += 1
        self.performance_metrics["total_bytes_read"] += length
        
        logger.debug(f"Read {length} bytes from region {region_id} at offset {offset}")
        return data
    
    async def write_blocks(self, region_id: str, offset: int, data: bytes) -> None:
        """Write data blocks to a region."""
        await self._simulate_latency()
        await self._check_failure_rate()
        
        if not self.is_online:
            raise RuntimeError(f"Sled {self.config.ip} is offline")
        
        if region_id not in self.regions:
            raise ValueError(f"Region {region_id} not found")
        
        region = self.regions[region_id]
        
        # Store block in mock storage
        block_key = f"{offset}:{len(data)}"
        region["blocks"][block_key] = len(data)  # Just store size for mock
        
        # Update metrics
        self.performance_metrics["write_ops"] += 1
        self.performance_metrics["total_bytes_written"] += len(data)
        
        logger.debug(f"Wrote {len(data)} bytes to region {region_id} at offset {offset}")
    
    async def get_region_info(self, region_id: str) -> Dict[str, Any]:
        """Get information about a specific region."""
        await self._simulate_latency()
        
        if region_id not in self.regions:
            raise ValueError(f"Region {region_id} not found")
        
        return self.regions[region_id].copy()
    
    async def get_sled_status(self) -> Dict[str, Any]:
        """Get current status and metrics for this sled."""
        return {
            "ip": self.config.ip,
            "hostname": self.config.hostname,
            "is_online": self.is_online,
            "total_capacity_bytes": self.total_capacity_bytes,
            "used_capacity_bytes": self.used_capacity_bytes,
            "free_capacity_bytes": self.total_capacity_bytes - self.used_capacity_bytes,
            "region_count": len(self.regions),
            "performance_metrics": self.performance_metrics.copy()
        }
    
    def set_online(self, online: bool) -> None:
        """Simulate sled going online/offline."""
        self.is_online = online
        status = "online" if online else "offline"
        logger.info(f"Sled {self.config.ip} is now {status}")
    
    async def _simulate_latency(self) -> None:
        """Simulate network/storage latency."""
        if self.crucible_config.mock_latency_ms > 0:
            latency = random.uniform(
                self.crucible_config.mock_latency_ms * 0.5,
                self.crucible_config.mock_latency_ms * 1.5
            )
            await asyncio.sleep(latency / 1000.0)
    
    async def _check_failure_rate(self) -> None:
        """Simulate random failures based on configured failure rate."""
        if (self.crucible_config.mock_failure_rate > 0 and 
            random.random() < self.crucible_config.mock_failure_rate):
            raise RuntimeError(f"Simulated failure on sled {self.config.ip}")


class MockCrucibleManager:
    """Mock implementation of Crucible storage management."""
    
    def __init__(self, config: CrucibleConfig):
        self.config = config
        self.sleds: Dict[str, MockCrucibleSled] = {}
        self.volumes: Dict[str, Dict[str, Any]] = {}
        self.snapshots: Dict[str, Dict[str, Any]] = {}
        
        # Initialize mock sleds
        for sled_config in config.storage_sleds:
            self.sleds[sled_config.ip] = MockCrucibleSled(sled_config, config)
        
        logger.info(f"Initialized MockCrucibleManager with {len(self.sleds)} sleds")
    
    async def discover_sleds(self) -> Dict[str, Dict[str, Any]]:
        """Discover all available storage sleds."""
        logger.info("Discovering storage sleds")
        
        sled_status = {}
        for ip, sled in self.sleds.items():
            try:
                status = await sled.get_sled_status()
                sled_status[ip] = status
            except Exception as e:
                sled_status[ip] = {"error": str(e), "is_online": False}
        
        return sled_status
    
    async def create_volume(self, volume_id: str, size_bytes: int, 
                          replica_count: Optional[int] = None) -> Dict[str, Any]:
        """Create a replicated volume across storage sleds."""
        if replica_count is None:
            replica_count = self.config.replication_factor
        
        logger.info(f"Creating volume {volume_id} ({size_bytes} bytes, {replica_count} replicas)")
        
        # Select online sleds for replicas
        online_sleds = [sled for sled in self.sleds.values() if sled.is_online]
        if len(online_sleds) < replica_count:
            raise RuntimeError(f"Insufficient online sleds ({len(online_sleds)}) for {replica_count} replicas")
        
        selected_sleds = random.sample(online_sleds, replica_count)
        
        # Create regions on selected sleds
        replicas = []
        try:
            for sled in selected_sleds:
                region_id = f"{volume_id}-replica-{sled.config.ip.split('.')[-1]}"
                region_info = await sled.create_region(region_id, size_bytes)
                replicas.append({
                    "sled_ip": sled.config.ip,
                    "region_id": region_id,
                    "port": region_info["port"]
                })
            
            volume_info = {
                "id": volume_id,
                "size_bytes": size_bytes,
                "replicas": replicas,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "ready",
                "encryption_enabled": self.config.enable_encryption
            }
            
            self.volumes[volume_id] = volume_info
            logger.info(f"Created volume {volume_id} with {len(replicas)} replicas")
            return volume_info.copy()
            
        except Exception as e:
            # Cleanup on failure
            for replica in replicas:
                try:
                    sled = self.sleds[replica["sled_ip"]]
                    await sled.delete_region(replica["region_id"])
                except Exception:
                    pass
            raise e
    
    async def delete_volume(self, volume_id: str) -> None:
        """Delete a volume and all its replicas."""
        logger.info(f"Deleting volume {volume_id}")
        
        if volume_id not in self.volumes:
            raise ValueError(f"Volume {volume_id} not found")
        
        volume = self.volumes[volume_id]
        
        # Delete all replicas
        for replica in volume["replicas"]:
            try:
                sled = self.sleds[replica["sled_ip"]]
                await sled.delete_region(replica["region_id"])
            except Exception as e:
                logger.warning(f"Failed to delete replica {replica['region_id']}: {e}")
        
        del self.volumes[volume_id]
        logger.info(f"Deleted volume {volume_id}")
    
    async def read_volume(self, volume_id: str, offset: int, length: int) -> bytes:
        """Read data from a volume (uses first available replica)."""
        if volume_id not in self.volumes:
            raise ValueError(f"Volume {volume_id} not found")
        
        volume = self.volumes[volume_id]
        
        # Try replicas in order until one succeeds
        last_error = None
        for replica in volume["replicas"]:
            try:
                sled = self.sleds[replica["sled_ip"]]
                data = await sled.read_blocks(replica["region_id"], offset, length)
                return data
            except Exception as e:
                last_error = e
                continue
        
        raise RuntimeError(f"Failed to read from volume {volume_id}: {last_error}")
    
    async def write_volume(self, volume_id: str, offset: int, data: bytes) -> None:
        """Write data to a volume (writes to all replicas)."""
        if volume_id not in self.volumes:
            raise ValueError(f"Volume {volume_id} not found")
        
        volume = self.volumes[volume_id]
        
        # Write to all replicas
        write_tasks = []
        for replica in volume["replicas"]:
            sled = self.sleds[replica["sled_ip"]]
            task = sled.write_blocks(replica["region_id"], offset, data)
            write_tasks.append(task)
        
        # Wait for all writes to complete
        results = await asyncio.gather(*write_tasks, return_exceptions=True)
        
        # Check for any failures
        failures = [r for r in results if isinstance(r, Exception)]
        if failures:
            raise RuntimeError(f"Write failed on {len(failures)}/{len(results)} replicas")
    
    async def create_snapshot(self, snapshot_id: str, volume_id: str) -> Dict[str, Any]:
        """Create a point-in-time snapshot of a volume."""
        logger.info(f"Creating snapshot {snapshot_id} of volume {volume_id}")
        
        if volume_id not in self.volumes:
            raise ValueError(f"Volume {volume_id} not found")
        
        volume = self.volumes[volume_id]
        
        # In a real implementation, this would create copy-on-write snapshots
        # For the mock, we just record the snapshot metadata
        snapshot_info = {
            "id": snapshot_id,
            "volume_id": volume_id,
            "size_bytes": volume["size_bytes"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "ready"
        }
        
        self.snapshots[snapshot_id] = snapshot_info
        logger.info(f"Created snapshot {snapshot_id}")
        return snapshot_info.copy()
    
    async def delete_snapshot(self, snapshot_id: str) -> None:
        """Delete a snapshot."""
        logger.info(f"Deleting snapshot {snapshot_id}")
        
        if snapshot_id not in self.snapshots:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        
        del self.snapshots[snapshot_id]
        logger.info(f"Deleted snapshot {snapshot_id}")
    
    async def get_volume_info(self, volume_id: str) -> Dict[str, Any]:
        """Get detailed information about a volume."""
        if volume_id not in self.volumes:
            raise ValueError(f"Volume {volume_id} not found")
        
        return self.volumes[volume_id].copy()
    
    async def list_volumes(self) -> List[Dict[str, Any]]:
        """List all volumes."""
        return [info.copy() for info in self.volumes.values()]
    
    async def list_snapshots(self) -> List[Dict[str, Any]]:
        """List all snapshots."""
        return [info.copy() for info in self.snapshots.values()]
    
    async def simulate_sled_failure(self, sled_ip: str) -> None:
        """Simulate a storage sled going offline."""
        if sled_ip in self.sleds:
            self.sleds[sled_ip].set_online(False)
            logger.warning(f"Simulated failure of sled {sled_ip}")
        else:
            raise ValueError(f"Sled {sled_ip} not found")
    
    async def simulate_sled_recovery(self, sled_ip: str) -> None:
        """Simulate a storage sled coming back online."""
        if sled_ip in self.sleds:
            self.sleds[sled_ip].set_online(True)
            logger.info(f"Simulated recovery of sled {sled_ip}")
        else:
            raise ValueError(f"Sled {sled_ip} not found")
    
    async def get_cluster_status(self) -> Dict[str, Any]:
        """Get overall cluster status and metrics."""
        sled_status = await self.discover_sleds()
        
        online_sleds = sum(1 for s in sled_status.values() if s.get("is_online", False))
        total_capacity = sum(s.get("total_capacity_bytes", 0) for s in sled_status.values())
        used_capacity = sum(s.get("used_capacity_bytes", 0) for s in sled_status.values())
        
        return {
            "total_sleds": len(self.sleds),
            "online_sleds": online_sleds,
            "offline_sleds": len(self.sleds) - online_sleds,
            "total_capacity_bytes": total_capacity,
            "used_capacity_bytes": used_capacity,
            "free_capacity_bytes": total_capacity - used_capacity,
            "total_volumes": len(self.volumes),
            "total_snapshots": len(self.snapshots),
            "replication_factor": self.config.replication_factor,
            "sleds": sled_status
        }