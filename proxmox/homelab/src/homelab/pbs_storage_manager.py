#!/usr/bin/env python3
"""
Declarative PBS (Proxmox Backup Server) Storage Management.

Implements GitOps-style declarative configuration for PBS storage entries.
Reconciles desired state (YAML config) with actual state (Proxmox API).

Usage:
    from homelab.pbs_storage_manager import PBSStorageManager

    manager = PBSStorageManager(proxmox_client)
    results = manager.reconcile_from_file("config/pbs-storage.yaml")
"""

import logging
import socket
import ssl
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)


class PBSStorageConfig:
    """Model for PBS storage configuration."""

    def __init__(self, data: Dict[str, Any]):
        """
        Initialize PBS storage config from dictionary.

        Args:
            data: Configuration dictionary from YAML
        """
        self.name: str = data["name"]
        self.enabled: bool = data.get("enabled", True)
        self.server: str = data["server"]
        self.datastore: str = data["datastore"]
        self.content: List[str] = data.get("content", ["backup"])
        self.username: str = data.get("username", "root@pam")
        self.fingerprint: str = data["fingerprint"]
        self.prune_backups: Dict[str, int] = data.get("prune_backups", {})
        self.description: str = data.get("description", "")

    def to_proxmox_params(self) -> Dict[str, Any]:
        """
        Convert config to Proxmox API parameters.

        Returns:
            Dictionary of parameters for Proxmox storage API
        """
        params = {
            "type": "pbs",
            "server": self.server,
            "datastore": self.datastore,
            "content": ",".join(self.content),
            "username": self.username,
            "fingerprint": self.fingerprint,
        }

        # Build prune-backups parameter
        if self.prune_backups:
            prune_parts = []
            for key, value in self.prune_backups.items():
                # Convert snake_case to kebab-case (keep_daily -> keep-daily)
                prune_key = key.replace("_", "-")
                prune_parts.append(f"{prune_key}={value}")
            params["prune-backups"] = ",".join(prune_parts)

        if self.description:
            params["comment"] = self.description

        return params


class PBSStorageManager:
    """Manages PBS storage entries declaratively."""

    def __init__(self, proxmox_client: Any):
        """
        Initialize PBS storage manager.

        Args:
            proxmox_client: ProxmoxAPI client instance
        """
        self.proxmox = proxmox_client
        self.logger = logger

    def resolve_hostname(self, hostname: str) -> Optional[str]:
        """
        Resolve hostname to IP address.

        Args:
            hostname: Hostname to resolve (e.g., 'proxmox-backup-server.maas')

        Returns:
            IP address string or None if resolution fails
        """
        try:
            ip = socket.gethostbyname(hostname)
            self.logger.debug(f"Resolved {hostname} -> {ip}")
            return ip
        except socket.gaierror as e:
            self.logger.error(f"❌ Failed to resolve {hostname}: {e}")
            return None

    def check_pbs_connectivity(
        self, server: str, port: int = 8007, timeout: int = 5
    ) -> Dict[str, Any]:
        """
        Check connectivity to PBS server.

        Args:
            server: PBS server hostname or IP
            port: PBS API port (default: 8007)
            timeout: Connection timeout in seconds

        Returns:
            Dictionary with connectivity check results:
            {
                'reachable': bool,
                'ip': str,
                'dns_resolved': bool,
                'port_open': bool,
                'ssl_valid': bool,
                'error': str (if any)
            }
        """
        result = {
            "reachable": False,
            "ip": None,
            "dns_resolved": False,
            "port_open": False,
            "ssl_valid": False,
            "error": None,
        }

        # Step 1: DNS resolution
        ip = self.resolve_hostname(server)
        if not ip:
            result["error"] = f"DNS resolution failed for {server}"
            return result

        result["dns_resolved"] = True
        result["ip"] = ip

        # Step 2: TCP connectivity check
        try:
            sock = socket.create_connection((ip, port), timeout=timeout)
            result["port_open"] = True
            sock.close()
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            result["error"] = f"Port {port} not reachable on {ip}: {e}"
            return result

        # Step 3: SSL/TLS check (PBS uses HTTPS)
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

            with socket.create_connection((ip, port), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=server) as ssock:
                    result["ssl_valid"] = True
                    result["reachable"] = True
        except ssl.SSLError as e:
            result["error"] = f"SSL handshake failed: {e}"
            return result
        except Exception as e:
            result["error"] = f"Connectivity check failed: {e}"
            return result

        return result

    def validate_storage_config(
        self, config: PBSStorageConfig
    ) -> Dict[str, Any]:
        """
        Validate PBS storage configuration before reconciliation.

        Checks:
        - DNS resolution for server hostname
        - PBS server connectivity
        - Port accessibility
        - SSL/TLS availability

        Args:
            config: PBS storage configuration to validate

        Returns:
            Dictionary with validation results:
            {
                'valid': bool,
                'checks': dict,
                'warnings': list,
                'errors': list
            }
        """
        warnings = []
        errors = []
        checks = {}

        self.logger.info(f"🔍 Validating configuration for {config.name}")

        # Check 1: DNS resolution
        connectivity = self.check_pbs_connectivity(config.server)
        checks["connectivity"] = connectivity

        if not connectivity["dns_resolved"]:
            errors.append(
                f"DNS resolution failed for {config.server}. "
                f"Add DNS entry in MAAS: {config.server} -> <PBS_IP>"
            )

        if not connectivity["port_open"]:
            errors.append(
                f"PBS port 8007 not reachable on {config.server}. "
                f"Ensure PBS is running and firewall allows connections."
            )

        if not connectivity["ssl_valid"]:
            warnings.append(
                f"SSL/TLS check failed for {config.server}. "
                f"This may be normal for self-signed certificates."
            )

        # Check 2: Datastore name validation
        if not config.datastore:
            errors.append("Datastore name is required")

        if len(config.datastore) > 32:
            warnings.append(
                f"Datastore name '{config.datastore}' is longer than 32 characters"
            )

        # Check 3: Fingerprint format validation
        if config.fingerprint:
            expected_format = "XX:XX:XX:..."
            if ":" not in config.fingerprint or len(config.fingerprint) < 47:
                errors.append(
                    f"Fingerprint appears invalid. Expected format: {expected_format}"
                )

        is_valid = len(errors) == 0

        result = {
            "valid": is_valid,
            "checks": checks,
            "warnings": warnings,
            "errors": errors,
        }

        if is_valid:
            self.logger.info(f"✅ Validation passed for {config.name}")
            if warnings:
                for warning in warnings:
                    self.logger.warning(f"⚠️  {warning}")
        else:
            self.logger.error(f"❌ Validation failed for {config.name}")
            for error in errors:
                self.logger.error(f"  - {error}")

        return result

    def get_storage(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get storage configuration from Proxmox.

        Args:
            name: Storage identifier

        Returns:
            Storage configuration dictionary or None if not found
        """
        try:
            return self.proxmox.storage(name).get()
        except Exception:
            return None

    def storage_exists(self, name: str) -> bool:
        """
        Check if storage exists in Proxmox.

        Args:
            name: Storage identifier

        Returns:
            True if storage exists, False otherwise
        """
        return self.get_storage(name) is not None

    def create_storage(self, config: PBSStorageConfig) -> Dict[str, Any]:
        """
        Create PBS storage entry in Proxmox.

        Args:
            config: PBS storage configuration

        Returns:
            Dictionary with operation result:
            {
                'action': 'created',
                'name': str,
                'params': dict
            }
        """
        self.logger.info(f"🆕 Creating PBS storage: {config.name}")

        params = config.to_proxmox_params()
        params["storage"] = config.name

        try:
            self.proxmox.storage.create(**params)
            self.logger.info(f"✅ Storage {config.name} created successfully")
            return {"action": "created", "name": config.name, "params": params}
        except Exception as e:
            self.logger.error(f"❌ Error creating storage {config.name}: {e}")
            raise

    def update_storage(
        self, config: PBSStorageConfig, existing: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update existing PBS storage entry to match desired config.

        Args:
            config: Desired PBS storage configuration
            existing: Current storage configuration from Proxmox

        Returns:
            Dictionary with operation result:
            {
                'action': 'updated' | 'no_change',
                'name': str,
                'changes': dict
            }
        """
        changes = {}
        params = config.to_proxmox_params()

        # Check for differences
        for key, desired_value in params.items():
            # Skip 'type' field as it can't be updated
            if key == "type":
                continue

            current_value = existing.get(key)

            # Normalize values for comparison
            if isinstance(desired_value, str) and isinstance(current_value, str):
                if desired_value.strip() != current_value.strip():
                    changes[key] = {"from": current_value, "to": desired_value}
            elif desired_value != current_value:
                changes[key] = {"from": current_value, "to": desired_value}

        if not changes:
            self.logger.info(f"✅ Storage {config.name} already matches desired state")
            return {"action": "no_change", "name": config.name, "changes": {}}

        # Apply updates
        self.logger.info(f"📝 Updating PBS storage: {config.name}")
        self.logger.debug(f"Changes: {changes}")

        try:
            update_params = {k: v for k, v in params.items() if k != "type"}
            self.proxmox.storage(config.name).put(**update_params)
            self.logger.info(f"✅ Storage {config.name} updated successfully")
            return {"action": "updated", "name": config.name, "changes": changes}
        except Exception as e:
            self.logger.error(f"❌ Error updating storage {config.name}: {e}")
            raise

    def disable_storage(self, name: str) -> Dict[str, Any]:
        """
        Disable PBS storage entry in Proxmox.

        Args:
            name: Storage identifier

        Returns:
            Dictionary with operation result:
            {
                'action': 'disabled',
                'name': str
            }
        """
        existing = self.get_storage(name)
        if not existing:
            self.logger.warning(f"⚠️  Storage {name} not found, skipping disable")
            return {"action": "not_found", "name": name}

        # Check if already disabled
        if existing.get("disable") == 1:
            self.logger.info(f"✅ Storage {name} already disabled")
            return {"action": "no_change", "name": name}

        self.logger.info(f"🔒 Disabling PBS storage: {name}")
        try:
            self.proxmox.storage(name).put(disable=1)
            self.logger.info(f"✅ Storage {name} disabled successfully")
            return {"action": "disabled", "name": name}
        except Exception as e:
            self.logger.error(f"❌ Error disabling storage {name}: {e}")
            raise

    def enable_storage(self, name: str) -> Dict[str, Any]:
        """
        Enable PBS storage entry in Proxmox.

        Args:
            name: Storage identifier

        Returns:
            Dictionary with operation result:
            {
                'action': 'enabled',
                'name': str
            }
        """
        existing = self.get_storage(name)
        if not existing:
            self.logger.warning(f"⚠️  Storage {name} not found, cannot enable")
            return {"action": "not_found", "name": name}

        # Check if already enabled
        if existing.get("disable") != 1:
            self.logger.info(f"✅ Storage {name} already enabled")
            return {"action": "no_change", "name": name}

        self.logger.info(f"🔓 Enabling PBS storage: {name}")
        try:
            self.proxmox.storage(name).put(disable=0)
            self.logger.info(f"✅ Storage {name} enabled successfully")
            return {"action": "enabled", "name": name}
        except Exception as e:
            self.logger.error(f"❌ Error enabling storage {name}: {e}")
            raise

    def reconcile_storage(
        self, config: PBSStorageConfig, skip_validation: bool = False
    ) -> Dict[str, Any]:
        """
        Reconcile single storage entry to match desired state.

        Args:
            config: Desired PBS storage configuration
            skip_validation: Skip pre-flight validation checks (default: False)

        Returns:
            Dictionary with reconciliation result
        """
        # Pre-flight validation (unless skipped)
        if not skip_validation and config.enabled:
            validation = self.validate_storage_config(config)
            if not validation["valid"]:
                self.logger.error(
                    f"❌ Skipping reconciliation for {config.name} due to validation errors"
                )
                return {
                    "action": "validation_failed",
                    "name": config.name,
                    "validation": validation,
                }

        existing = self.get_storage(config.name)

        # Case 1: Storage doesn't exist and should be enabled
        if not existing and config.enabled:
            return self.create_storage(config)

        # Case 2: Storage doesn't exist and should be disabled (no-op)
        if not existing and not config.enabled:
            self.logger.info(
                f"✅ Storage {config.name} doesn't exist and is not desired"
            )
            return {"action": "no_change", "name": config.name}

        # Case 3: Storage exists and should be disabled
        if existing and not config.enabled:
            return self.disable_storage(config.name)

        # Case 4: Storage exists and should be enabled
        if existing and config.enabled:
            # First ensure it's enabled
            enable_result = self.enable_storage(config.name)

            # Then check if configuration needs updates
            update_result = self.update_storage(config, existing)

            # Combine results
            if enable_result["action"] == "enabled":
                return {
                    "action": "enabled_and_updated",
                    "name": config.name,
                    "changes": update_result.get("changes", {}),
                }
            return update_result

        # Should not reach here
        return {"action": "unknown", "name": config.name}

    def load_config(self, config_path: str) -> List[PBSStorageConfig]:
        """
        Load PBS storage configurations from YAML file.

        Args:
            config_path: Path to YAML configuration file

        Returns:
            List of PBS storage configurations
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        self.logger.info(f"📖 Loading PBS storage config from: {config_path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        if not data or "pbs_storages" not in data:
            raise ValueError("Invalid config: missing 'pbs_storages' key")

        configs = []
        for storage_data in data["pbs_storages"]:
            config = PBSStorageConfig(storage_data)
            configs.append(config)
            self.logger.debug(f"Loaded config for: {config.name}")

        self.logger.info(f"✅ Loaded {len(configs)} PBS storage configurations")
        return configs

    def reconcile_from_file(self, config_path: str) -> List[Dict[str, Any]]:
        """
        Reconcile all PBS storage entries from configuration file.

        Args:
            config_path: Path to YAML configuration file

        Returns:
            List of reconciliation results for each storage entry
        """
        configs = self.load_config(config_path)
        results = []

        self.logger.info(f"🔄 Starting reconciliation of {len(configs)} storage entries")

        for config in configs:
            try:
                result = self.reconcile_storage(config)
                results.append(result)
            except Exception as e:
                self.logger.error(
                    f"❌ Failed to reconcile storage {config.name}: {e}",
                    exc_info=True,
                )
                results.append(
                    {"action": "error", "name": config.name, "error": str(e)}
                )

        # Summary
        actions_summary = {}
        for result in results:
            action = result["action"]
            actions_summary[action] = actions_summary.get(action, 0) + 1

        self.logger.info(f"✅ Reconciliation complete: {actions_summary}")

        return results
