#!/usr/bin/env python3
"""
src/homelab/zfs_mirror_manager.py

Config-driven ZFS mirror management for Proxmox hosts.
Reads zfs_mirrors config from config/cluster.yaml and performs idempotent
mirror operations (partition cloning, GUID randomization, boot setup,
mirror attach, resilver verification).

Usage:
    from homelab.zfs_mirror_manager import ZfsMirrorManager

    with ZfsMirrorManager("still-fawn") as mgr:
        result = mgr.apply(dry_run=True)

CLI:
    poetry run homelab storage mirror apply --host still-fawn --dry-run
    poetry run homelab storage mirror status --host still-fawn
"""

import logging
import re
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import paramiko
import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "cluster.yaml"


def load_cluster_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load cluster configuration from YAML file."""
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Cluster config not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


class ZfsMirrorManager:
    """Manages ZFS mirror operations on Proxmox hosts.

    Provides idempotent operations for converting single-vdev ZFS pools
    into mirrors by cloning partition tables, configuring boot, and
    attaching the new disk.
    """

    def __init__(
        self,
        hostname: str,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        self.hostname = hostname
        self.ssh_client: Optional[paramiko.SSHClient] = None

        if config:
            self._config = config
        else:
            self._config = load_cluster_config(config_path)

        # Find this node's config
        self._node_config: Optional[Dict[str, Any]] = None
        for node in self._config.get("nodes", []):
            if node.get("name") == hostname:
                self._node_config = node
                break

        if not self._node_config:
            raise ValueError(f"Host '{hostname}' not found in cluster config")

        self._mirrors: List[Dict[str, Any]] = self._node_config.get("zfs_mirrors", [])

    # -- SSH helpers (same pattern as node_exporter_manager.py) --

    def _get_ssh_client(self) -> paramiko.SSHClient:
        """Get or create an SSH connection to the host."""
        if not self.ssh_client:
            import os

            ssh_user = os.getenv("SSH_USER", "root")
            ssh_key = os.path.expanduser(
                os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa")
            )

            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            hostname = self.hostname
            if not hostname.endswith(".maas"):
                hostname = f"{self.hostname}.maas"

            try:
                resolved_ip = socket.gethostbyname(hostname)
                logger.debug(f"Resolved {hostname} -> {resolved_ip}")
                self.ssh_client.connect(
                    hostname=resolved_ip,
                    username=ssh_user,
                    key_filename=ssh_key,
                    timeout=10,
                )
            except Exception as e:
                logger.debug(f"Failed to connect to {hostname}: {e}")
                if hostname.endswith(".maas"):
                    hostname = self.hostname
                    try:
                        resolved_ip = socket.gethostbyname(hostname)
                        self.ssh_client.connect(
                            hostname=resolved_ip,
                            username=ssh_user,
                            key_filename=ssh_key,
                            timeout=10,
                        )
                    except Exception as e2:
                        raise e2
                else:
                    raise

        return self.ssh_client

    def _ssh_exec(self, cmd: str) -> Tuple[str, str, int]:
        """Execute a command via SSH. Returns (stdout, stderr, exit_code)."""
        ssh = self._get_ssh_client()
        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_code = stdout.channel.recv_exit_status()
        return (
            stdout.read().decode().strip(),
            stderr.read().decode().strip(),
            exit_code,
        )

    def cleanup(self) -> None:
        """Close SSH connection."""
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None

    def __enter__(self) -> "ZfsMirrorManager":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup()

    # -- helpers --

    def _disk_path(self, disk_id: str) -> str:
        """Return /dev/disk/by-id/ path for a disk serial."""
        return f"/dev/disk/by-id/{disk_id}"

    def _part_path(self, disk_id: str, part_num: int) -> str:
        """Return /dev/disk/by-id/ path for a partition."""
        return f"/dev/disk/by-id/{disk_id}-part{part_num}"

    # -- state detection --

    def get_pool_topology(self, pool: str) -> Dict[str, Any]:
        """Parse ``zpool status`` into a structured dict.

        Returns dict with keys:
            state: pool state string (e.g. "ONLINE")
            is_mirror: True if pool has a mirror-0 vdev
            vdev_disks: list of disk-id strings in the vdev
            scan: the scan/resilver status line (or "")
        """
        stdout, stderr, rc = self._ssh_exec(f"zpool status {pool}")
        if rc != 0:
            return {"state": "MISSING", "is_mirror": False, "vdev_disks": [], "scan": ""}

        result: Dict[str, Any] = {
            "state": "UNKNOWN",
            "is_mirror": False,
            "vdev_disks": [],
            "scan": "",
        }

        for line in stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("state:"):
                result["state"] = stripped.split(":", 1)[1].strip()
            if "mirror-0" in stripped:
                result["is_mirror"] = True
            if stripped.startswith("scan:"):
                result["scan"] = stripped.split(":", 1)[1].strip()
            # Capture disk-by-id references in vdev listing
            m = re.search(r"(ata-\S+)", stripped)
            if m:
                result["vdev_disks"].append(m.group(1))

        return result

    def is_already_mirror(self, pool: str) -> bool:
        """True if the pool already has a mirror vdev."""
        topo = self.get_pool_topology(pool)
        return topo["is_mirror"]

    def disk_exists(self, disk_id: str) -> bool:
        """True if the disk symlink exists under /dev/disk/by-id/."""
        _, _, rc = self._ssh_exec(f"test -e {self._disk_path(disk_id)}")
        return rc == 0

    def get_partition_table(self, disk_id: str) -> str:
        """Return raw sgdisk -p output for a disk."""
        stdout, _, _ = self._ssh_exec(f"sgdisk -p {self._disk_path(disk_id)}")
        return stdout

    def partitions_match(self, src_id: str, dst_id: str) -> bool:
        """True if dst has partition count & sizes matching src."""
        src_table = self.get_partition_table(src_id)
        dst_table = self.get_partition_table(dst_id)

        def _extract_parts(text: str) -> List[str]:
            """Extract partition lines (start with a number)."""
            parts = []
            for line in text.splitlines():
                stripped = line.strip()
                if stripped and stripped[0].isdigit():
                    parts.append(stripped)
            return parts

        src_parts = _extract_parts(src_table)
        dst_parts = _extract_parts(dst_table)
        return len(src_parts) > 0 and src_parts == dst_parts

    def guids_differ(self, src_id: str, dst_id: str) -> bool:
        """True if the two disks have different disk GUIDs."""
        def _get_guid(disk_id: str) -> Optional[str]:
            stdout, _, _ = self._ssh_exec(f"sgdisk -p {self._disk_path(disk_id)}")
            for line in stdout.splitlines():
                if "Disk identifier (GUID)" in line:
                    return line.split(":")[-1].strip()
            return None

        src_guid = _get_guid(src_id)
        dst_guid = _get_guid(dst_id)
        if src_guid is None or dst_guid is None:
            return False
        return src_guid != dst_guid

    def boot_configured(self, disk_id: str, efi_part: int) -> bool:
        """True if proxmox-boot-tool status lists the disk's ESP."""
        stdout, _, rc = self._ssh_exec("proxmox-boot-tool status")
        if rc != 0:
            return False
        part_path = self._part_path(disk_id, efi_part)
        return part_path in stdout

    def pool_is_resilvering(self, pool: str) -> bool:
        """True if the pool is currently resilvering."""
        topo = self.get_pool_topology(pool)
        return "resilver in progress" in topo["scan"].lower()

    def pool_is_scrubbing(self, pool: str) -> bool:
        """True if the pool is currently scrubbing."""
        topo = self.get_pool_topology(pool)
        return "scrub in progress" in topo["scan"].lower()

    def get_disk_size_sectors(self, disk_id: str) -> Optional[int]:
        """Return sector count via lsblk for a disk."""
        stdout, _, rc = self._ssh_exec(
            f"lsblk -bndo SIZE {self._disk_path(disk_id)}"
        )
        if rc != 0 or not stdout:
            return None
        try:
            return int(stdout)
        except ValueError:
            return None

    def disk_in_any_pool(self, disk_id: str) -> bool:
        """True if any partition on the disk is already part of a zpool."""
        stdout, _, rc = self._ssh_exec("zpool status -L")
        if rc != 0:
            return False
        return disk_id in stdout

    def required_tools_present(self) -> Dict[str, bool]:
        """Check that sgdisk, proxmox-boot-tool, zpool are available."""
        tools = {}
        for tool in ("sgdisk", "proxmox-boot-tool", "zpool"):
            _, _, rc = self._ssh_exec(f"which {tool}")
            tools[tool] = rc == 0
        return tools

    # -- pre-flight --

    def preflight(self, mirror_cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Run pre-flight checks. Returns dict of check_name -> pass/fail + detail."""
        existing = mirror_cfg["existing_disk"]
        new = mirror_cfg["new_disk"]
        pool = mirror_cfg["pool"]

        checks: Dict[str, Any] = {}

        # 1. Pool exists and is ONLINE
        topo = self.get_pool_topology(pool)
        checks["pool_online"] = {
            "passed": topo["state"] == "ONLINE",
            "detail": f"state={topo['state']}",
        }

        # 2. Both disks present
        checks["existing_disk_present"] = {
            "passed": self.disk_exists(existing),
            "detail": self._disk_path(existing),
        }
        checks["new_disk_present"] = {
            "passed": self.disk_exists(new),
            "detail": self._disk_path(new),
        }

        # 3. New disk not already in a pool
        in_pool = self.disk_in_any_pool(new)
        checks["new_disk_free"] = {
            "passed": not in_pool,
            "detail": "already in a pool" if in_pool else "not in any pool",
        }

        # 4. Disk sizes match
        src_size = self.get_disk_size_sectors(existing)
        dst_size = self.get_disk_size_sectors(new)
        sizes_match = src_size is not None and dst_size is not None and src_size == dst_size
        checks["disk_sizes_match"] = {
            "passed": sizes_match,
            "detail": f"existing={src_size} new={dst_size}",
        }

        # 5. Required tools
        tools = self.required_tools_present()
        all_tools = all(tools.values())
        missing = [t for t, ok in tools.items() if not ok]
        checks["required_tools"] = {
            "passed": all_tools,
            "detail": f"missing: {missing}" if missing else "all present",
        }

        # 6. Not resilvering or scrubbing
        busy = self.pool_is_resilvering(pool) or self.pool_is_scrubbing(pool)
        checks["pool_not_busy"] = {
            "passed": not busy,
            "detail": "resilvering or scrubbing" if busy else "idle",
        }

        return checks

    # -- operations (each idempotent) --

    def clone_partitions(
        self, mirror_cfg: Dict[str, Any], dry_run: bool = False
    ) -> Dict[str, Any]:
        """Step 1: Clone partition table from existing to new disk."""
        existing = mirror_cfg["existing_disk"]
        new = mirror_cfg["new_disk"]

        if self.partitions_match(existing, new):
            return {"step": "clone_partitions", "status": "skipped", "reason": "already match"}

        cmd = f"sgdisk -R {self._disk_path(new)} {self._disk_path(existing)}"
        if dry_run:
            return {"step": "clone_partitions", "status": "would_execute", "cmd": cmd}

        stdout, stderr, rc = self._ssh_exec(cmd)
        if rc != 0:
            return {"step": "clone_partitions", "status": "failed", "error": stderr}

        return {"step": "clone_partitions", "status": "done", "output": stdout}

    def randomize_guids(
        self, mirror_cfg: Dict[str, Any], dry_run: bool = False
    ) -> Dict[str, Any]:
        """Step 2: Randomize GUIDs on the new disk so they differ from source."""
        existing = mirror_cfg["existing_disk"]
        new = mirror_cfg["new_disk"]

        if self.guids_differ(existing, new):
            return {"step": "randomize_guids", "status": "skipped", "reason": "already differ"}

        cmd = f"sgdisk -G {self._disk_path(new)}"
        if dry_run:
            return {"step": "randomize_guids", "status": "would_execute", "cmd": cmd}

        stdout, stderr, rc = self._ssh_exec(cmd)
        if rc != 0:
            return {"step": "randomize_guids", "status": "failed", "error": stderr}

        return {"step": "randomize_guids", "status": "done", "output": stdout}

    def setup_boot(
        self, mirror_cfg: Dict[str, Any], dry_run: bool = False
    ) -> Dict[str, Any]:
        """Step 3: Format + init ESP on the new disk for proxmox-boot-tool."""
        new = mirror_cfg["new_disk"]
        efi_part = mirror_cfg.get("efi_partition", 2)

        if self.boot_configured(new, efi_part):
            return {"step": "setup_boot", "status": "skipped", "reason": "already configured"}

        part = self._part_path(new, efi_part)
        fmt_cmd = f"proxmox-boot-tool format {part}"
        init_cmd = f"proxmox-boot-tool init {part}"

        if dry_run:
            return {
                "step": "setup_boot",
                "status": "would_execute",
                "cmds": [fmt_cmd, init_cmd],
            }

        # Format ESP
        stdout, stderr, rc = self._ssh_exec(fmt_cmd)
        if rc != 0:
            return {"step": "setup_boot", "status": "failed", "error": f"format: {stderr}"}

        # Init ESP
        stdout, stderr, rc = self._ssh_exec(init_cmd)
        if rc != 0:
            return {"step": "setup_boot", "status": "failed", "error": f"init: {stderr}"}

        return {"step": "setup_boot", "status": "done"}

    def attach_mirror(
        self, mirror_cfg: Dict[str, Any], dry_run: bool = False
    ) -> Dict[str, Any]:
        """Step 4: Attach new disk partition to pool as mirror."""
        pool = mirror_cfg["pool"]
        existing = mirror_cfg["existing_disk"]
        new = mirror_cfg["new_disk"]
        zfs_part = mirror_cfg.get("zfs_partition", 3)

        if self.is_already_mirror(pool):
            topo = self.get_pool_topology(pool)
            new_part = self._part_path(new, zfs_part)
            # Check both disks are already in the mirror
            if any(new in d for d in topo["vdev_disks"]):
                return {"step": "attach_mirror", "status": "skipped", "reason": "already mirrored"}

        existing_part = self._part_path(existing, zfs_part)
        new_part = self._part_path(new, zfs_part)
        cmd = f"zpool attach {pool} {existing_part} {new_part}"

        if dry_run:
            return {"step": "attach_mirror", "status": "would_execute", "cmd": cmd}

        stdout, stderr, rc = self._ssh_exec(cmd)
        if rc != 0:
            return {"step": "attach_mirror", "status": "failed", "error": stderr}

        return {"step": "attach_mirror", "status": "done"}

    def check_resilver(self, pool: str) -> Dict[str, Any]:
        """Step 5: Check resilver progress."""
        topo = self.get_pool_topology(pool)
        return {
            "step": "check_resilver",
            "is_mirror": topo["is_mirror"],
            "state": topo["state"],
            "scan": topo["scan"],
            "vdev_disks": topo["vdev_disks"],
        }

    # -- orchestration --

    def status(self) -> Dict[str, Any]:
        """Return mirror status for all configured mirrors on this host."""
        results = []
        for mcfg in self._mirrors:
            pool = mcfg["pool"]
            topo = self.get_pool_topology(pool)
            results.append({
                "pool": pool,
                "existing_disk": mcfg["existing_disk"],
                "new_disk": mcfg["new_disk"],
                "is_mirror": topo["is_mirror"],
                "state": topo["state"],
                "scan": topo["scan"],
                "vdev_disks": topo["vdev_disks"],
            })
        return {"hostname": self.hostname, "mirrors": results}

    def apply(self, dry_run: bool = False) -> Dict[str, Any]:
        """Run all mirror operations for every configured mirror on this host.

        Returns dict with overall success and per-mirror step results.
        """
        all_results: List[Dict[str, Any]] = []

        for mcfg in self._mirrors:
            pool = mcfg["pool"]
            mirror_result: Dict[str, Any] = {
                "pool": pool,
                "existing_disk": mcfg["existing_disk"],
                "new_disk": mcfg["new_disk"],
                "preflight": {},
                "steps": [],
                "status": "unknown",
            }

            # Pre-flight
            checks = self.preflight(mcfg)
            mirror_result["preflight"] = checks
            failed_checks = [k for k, v in checks.items() if not v["passed"]]

            # If already mirrored with both disks, skip everything
            if self.is_already_mirror(pool):
                topo = self.get_pool_topology(pool)
                if any(mcfg["new_disk"] in d for d in topo["vdev_disks"]):
                    mirror_result["status"] = "already_mirrored"
                    mirror_result["steps"] = []
                    resilver = self.check_resilver(pool)
                    mirror_result["resilver"] = resilver
                    all_results.append(mirror_result)
                    continue

            if failed_checks and not dry_run:
                # Allow new_disk_free to fail if it's already in THIS pool's mirror
                critical_fails = [c for c in failed_checks if c != "new_disk_free"]
                if critical_fails:
                    mirror_result["status"] = "preflight_failed"
                    mirror_result["failed_checks"] = failed_checks
                    all_results.append(mirror_result)
                    continue

            # Execute steps
            steps = [
                self.clone_partitions,
                self.randomize_guids,
                self.setup_boot,
                self.attach_mirror,
            ]

            had_failure = False
            for step_fn in steps:
                result = step_fn(mcfg, dry_run=dry_run)
                mirror_result["steps"].append(result)
                if result.get("status") == "failed":
                    had_failure = True
                    break

            # Resilver check (always runs, not affected by dry_run)
            if not dry_run and not had_failure:
                resilver = self.check_resilver(pool)
                mirror_result["resilver"] = resilver

            if had_failure:
                mirror_result["status"] = "failed"
            elif dry_run:
                mirror_result["status"] = "dry_run"
            else:
                mirror_result["status"] = "success"

            all_results.append(mirror_result)

        return {
            "hostname": self.hostname,
            "mirrors": all_results,
            "success": all(m["status"] in ("success", "already_mirrored", "dry_run") for m in all_results),
        }
