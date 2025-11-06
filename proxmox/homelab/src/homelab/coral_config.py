"""LXC configuration management for Coral TPU."""

import logging
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from .coral_models import ConfigurationError, ContainerStatus, LXCConfig

logger = logging.getLogger(__name__)


class LXCConfigManager:
    """Manages LXC container configuration for Coral TPU access."""

    def __init__(self, container_id: str, config_path: Optional[Path] = None, backup_dir: Optional[Path] = None):
        """
        Initialize the config manager.

        Args:
            container_id: LXC container ID (e.g., "113")
            config_path: Path to LXC config file (defaults to /etc/pve/lxc/{container_id}.conf)
            backup_dir: Directory for config backups (defaults to /root/coral-backups)
        """
        self.container_id = container_id
        # Use Mac-friendly defaults when /etc/pve doesn't exist
        if config_path:
            self.config_path = config_path
        elif Path("/etc/pve").exists():
            self.config_path = Path(f"/etc/pve/lxc/{container_id}.conf")
        else:
            # Development environment fallback
            self.config_path = Path.home() / "lxc_configs" / f"{container_id}.conf"

        self.backup_dir = backup_dir or Path.home() / "coral-backups"

        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def read_config(self) -> LXCConfig:
        """
        Read current LXC configuration.

        Returns:
            LXCConfig object with current state

        Raises:
            ConfigurationError: If config file cannot be read
        """
        logger.debug(f"Reading LXC config from {self.config_path}")

        if not self.config_path.exists():
            logger.warning(f"Config file not found: {self.config_path}")
            return LXCConfig(
                container_id=self.container_id, config_path=self.config_path, status=ContainerStatus.NOT_FOUND
            )

        try:
            content = self.config_path.read_text()
        except (OSError, PermissionError) as e:
            raise ConfigurationError(f"Failed to read config file {self.config_path}: {e}") from e

        # Parse configuration
        dev0_line = self._find_config_line(content, "dev0:")
        current_dev0 = dev0_line.split(":", 1)[1].strip() if dev0_line else None

        has_usb_permissions = "lxc.cgroup2.devices.allow: c 189:* rwm" in content

        # Get container status
        status = self._get_container_status()

        return LXCConfig(
            container_id=self.container_id,
            config_path=self.config_path,
            current_dev0=current_dev0,
            has_usb_permissions=has_usb_permissions,
            status=status,
        )

    def _find_config_line(self, content: str, prefix: str) -> Optional[str]:
        """Find configuration line starting with prefix."""
        for line in content.splitlines():
            line = line.strip()
            if line.startswith(prefix):
                return line
        return None

    def _get_container_status(self) -> ContainerStatus:
        """Get current container status."""
        try:
            result = subprocess.run(
                ["pct", "status", self.container_id], capture_output=True, text=True, check=True, timeout=10
            )

            if "status: running" in result.stdout:
                return ContainerStatus.RUNNING
            elif "status: stopped" in result.stdout:
                return ContainerStatus.STOPPED
            else:
                return ContainerStatus.ERROR

        except subprocess.SubprocessError:
            logger.warning(f"Failed to get status for container {self.container_id}")
            return ContainerStatus.NOT_FOUND

    def backup_config(self) -> Path:
        """
        Create a backup of the current configuration.

        Returns:
            Path to backup file

        Raises:
            ConfigurationError: If backup fails
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"lxc_{self.container_id}_{timestamp}.conf"

        try:
            shutil.copy2(self.config_path, backup_file)
            logger.info(f"Config backed up to {backup_file}")

            # Keep only last 5 backups
            self._cleanup_old_backups()

            return backup_file
        except (OSError, PermissionError) as e:
            raise ConfigurationError(f"Failed to backup config to {backup_file}: {e}") from e

    def _cleanup_old_backups(self) -> None:
        """Keep only the 5 most recent backups."""
        pattern = f"lxc_{self.container_id}_*.conf"
        backups = sorted(self.backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

        for old_backup in backups[5:]:
            try:
                old_backup.unlink()
                logger.debug(f"Removed old backup: {old_backup}")
            except OSError:
                logger.warning(f"Failed to remove old backup: {old_backup}")

    def update_config(self, device_path: str, dry_run: bool = False) -> bool:
        """
        Update LXC configuration with new device path.

        Args:
            device_path: New device path (e.g., "/dev/bus/usb/003/004")
            dry_run: If True, only validate changes without applying

        Returns:
            True if update succeeded, False otherwise

        Raises:
            ConfigurationError: If update fails
        """
        logger.info(f"Updating LXC config with device: {device_path} (dry_run={dry_run})")

        if not self.config_path.exists():
            raise ConfigurationError(f"Config file not found: {self.config_path}")

        try:
            content = self.config_path.read_text()
        except (OSError, PermissionError) as e:
            raise ConfigurationError(f"Failed to read config: {e}") from e

        # Update content
        new_content = self._update_config_content(content, device_path)

        if dry_run:
            logger.info("Dry run - would update config with:")
            logger.info(f"dev0: {device_path}")
            if "lxc.cgroup2.devices.allow: c 189:* rwm" not in content:
                logger.info("lxc.cgroup2.devices.allow: c 189:* rwm")
            return True

        # Validate new content
        if not self._validate_config_content(new_content):
            raise ConfigurationError("Generated config content is invalid")

        # Check if this is a pmxcfs filesystem (Proxmox cluster filesystem)
        is_pmxcfs = str(self.config_path).startswith("/etc/pve/")

        if is_pmxcfs:
            # For pmxcfs, use direct write (atomic operations not supported)
            logger.debug("Using direct write for pmxcfs filesystem")
            try:
                self.config_path.write_text(new_content)
                logger.info("Configuration updated successfully (direct write)")
                return True
            except (OSError, PermissionError) as e:
                raise ConfigurationError(f"Failed to update config: {e}") from e
        else:
            # For regular filesystems, use atomic replacement
            logger.debug("Using atomic replacement for regular filesystem")

            # Write to temporary file first
            with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as tmp_file:
                tmp_file.write(new_content)
                tmp_path = Path(tmp_file.name)

            try:
                # Atomic move to final location
                shutil.move(str(tmp_path), str(self.config_path))
                logger.info("Configuration updated successfully (atomic)")
                return True
            except (OSError, PermissionError) as e:
                # Cleanup temp file
                tmp_path.unlink(missing_ok=True)
                raise ConfigurationError(f"Failed to update config: {e}") from e

    def _update_config_content(self, content: str, device_path: str) -> str:
        """Update configuration content with new device path."""
        lines = content.splitlines()
        new_lines = []
        dev0_updated = False
        usb_perms_exists = False

        for line in lines:
            stripped = line.strip()

            # Update existing dev0 line
            if stripped.startswith("dev0:"):
                new_lines.append(f"dev0: {device_path}")
                dev0_updated = True
            # Check for existing USB permissions
            elif stripped == "lxc.cgroup2.devices.allow: c 189:* rwm":
                new_lines.append(line)
                usb_perms_exists = True
            else:
                new_lines.append(line)

        # Add dev0 line if it didn't exist
        if not dev0_updated:
            new_lines.append(f"dev0: {device_path}")

        # Add USB permissions if they don't exist
        if not usb_perms_exists:
            new_lines.append("lxc.cgroup2.devices.allow: c 189:* rwm")

        return "\n".join(new_lines) + "\n"

    def _validate_config_content(self, content: str) -> bool:
        """Validate configuration content."""
        # Basic validation - ensure required lines exist
        has_dev0 = any(line.strip().startswith("dev0:") for line in content.splitlines())
        has_usb_perms = "lxc.cgroup2.devices.allow: c 189:* rwm" in content

        return has_dev0 and has_usb_perms

    def stop_container(self, timeout: int = 30) -> bool:
        """
        Stop the LXC container.

        Args:
            timeout: Maximum time to wait for container to stop

        Returns:
            True if container stopped successfully
        """
        logger.info(f"Stopping container {self.container_id}")

        # Check current status
        status = self._get_container_status()
        if status == ContainerStatus.STOPPED:
            logger.info("Container already stopped")
            return True
        elif status in (ContainerStatus.NOT_FOUND, ContainerStatus.ERROR):
            logger.warning(f"Container in unexpected state: {status}")
            return False

        try:
            subprocess.run(["pct", "stop", self.container_id], check=True, timeout=timeout)

            # Wait for container to stop
            import time

            start_time = time.time()
            while time.time() - start_time < timeout:
                if self._get_container_status() == ContainerStatus.STOPPED:
                    logger.info("Container stopped successfully")
                    return True
                time.sleep(1)

            logger.error(f"Container failed to stop within {timeout} seconds")
            return False

        except subprocess.SubprocessError as e:
            logger.error(f"Failed to stop container: {e}")
            return False

    def start_container(self, timeout: int = 30) -> bool:
        """
        Start the LXC container.

        Args:
            timeout: Maximum time to wait for container to start

        Returns:
            True if container started successfully
        """
        logger.info(f"Starting container {self.container_id}")

        try:
            subprocess.run(["pct", "start", self.container_id], check=True, timeout=timeout)

            # Wait for container to start
            import time

            start_time = time.time()
            while time.time() - start_time < timeout:
                if self._get_container_status() == ContainerStatus.RUNNING:
                    logger.info("Container started successfully")
                    return True
                time.sleep(1)

            logger.error(f"Container failed to start within {timeout} seconds")
            return False

        except subprocess.SubprocessError as e:
            logger.error(f"Failed to start container: {e}")
            return False

    def verify_coral_access(self, expected_device_path: str) -> bool:
        """
        Verify that Coral is accessible inside the container.

        Args:
            expected_device_path: Expected device path

        Returns:
            True if Coral is accessible inside container
        """
        if self._get_container_status() != ContainerStatus.RUNNING:
            logger.warning("Container not running - cannot verify Coral access")
            return False

        try:
            # Check if device is visible via lsusb inside container
            result = subprocess.run(
                ["pct", "exec", self.container_id, "--", "lsusb"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )

            google_found = "18d1:9302" in result.stdout

            if google_found:
                logger.info("Coral TPU verified accessible inside container")
                return True
            else:
                logger.warning("Coral TPU not visible inside container")
                return False

        except subprocess.SubprocessError as e:
            logger.error(f"Failed to verify Coral access: {e}")
            return False
