"""
Configuration management for Crucible storage integration.
Supports multiple deployment modes and environments.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union
from urllib.parse import quote

from dotenv import load_dotenv


@dataclass
class CrucibleStorageSled:
    """Configuration for a single Crucible storage sled."""
    ip: str
    hostname: str
    ports: List[int] = field(default_factory=lambda: [8001, 8002, 8003])
    max_regions: int = 3
    credentials: Optional[Dict[str, str]] = None


@dataclass
class CrucibleConfig:
    """Complete Crucible deployment configuration."""
    # Storage sleds
    storage_sleds: List[CrucibleStorageSled] = field(default_factory=list)
    
    # Network configuration
    storage_network: str = "192.168.4.0/24"
    base_ip_range: str = "192.168.4.200-220"
    
    # Deployment settings
    deployment_mode: str = "development"  # development, testing, production
    enable_encryption: bool = True
    replication_factor: int = 3
    
    # Performance settings
    default_block_size: int = 512
    max_disk_size_gb: int = 1023
    io_timeout_sec: int = 30
    
    # Mock settings for testing
    enable_mocking: bool = False
    mock_latency_ms: float = 2.5
    mock_failure_rate: float = 0.0
    
    # Integration settings
    proxmox_integration: bool = True
    auto_attach_disks: bool = False
    
    @classmethod
    def from_environment(cls) -> "CrucibleConfig":
        """Load configuration from environment variables."""
        load_dotenv()
        
        # Parse storage sleds from environment
        sleds = []
        sled_ips = os.getenv("CRUCIBLE_SLED_IPS", "192.168.4.200,192.168.4.201,192.168.4.202")
        
        for i, ip in enumerate(sled_ips.split(",")):
            ip = ip.strip()
            hostname = os.getenv(f"CRUCIBLE_SLED_{i+1}_HOSTNAME", f"ma90-{i+1}")
            ports_str = os.getenv(f"CRUCIBLE_SLED_{i+1}_PORTS", "8001,8002,8003")
            ports = [int(p.strip()) for p in ports_str.split(",")]
            
            sled = CrucibleStorageSled(
                ip=ip,
                hostname=hostname,
                ports=ports,
                max_regions=int(os.getenv(f"CRUCIBLE_SLED_{i+1}_MAX_REGIONS", "3")),
                credentials={
                    "username": os.getenv(f"CRUCIBLE_SLED_{i+1}_USER", "ubuntu"),
                    "ssh_key": os.getenv("SSH_PUBKEY_PATH", "~/.ssh/id_rsa")
                }
            )
            sleds.append(sled)
        
        return cls(
            storage_sleds=sleds,
            storage_network=os.getenv("CRUCIBLE_STORAGE_NETWORK", "192.168.4.0/24"),
            base_ip_range=os.getenv("CRUCIBLE_IP_RANGE", "192.168.4.200-220"),
            deployment_mode=os.getenv("CRUCIBLE_DEPLOYMENT_MODE", "development"),
            enable_encryption=os.getenv("CRUCIBLE_ENCRYPTION", "true").lower() == "true",
            replication_factor=int(os.getenv("CRUCIBLE_REPLICATION_FACTOR", "3")),
            default_block_size=int(os.getenv("CRUCIBLE_BLOCK_SIZE", "512")),
            max_disk_size_gb=int(os.getenv("CRUCIBLE_MAX_DISK_SIZE_GB", "1023")),
            io_timeout_sec=int(os.getenv("CRUCIBLE_IO_TIMEOUT", "30")),
            enable_mocking=os.getenv("CRUCIBLE_ENABLE_MOCKING", "false").lower() == "true",
            mock_latency_ms=float(os.getenv("CRUCIBLE_MOCK_LATENCY_MS", "2.5")),
            mock_failure_rate=float(os.getenv("CRUCIBLE_MOCK_FAILURE_RATE", "0.0")),
            proxmox_integration=os.getenv("CRUCIBLE_PROXMOX_INTEGRATION", "true").lower() == "true",
            auto_attach_disks=os.getenv("CRUCIBLE_AUTO_ATTACH", "false").lower() == "true"
        )
    
    def validate(self) -> None:
        """Validate configuration settings."""
        if not self.storage_sleds:
            raise ValueError("At least one storage sled must be configured")
        
        if self.replication_factor > len(self.storage_sleds):
            raise ValueError(f"Replication factor ({self.replication_factor}) cannot exceed number of sleds ({len(self.storage_sleds)})")
        
        if self.default_block_size not in [512, 2048, 4096]:
            raise ValueError(f"Invalid block size {self.default_block_size}, must be 512, 2048, or 4096")
        
        if self.max_disk_size_gb <= 0 or self.max_disk_size_gb > 10240:
            raise ValueError(f"Invalid max disk size {self.max_disk_size_gb}GB, must be 1-10240")
    
    def to_dict(self) -> Dict[str, Union[str, int, bool, List[Dict[str, Union[str, int]]]]]:
        """Convert to dictionary for serialization."""
        return {
            "storage_sleds": [
                {
                    "ip": sled.ip,
                    "hostname": sled.hostname,
                    "ports": sled.ports,
                    "max_regions": sled.max_regions
                }
                for sled in self.storage_sleds
            ],
            "storage_network": self.storage_network,
            "deployment_mode": self.deployment_mode,
            "enable_encryption": self.enable_encryption,
            "replication_factor": self.replication_factor,
            "default_block_size": self.default_block_size,
            "max_disk_size_gb": self.max_disk_size_gb,
            "enable_mocking": self.enable_mocking,
            "proxmox_integration": self.proxmox_integration
        }