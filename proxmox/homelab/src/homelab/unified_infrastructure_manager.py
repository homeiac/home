#!/usr/bin/env python3
"""
Unified Infrastructure Manager - Homelab's Terraform/Pulumi equivalent.

Single command to reconcile ALL infrastructure components:
- DNS resources (MAAS/OPNsense)
- PBS storage entries
- Storage pools (ZFS)
- Virtual machines
- Containers
- Networks

Usage:
    from homelab.unified_infrastructure_manager import UnifiedInfrastructureManager

    manager = UnifiedInfrastructureManager()
    results = manager.apply("config/homelab.yaml")
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from homelab.pbs_storage_manager import PBSStorageConfig, PBSStorageManager

logger = logging.getLogger(__name__)


class InfrastructureConfig:
    """Model for complete infrastructure configuration."""

    def __init__(self, data: Dict[str, Any]):
        """
        Initialize infrastructure config from dictionary.

        Args:
            data: Complete infrastructure configuration from YAML
        """
        self.metadata = data.get("metadata", {})
        self.dns_resources = data.get("dns_resources", [])
        self.pbs_storages = data.get("pbs_storages", [])
        self.storage_pools = data.get("storage_pools", [])
        self.virtual_machines = data.get("virtual_machines", [])
        self.containers = data.get("containers", [])
        self.networks = data.get("networks", [])

    @property
    def name(self) -> str:
        """Get infrastructure name."""
        return self.metadata.get("name", "homelab")

    @property
    def version(self) -> str:
        """Get infrastructure version."""
        return self.metadata.get("version", "unknown")


class ResourceResult:
    """Result of a resource reconciliation operation."""

    def __init__(
        self,
        resource_type: str,
        resource_name: str,
        action: str,
        success: bool,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize resource result.

        Args:
            resource_type: Type of resource (dns, pbs_storage, etc.)
            resource_name: Name/identifier of the resource
            action: Action taken (created, updated, deleted, no_change)
            success: Whether the operation succeeded
            message: Human-readable message
            details: Additional details about the operation
        """
        self.resource_type = resource_type
        self.resource_name = resource_name
        self.action = action
        self.success = success
        self.message = message
        self.details = details or {}

    def __repr__(self) -> str:
        """String representation."""
        status = "✅" if self.success else "❌"
        return f"{status} {self.resource_type}/{self.resource_name}: {self.action}"


class UnifiedInfrastructureManager:
    """Unified infrastructure manager - orchestrates all components."""

    def __init__(self, proxmox_client: Any):
        """
        Initialize unified infrastructure manager.

        Args:
            proxmox_client: ProxmoxAPI client instance
        """
        self.proxmox = proxmox_client
        self.logger = logger

        # Initialize component managers
        self.pbs_manager = PBSStorageManager(proxmox_client)

        # Track resource order for dependency resolution
        self.resource_order = [
            "dns_resources",  # DNS first - required by other components
            "pbs_storages",  # Storage configuration
            "storage_pools",  # Physical storage
            "networks",  # Network configuration
            "containers",  # Containers
            "virtual_machines",  # VMs last
        ]

    def load_config(self, config_path: str) -> InfrastructureConfig:
        """
        Load complete infrastructure configuration from YAML file.

        Args:
            config_path: Path to unified configuration file

        Returns:
            InfrastructureConfig object

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        self.logger.info(f"📖 Loading infrastructure config from: {config_path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError("Config file is empty")

        config = InfrastructureConfig(data)

        self.logger.info(
            f"✅ Loaded infrastructure '{config.name}' v{config.version}"
        )

        return config

    def validate_config(
        self, config: InfrastructureConfig
    ) -> Dict[str, Any]:
        """
        Validate complete infrastructure configuration.

        Args:
            config: Infrastructure configuration to validate

        Returns:
            Dictionary with validation results
        """
        self.logger.info("🔍 Validating infrastructure configuration...")

        errors = []
        warnings = []
        checks = {}

        # Validate PBS storages
        if config.pbs_storages:
            pbs_errors = []
            pbs_warnings = []

            for storage_data in config.pbs_storages:
                storage_config = PBSStorageConfig(storage_data)

                # Skip validation for disabled storages
                if not storage_config.enabled:
                    continue

                validation = self.pbs_manager.validate_storage_config(
                    storage_config
                )

                if not validation["valid"]:
                    pbs_errors.extend(validation["errors"])

                pbs_warnings.extend(validation["warnings"])

            if pbs_errors:
                errors.append(f"PBS storage validation failed: {len(pbs_errors)} errors")
                checks["pbs_storages"] = {"valid": False, "errors": pbs_errors}
            else:
                checks["pbs_storages"] = {"valid": True, "count": len(config.pbs_storages)}

            if pbs_warnings:
                warnings.extend(pbs_warnings)

        # Add validation for other resource types here
        # TODO: DNS resources validation
        # TODO: Storage pools validation
        # TODO: VMs validation

        is_valid = len(errors) == 0

        result = {
            "valid": is_valid,
            "checks": checks,
            "warnings": warnings,
            "errors": errors,
        }

        if is_valid:
            self.logger.info("✅ Infrastructure configuration is valid")
            if warnings:
                for warning in warnings:
                    self.logger.warning(f"⚠️  {warning}")
        else:
            self.logger.error("❌ Infrastructure configuration has errors")
            for error in errors:
                self.logger.error(f"  - {error}")

        return result

    def reconcile_dns_resources(
        self, dns_resources: List[Dict[str, Any]]
    ) -> List[ResourceResult]:
        """
        Reconcile DNS resources.

        Args:
            dns_resources: List of DNS resource configurations

        Returns:
            List of resource results
        """
        results = []

        if not dns_resources:
            return results

        self.logger.info(f"🌐 Reconciling {len(dns_resources)} DNS resources...")

        for resource in dns_resources:
            name = resource.get("name", "unknown")

            # TODO: Implement DNS reconciliation
            # For now, just log that this would be done
            self.logger.info(
                f"  ℹ️  DNS resource '{name}' reconciliation not yet implemented"
            )

            results.append(
                ResourceResult(
                    resource_type="dns",
                    resource_name=name,
                    action="skipped",
                    success=True,
                    message="DNS reconciliation not yet implemented",
                )
            )

        return results

    def reconcile_pbs_storages(
        self, pbs_storages: List[Dict[str, Any]], skip_validation: bool = False
    ) -> List[ResourceResult]:
        """
        Reconcile PBS storage entries.

        Args:
            pbs_storages: List of PBS storage configurations
            skip_validation: Skip pre-flight validation

        Returns:
            List of resource results
        """
        results = []

        if not pbs_storages:
            return results

        self.logger.info(f"💾 Reconciling {len(pbs_storages)} PBS storage entries...")

        for storage_data in pbs_storages:
            config = PBSStorageConfig(storage_data)

            try:
                result = self.pbs_manager.reconcile_storage(
                    config, skip_validation=skip_validation
                )

                success = result["action"] not in ["error", "validation_failed"]

                results.append(
                    ResourceResult(
                        resource_type="pbs_storage",
                        resource_name=config.name,
                        action=result["action"],
                        success=success,
                        message=f"PBS storage {config.name}: {result['action']}",
                        details=result,
                    )
                )

            except Exception as e:
                self.logger.error(
                    f"❌ Failed to reconcile PBS storage {config.name}: {e}",
                    exc_info=True,
                )

                results.append(
                    ResourceResult(
                        resource_type="pbs_storage",
                        resource_name=config.name,
                        action="error",
                        success=False,
                        message=str(e),
                    )
                )

        return results

    def reconcile_infrastructure(
        self,
        config: InfrastructureConfig,
        skip_validation: bool = False,
        dry_run: bool = False,
    ) -> List[ResourceResult]:
        """
        Reconcile complete infrastructure to match desired state.

        Applies changes in dependency order:
        1. DNS resources (required by other components)
        2. PBS storage
        3. Storage pools
        4. Networks
        5. Containers
        6. Virtual machines

        Args:
            config: Infrastructure configuration
            skip_validation: Skip pre-flight validation
            dry_run: Show what would be done without making changes

        Returns:
            List of all resource results
        """
        self.logger.info("🔄 Starting infrastructure reconciliation...")
        self.logger.info(f"  Infrastructure: {config.name} v{config.version}")

        if dry_run:
            self.logger.info("  Mode: DRY RUN (no changes will be made)")

        all_results = []

        # Apply resources in dependency order
        for resource_type in self.resource_order:
            if resource_type == "dns_resources" and config.dns_resources:
                if not dry_run:
                    results = self.reconcile_dns_resources(config.dns_resources)
                    all_results.extend(results)

            elif resource_type == "pbs_storages" and config.pbs_storages:
                if not dry_run:
                    results = self.reconcile_pbs_storages(
                        config.pbs_storages, skip_validation=skip_validation
                    )
                    all_results.extend(results)
                else:
                    # Dry run - just log what would happen
                    self.logger.info(
                        f"  [DRY RUN] Would reconcile {len(config.pbs_storages)} PBS storages"
                    )

            # TODO: Add other resource types
            # elif resource_type == "storage_pools" and config.storage_pools:
            #     results = self.reconcile_storage_pools(config.storage_pools)
            #     all_results.extend(results)

        return all_results

    def apply(
        self,
        config_path: str,
        skip_validation: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Apply complete infrastructure configuration (like 'terraform apply').

        Args:
            config_path: Path to unified configuration file
            skip_validation: Skip pre-flight validation
            dry_run: Show what would be done without making changes

        Returns:
            Dictionary with apply results and summary
        """
        # Load configuration
        config = self.load_config(config_path)

        # Validate (unless skipped)
        if not skip_validation and not dry_run:
            validation = self.validate_config(config)

            if not validation["valid"]:
                self.logger.error(
                    "❌ Infrastructure validation failed. Fix errors before applying."
                )
                return {
                    "success": False,
                    "validation": validation,
                    "results": [],
                    "summary": {"total": 0, "success": 0, "failed": 0},
                }

        # Reconcile infrastructure
        results = self.reconcile_infrastructure(
            config, skip_validation=skip_validation, dry_run=dry_run
        )

        # Generate summary
        summary = {
            "total": len(results),
            "success": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "by_action": {},
            "by_type": {},
        }

        for result in results:
            # Count by action
            summary["by_action"][result.action] = (
                summary["by_action"].get(result.action, 0) + 1
            )

            # Count by resource type
            summary["by_type"][result.resource_type] = (
                summary["by_type"].get(result.resource_type, 0) + 1
            )

        # Log summary
        self.logger.info("=" * 70)
        self.logger.info("📊 Infrastructure Reconciliation Summary:")
        self.logger.info(f"  Total resources: {summary['total']}")
        self.logger.info(f"  ✅ Success: {summary['success']}")
        self.logger.info(f"  ❌ Failed: {summary['failed']}")

        if summary["by_action"]:
            self.logger.info("  Actions:")
            for action, count in summary["by_action"].items():
                self.logger.info(f"    - {action}: {count}")

        self.logger.info("=" * 70)

        if dry_run:
            self.logger.info("✅ Dry run complete - no changes made")
        elif summary["failed"] == 0:
            self.logger.info("✅ Infrastructure reconciliation complete!")
        else:
            self.logger.warning(
                f"⚠️  Infrastructure reconciliation completed with {summary['failed']} failures"
            )

        return {
            "success": summary["failed"] == 0,
            "results": results,
            "summary": summary,
        }
