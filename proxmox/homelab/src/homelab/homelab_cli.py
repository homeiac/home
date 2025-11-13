#!/usr/bin/env python3
"""
Unified Homelab CLI - Single command for all infrastructure.

Like Terraform/Pulumi but for your homelab:
    poetry run homelab apply       # Apply all infrastructure
    poetry run homelab validate    # Validate configuration
    poetry run homelab status      # Show current state

All infrastructure defined in single config file: config/homelab.yaml
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from homelab.config import Config
from homelab.proxmox_api import ProxmoxClient
from homelab.unified_infrastructure_manager import UnifiedInfrastructureManager

# Initialize CLI app and console
app = typer.Typer(
    name="homelab",
    help="Unified Infrastructure Management CLI",
    add_completion=False
)
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def get_manager() -> UnifiedInfrastructureManager:
    """Get unified infrastructure manager with Proxmox client."""
    try:
        # Get first PVE host from config or use default
        nodes = Config.get_nodes()
        if not nodes:
            host = "pve.maas"
        else:
            host = nodes[0]["name"]

        proxmox_client = ProxmoxClient(host=host, verify_ssl=False)

        if proxmox_client.proxmox is None:
            console.print(f"❌ Could not connect to Proxmox")
            raise typer.Exit(1)

        return UnifiedInfrastructureManager(proxmox_client.proxmox)

    except Exception as e:
        console.print(f"❌ Failed to connect to Proxmox: {e}")
        raise typer.Exit(1)


@app.command("apply")
def apply_infrastructure(
    config_file: Path = typer.Option(
        "config/homelab.yaml",
        "--config", "-c",
        help="Unified infrastructure configuration file"
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
    Apply complete infrastructure configuration (like 'terraform apply').

    Reconciles all infrastructure components to match desired state:
    - DNS resources (MAAS/OPNsense)
    - PBS storage entries
    - Storage pools (ZFS)
    - Virtual machines
    - Containers
    - Networks

    Changes are applied in dependency order to ensure correctness.
    """
    console.print(f"🚀 Applying infrastructure from: {config_file}")

    if not config_file.exists():
        console.print(f"❌ Config file not found: {config_file}")
        raise typer.Exit(1)

    if dry_run:
        console.print("🔍 DRY RUN MODE - No changes will be made\n")

    try:
        manager = get_manager()

        # Apply infrastructure
        result = manager.apply(
            str(config_file),
            skip_validation=skip_validation,
            dry_run=dry_run
        )

        # Display results table
        if result["results"]:
            table = Table(title="Infrastructure Changes")
            table.add_column("Resource Type", style="cyan")
            table.add_column("Resource Name", style="blue")
            table.add_column("Action", style="yellow")
            table.add_column("Status", style="bold")

            for res in result["results"]:
                status = "✅" if res.success else "❌"
                table.add_row(
                    res.resource_type,
                    res.resource_name,
                    res.action,
                    status
                )

            console.print(table)

        # Display summary
        console.print("\n" + "=" * 70)
        console.print("[bold]Summary:[/bold]")
        summary = result["summary"]

        console.print(f"  Total resources: {summary['total']}")
        console.print(f"  ✅ Success: {summary['success']}")
        console.print(f"  ❌ Failed: {summary['failed']}")

        if summary.get("by_action"):
            console.print("\n  [bold]Actions taken:[/bold]")
            for action, count in summary["by_action"].items():
                console.print(f"    - {action}: {count}")

        console.print("=" * 70)

        if not result["success"]:
            console.print("\n❌ Infrastructure apply completed with errors")
            raise typer.Exit(1)

        if dry_run:
            console.print("\n✅ Dry run complete - no changes made")
        else:
            console.print("\n✅ Infrastructure apply complete!")

    except Exception as e:
        console.print(f"\n❌ Failed to apply infrastructure: {e}")
        logger.exception("Apply error")
        raise typer.Exit(1)


@app.command("validate")
def validate_infrastructure(
    config_file: Path = typer.Option(
        "config/homelab.yaml",
        "--config", "-c",
        help="Unified infrastructure configuration file"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Show detailed validation results"
    )
) -> None:
    """
    Validate infrastructure configuration without making changes.

    Checks:
    - Configuration syntax
    - DNS resolution for all hostnames
    - Connectivity to all services
    - Resource dependencies
    """
    console.print(f"🔍 Validating infrastructure: {config_file}")

    if not config_file.exists():
        console.print(f"❌ Config file not found: {config_file}")
        raise typer.Exit(1)

    try:
        manager = get_manager()

        # Load and validate config
        config = manager.load_config(str(config_file))
        validation = manager.validate_config(config)

        # Display validation results
        table = Table(title="Validation Results")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Details", style="yellow")

        for component, check in validation["checks"].items():
            if check.get("valid"):
                status = "✅ Valid"
                details = f"{check.get('count', 0)} resources"
            else:
                status = "❌ Invalid"
                details = f"{len(check.get('errors', []))} errors"

            table.add_row(component, status, details)

        console.print(table)

        # Show errors and warnings if verbose
        if verbose or not validation["valid"]:
            if validation["errors"]:
                console.print("\n[bold red]Errors:[/bold red]")
                for error in validation["errors"]:
                    console.print(f"  ❌ {error}")

            if validation["warnings"]:
                console.print("\n[bold yellow]Warnings:[/bold yellow]")
                for warning in validation["warnings"]:
                    console.print(f"  ⚠️  {warning}")

        if validation["valid"]:
            console.print("\n✅ Infrastructure configuration is valid")
        else:
            console.print("\n❌ Infrastructure configuration has errors")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"\n❌ Validation failed: {e}")
        logger.exception("Validation error")
        raise typer.Exit(1)


@app.command("status")
def show_status(
    config_file: Path = typer.Option(
        "config/homelab.yaml",
        "--config", "-c",
        help="Unified infrastructure configuration file"
    )
) -> None:
    """
    Show current infrastructure status.

    Displays current state of all managed resources.
    """
    console.print(f"📊 Infrastructure Status")

    try:
        manager = get_manager()

        # Load config
        config = manager.load_config(str(config_file))

        console.print(f"\n[bold]Infrastructure:[/bold] {config.name} v{config.version}")

        # Show resource counts
        table = Table(title="Resource Counts")
        table.add_column("Resource Type", style="cyan")
        table.add_column("Count", style="green")

        resource_types = [
            ("DNS Resources", len(config.dns_resources)),
            ("PBS Storages", len(config.pbs_storages)),
            ("Storage Pools", len(config.storage_pools)),
            ("Networks", len(config.networks)),
            ("Containers", len(config.containers)),
            ("Virtual Machines", len(config.virtual_machines)),
        ]

        total = 0
        for resource_type, count in resource_types:
            if count > 0:
                table.add_row(resource_type, str(count))
                total += count

        table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")

        console.print(table)

        # TODO: Query actual Proxmox state and compare with desired state
        console.print("\n[dim]ℹ️  Detailed state comparison coming soon[/dim]")

    except Exception as e:
        console.print(f"\n❌ Failed to get status: {e}")
        logger.exception("Status error")
        raise typer.Exit(1)


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging")
) -> None:
    """
    Unified Homelab Infrastructure Management

    Single command to manage all infrastructure components.
    Like Terraform/Pulumi but designed specifically for homelabs.

    Configuration: config/homelab.yaml
    """
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif verbose:
        logging.getLogger().setLevel(logging.INFO)


if __name__ == "__main__":
    app()
