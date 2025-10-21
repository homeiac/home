#!/usr/bin/env python3
"""
Idempotent ZFS storage management for Proxmox VE.

Handles:
- ZFS pool creation/import with safety checks
- Proxmox storage registration
- Pool health verification
- Dataset management

All operations are idempotent and safe to re-run.
"""

import logging
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages ZFS pools and Proxmox storage integration."""

    def __init__(self, proxmox_client: Any, node: str):
        """
        Initialize storage manager.

        Args:
            proxmox_client: ProxmoxAPI client instance
            node: Proxmox node name (e.g., 'pumped-piglet')
        """
        self.proxmox = proxmox_client
        self.node = node
        self.logger = logger

    def pool_exists(self, pool_name: str) -> bool:
        """
        Check if ZFS pool exists locally.

        Args:
            pool_name: Name of the ZFS pool

        Returns:
            True if pool exists, False otherwise
        """
        try:
            result = subprocess.run(
                ["ssh", f"root@{self.node}.maas", "zpool", "list", "-H", pool_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout checking pool {pool_name}")
            return False

    def pool_importable(self, pool_name: str) -> bool:
        """
        Check if pool can be imported.

        Args:
            pool_name: Name of the ZFS pool

        Returns:
            True if pool can be imported, False otherwise
        """
        try:
            result = subprocess.run(
                ["ssh", f"root@{self.node}.maas", "zpool", "import"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return pool_name in result.stdout
        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout checking importable pools")
            return False

    def get_pool_status(self, pool_name: str) -> Optional[Dict[str, str]]:
        """
        Get ZFS pool status and properties.

        Args:
            pool_name: Name of the ZFS pool

        Returns:
            Dictionary with pool properties or None if pool doesn't exist
        """
        if not self.pool_exists(pool_name):
            return None

        try:
            result = subprocess.run(
                [
                    "ssh",
                    f"root@{self.node}.maas",
                    "zpool",
                    "list",
                    "-H",
                    "-o",
                    "name,size,alloc,free,health",
                    pool_name,
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            fields = result.stdout.strip().split("\t")
            return {
                "name": fields[0],
                "size": fields[1],
                "allocated": fields[2],
                "free": fields[3],
                "health": fields[4],
            }
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error getting pool status: {e}")
            return None

    def create_or_import_pool(
        self,
        pool_name: str,
        device: str,
        import_if_exists: bool = True,
        ashift: int = 12,
    ) -> Dict[str, Any]:
        """
        Idempotent pool creation or import.

        Args:
            pool_name: Name for the ZFS pool
            device: Device path (e.g., '/dev/nvme1n1')
            import_if_exists: If True, import pool if it exists externally
            ashift: ZFS ashift value (12 for 4K sectors)

        Returns:
            Dictionary with operation result:
            {
                'exists': bool,
                'created': bool,
                'imported': bool,
                'status': dict
            }
        """
        # Check if pool already exists
        if self.pool_exists(pool_name):
            self.logger.info(f"✅ Pool {pool_name} already exists on {self.node}")
            status = self.get_pool_status(pool_name)
            return {
                "exists": True,
                "created": False,
                "imported": False,
                "status": status,
            }

        # Check if pool can be imported
        if import_if_exists and self.pool_importable(pool_name):
            self.logger.info(f"📥 Importing existing pool {pool_name} on {self.node}")
            try:
                subprocess.run(
                    [
                        "ssh",
                        f"root@{self.node}.maas",
                        "zpool",
                        "import",
                        "-f",
                        pool_name,
                    ],
                    check=True,
                    capture_output=True,
                )
                status = self.get_pool_status(pool_name)
                self.logger.info(f"✅ Pool {pool_name} imported successfully")
                return {
                    "exists": True,
                    "created": False,
                    "imported": True,
                    "status": status,
                }
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Error importing pool: {e.stderr}")
                raise

        # Create new pool
        self.logger.info(f"🆕 Creating pool {pool_name} on {device} (ashift={ashift})")
        try:
            subprocess.run(
                [
                    "ssh",
                    f"root@{self.node}.maas",
                    "zpool",
                    "create",
                    "-o",
                    f"ashift={ashift}",
                    pool_name,
                    device,
                ],
                check=True,
                capture_output=True,
            )

            # Set recommended properties
            self._set_pool_properties(pool_name)

            status = self.get_pool_status(pool_name)
            self.logger.info(f"✅ Pool {pool_name} created successfully")
            return {
                "exists": True,
                "created": True,
                "imported": False,
                "status": status,
            }
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error creating pool: {e.stderr}")
            raise

    def _set_pool_properties(self, pool_name: str) -> None:
        """
        Set recommended ZFS properties for Proxmox VMs.

        Args:
            pool_name: Name of the ZFS pool
        """
        properties = {"compression": "lz4", "atime": "off"}

        for prop, value in properties.items():
            try:
                subprocess.run(
                    [
                        "ssh",
                        f"root@{self.node}.maas",
                        "zfs",
                        "set",
                        f"{prop}={value}",
                        pool_name,
                    ],
                    check=True,
                    capture_output=True,
                )
                self.logger.debug(f"Set {prop}={value} on {pool_name}")
            except subprocess.CalledProcessError as e:
                self.logger.warning(f"Could not set {prop}: {e.stderr}")

    def register_with_proxmox(
        self,
        pool_name: str,
        storage_id: str,
        content_types: Optional[List[str]] = None,
    ) -> bool:
        """
        Register ZFS pool as Proxmox storage (idempotent).

        Args:
            pool_name: ZFS pool name
            storage_id: Proxmox storage identifier
            content_types: List of content types (default: ['images', 'rootdir'])

        Returns:
            True if storage was registered, False if already existed
        """
        if content_types is None:
            content_types = ["images", "rootdir"]

        # Check if already registered
        try:
            existing = self.proxmox.storage(storage_id).get()
            self.logger.info(
                f"✅ Storage {storage_id} already registered in Proxmox"
            )
            return False
        except Exception:
            # Storage doesn't exist, proceed with registration
            pass

        # Register new storage
        self.logger.info(f"📝 Registering {storage_id} ({pool_name}) with Proxmox")
        try:
            self.proxmox.storage.create(
                storage=storage_id,
                type="zfspool",
                pool=pool_name,
                content=",".join(content_types),
                nodes=self.node,
            )
            self.logger.info(f"✅ Storage {storage_id} registered successfully")
            return True
        except Exception as e:
            self.logger.error(f"Error registering storage: {e}")
            raise

    def create_dataset(
        self, pool_name: str, dataset_name: str, quota: Optional[str] = None
    ) -> bool:
        """
        Create ZFS dataset (idempotent).

        Args:
            pool_name: Parent pool name
            dataset_name: Dataset name (will be pool_name/dataset_name)
            quota: Optional quota (e.g., '2T')

        Returns:
            True if created, False if already exists
        """
        full_path = f"{pool_name}/{dataset_name}"

        # Check if dataset exists
        try:
            result = subprocess.run(
                [
                    "ssh",
                    f"root@{self.node}.maas",
                    "zfs",
                    "list",
                    "-H",
                    full_path,
                ],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                self.logger.info(f"✅ Dataset {full_path} already exists")
                return False
        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout checking dataset {full_path}")
            return False

        # Create dataset
        self.logger.info(f"🆕 Creating dataset {full_path}")
        try:
            subprocess.run(
                ["ssh", f"root@{self.node}.maas", "zfs", "create", full_path],
                check=True,
                capture_output=True,
            )

            # Set quota if specified
            if quota:
                subprocess.run(
                    [
                        "ssh",
                        f"root@{self.node}.maas",
                        "zfs",
                        "set",
                        f"quota={quota}",
                        full_path,
                    ],
                    check=True,
                    capture_output=True,
                )
                self.logger.info(f"Set quota={quota} on {full_path}")

            self.logger.info(f"✅ Dataset {full_path} created successfully")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error creating dataset: {e.stderr}")
            raise
