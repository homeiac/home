#!/usr/bin/env python3
"""
CLI commands for PBS (Proxmox Backup Server) storage management.

Provides declarative, GitOps-style management of PBS storage entries.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from homelab.config import Config
from homelab.pbs_storage_manager import PBSStorageManager
from homelab.proxmox_api import ProxmoxClient

# Initialize CLI app and console
app = typer.Typer(
    name="pbs",
    help="PBS Storage Management CLI",
    add_completion=False
)
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def get_manager() -> PBSStorageManager:
    """Get PBS storage manager with Proxmox client."""
    try:
        # Get first PVE host from config or use default
        nodes = Config.get_nodes()
        if not nodes:
            # Fallback to pve.maas
            host = "pve.maas"
        else:
            host = nodes[0]["name"]

        proxmox_client = ProxmoxClient(host=host, verify_ssl=False)

        # Get the actual Proxmox API object
        if proxmox_client.proxmox is None:
            console.print(f"❌ Could not connect to Proxmox (CLI mode not supported for PBS management)")
            raise typer.Exit(1)

        return PBSStorageManager(proxmox_client.proxmox)
    except Exception as e:
        console.print(f"❌ Failed to connect to Proxmox: {e}")
        raise typer.Exit(1)


@app.command("validate")
def validate_config(
    config_file: Path = typer.Option(
        "config/pbs-storage.yaml",
        "--config", "-c",
        help="PBS storage configuration file"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Show detailed validation results"
    )
) -> None:
    """
    Validate PBS storage configuration without making changes.

    Checks:
    - DNS resolution for PBS servers
    - PBS connectivity on port 8007
    - Configuration syntax and completeness
    """
    console.print(f"🔍 Validating PBS storage configuration: {config_file}")

    if not config_file.exists():
        console.print(f"❌ Config file not found: {config_file}")
        raise typer.Exit(1)

    try:
        manager = get_manager()
        configs = manager.load_config(str(config_file))

        console.print(f"📋 Found {len(configs)} storage configurations")

        all_valid = True
        results = []

        for config in configs:
            validation = manager.validate_storage_config(config)
            results.append((config, validation))

            if not validation["valid"]:
                all_valid = False

        # Display results table
        table = Table(title="Validation Results")
        table.add_column("Storage", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("DNS", style="green")
        table.add_column("Port 8007", style="green")
        table.add_column("Issues", style="yellow")

        for config, validation in results:
            checks = validation["checks"]
            connectivity = checks.get("connectivity", {})

            status = "✅ Valid" if validation["valid"] else "❌ Invalid"
            dns_status = "✅" if connectivity.get("dns_resolved") else "❌"
            port_status = "✅" if connectivity.get("port_open") else "❌"

            issues = len(validation["errors"]) + len(validation["warnings"])
            issues_str = f"{len(validation['errors'])} errors, {len(validation['warnings'])} warnings"

            table.add_row(
                config.name,
                status,
                dns_status,
                port_status,
                issues_str if issues > 0 else "-"
            )

        console.print(table)

        # Show details if verbose
        if verbose:
            for config, validation in results:
                if validation["errors"] or validation["warnings"]:
                    console.print(f"\n[bold]{config.name}[/bold]:")

                    for error in validation["errors"]:
                        console.print(f"  ❌ {error}")

                    for warning in validation["warnings"]:
                        console.print(f"  ⚠️  {warning}")

        if all_valid:
            console.print("\n✅ All configurations are valid")
        else:
            console.print("\n❌ Some configurations have errors")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"❌ Validation failed: {e}")
        logger.exception("Validation error")
        raise typer.Exit(1)


@app.command("apply")
def apply_config(
    config_file: Path = typer.Option(
        "config/pbs-storage.yaml",
        "--config", "-c",
        help="PBS storage configuration file"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be changed without making changes"
    ),
    skip_validation: bool = typer.Option(
        False,
        "--skip-validation",
        help="Skip pre-flight validation checks"
    )
) -> None:
    """
    Apply PBS storage configuration (GitOps-style reconciliation).

    Reconciles actual Proxmox storage state with desired configuration:
    - Creates missing storage entries
    - Updates existing entries to match config
    - Enables/disables storage based on config
    """
    console.print(f"🔄 Applying PBS storage configuration: {config_file}")

    if not config_file.exists():
        console.print(f"❌ Config file not found: {config_file}")
        raise typer.Exit(1)

    if dry_run:
        console.print("🔍 DRY RUN MODE - No changes will be made")

    try:
        manager = get_manager()

        # Load configurations
        configs = manager.load_config(str(config_file))
        console.print(f"📋 Loaded {len(configs)} storage configurations\n")

        # Reconcile each storage entry
        results = []
        for config in configs:
            console.print(f"Processing: {config.name} ({'enabled' if config.enabled else 'disabled'})")

            if dry_run:
                # Just validate
                if config.enabled and not skip_validation:
                    validation = manager.validate_storage_config(config)
                    if validation["valid"]:
                        console.print(f"  ✅ Would reconcile {config.name}")
                    else:
                        console.print(f"  ❌ Validation failed for {config.name}")
                else:
                    console.print(f"  ℹ️  Would process {config.name}")
                continue

            # Actual reconciliation
            result = manager.reconcile_storage(config, skip_validation=skip_validation)
            results.append(result)

            action = result["action"]
            if action == "created":
                console.print(f"  🆕 Created storage {config.name}")
            elif action == "updated":
                console.print(f"  📝 Updated storage {config.name}")
            elif action == "disabled":
                console.print(f"  🔒 Disabled storage {config.name}")
            elif action == "enabled":
                console.print(f"  🔓 Enabled storage {config.name}")
            elif action == "no_change":
                console.print(f"  ✅ No changes needed for {config.name}")
            elif action == "validation_failed":
                console.print(f"  ❌ Validation failed for {config.name}")
            else:
                console.print(f"  ℹ️  {action}: {config.name}")

        if dry_run:
            console.print("\n🔍 Dry run complete - no changes made")
            return

        # Summary
        console.print("\n" + "=" * 50)
        console.print("📊 Reconciliation Summary:")

        action_counts = {}
        for result in results:
            action = result["action"]
            action_counts[action] = action_counts.get(action, 0) + 1

        for action, count in action_counts.items():
            console.print(f"  {action}: {count}")

        console.print("=" * 50)
        console.print("✅ Reconciliation complete")

    except Exception as e:
        console.print(f"❌ Failed to apply configuration: {e}")
        logger.exception("Apply error")
        raise typer.Exit(1)


@app.command("status")
def show_status(
    storage_name: Optional[str] = typer.Argument(
        None,
        help="Specific storage name to check (optional)"
    )
) -> None:
    """
    Show current PBS storage status from Proxmox.

    Displays all PBS storage entries or details for a specific one.
    """
    try:
        manager = get_manager()

        if storage_name:
            # Show specific storage
            storage = manager.get_storage(storage_name)
            if not storage:
                console.print(f"❌ Storage '{storage_name}' not found")
                raise typer.Exit(1)

            console.print(f"\n[bold]Storage: {storage_name}[/bold]")
            for key, value in storage.items():
                console.print(f"  {key}: {value}")
        else:
            # Show all PBS storages
            all_storages = manager.proxmox.storage.get()
            pbs_storages = [s for s in all_storages if s.get("type") == "pbs"]

            if not pbs_storages:
                console.print("ℹ️  No PBS storage entries found")
                return

            table = Table(title="PBS Storage Entries")
            table.add_column("Name", style="cyan")
            table.add_column("Server", style="green")
            table.add_column("Datastore", style="blue")
            table.add_column("Status", style="bold")

            for storage in pbs_storages:
                name = storage.get("storage", "")
                server = storage.get("server", "")
                datastore = storage.get("datastore", "")
                disabled = storage.get("disable", 0)

                status = "🔒 Disabled" if disabled else "✅ Enabled"

                table.add_row(name, server, datastore, status)

            console.print(table)

    except Exception as e:
        console.print(f"❌ Failed to retrieve storage status: {e}")
        logger.exception("Status error")
        raise typer.Exit(1)


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging")
) -> None:
    """
    PBS (Proxmox Backup Server) Storage Management

    Declarative, GitOps-style management of PBS storage entries in Proxmox VE.
    """
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif verbose:
        logging.getLogger().setLevel(logging.INFO)


if __name__ == "__main__":
    app()
