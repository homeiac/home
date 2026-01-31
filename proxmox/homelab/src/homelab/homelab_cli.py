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
from homelab.node_exporter_manager import (
    apply_from_config as apply_node_exporter,
    get_status_from_config as get_node_exporter_status,
    print_status_table,
)

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


# === MONITORING COMMANDS ===

monitoring_app = typer.Typer(help="Monitoring infrastructure management")
app.add_typer(monitoring_app, name="monitoring")


@monitoring_app.command("apply")
def monitoring_apply(
    config_file: Path = typer.Option(
        "config/cluster.yaml",
        "--config", "-c",
        help="Cluster configuration file"
    ),
    host: Optional[str] = typer.Option(
        None,
        "--host", "-H",
        help="Deploy to specific host only"
    )
) -> None:
    """
    Apply monitoring components to Proxmox hosts.

    Deploys node-exporter to all enabled hosts in cluster.yaml.
    Idempotent - safe to run multiple times.
    """
    console.print(f"🚀 Applying monitoring from: {config_file}")

    if not config_file.exists():
        console.print(f"❌ Config file not found: {config_file}")
        raise typer.Exit(1)

    try:
        if host:
            from homelab.node_exporter_manager import NodeExporterManager
            console.print(f"Deploying to {host}...")
            with NodeExporterManager(host, config_path=config_file) as manager:
                result = manager.deploy()

            status_icon = "✅" if result["status"] == "success" else "❌"
            console.print(f"\n{status_icon} {host}: {result['status']}")
            if result.get("hwmon_sensors"):
                console.print(f"   Sensors: {', '.join(result['hwmon_sensors'])}")
            if result.get("error"):
                console.print(f"   Error: {result['error']}")
        else:
            results = apply_node_exporter(config_file)
            print_status_table(results)

            success = sum(1 for r in results if r.get("status") == "success")
            failed = sum(1 for r in results if r.get("status") == "failed")
            already = sum(1 for r in results if "already_installed" in r.get("actions", []))

            console.print(f"\n✅ {success} deployed, {already} already installed, {failed} failed")

    except Exception as e:
        console.print(f"❌ Failed: {e}")
        logger.exception("Monitoring apply error")
        raise typer.Exit(1)


@monitoring_app.command("status")
def monitoring_status(
    config_file: Path = typer.Option(
        "config/cluster.yaml",
        "--config", "-c",
        help="Cluster configuration file"
    )
) -> None:
    """
    Show monitoring component status on all hosts.

    Checks node-exporter installation and service status.
    """
    console.print(f"📊 Monitoring Status (from {config_file})")

    if not config_file.exists():
        console.print(f"❌ Config file not found: {config_file}")
        raise typer.Exit(1)

    try:
        results = get_node_exporter_status(config_file)
        print_status_table(results)

        running = sum(1 for r in results if r.get("running"))
        total = len(results)
        console.print(f"\n{running}/{total} hosts have node-exporter running")

    except Exception as e:
        console.print(f"❌ Failed: {e}")
        logger.exception("Monitoring status error")
        raise typer.Exit(1)


# === STORAGE COMMANDS ===

storage_app = typer.Typer(help="Storage infrastructure management")
app.add_typer(storage_app, name="storage")

mirror_app = typer.Typer(help="ZFS mirror management")
storage_app.add_typer(mirror_app, name="mirror")


@mirror_app.command("apply")
def mirror_apply(
    config_file: Path = typer.Option(
        "config/cluster.yaml",
        "--config", "-c",
        help="Cluster configuration file"
    ),
    host: str = typer.Option(
        ...,
        "--host", "-H",
        help="Proxmox host to configure mirror on"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be done without making changes"
    ),
) -> None:
    """
    Apply ZFS mirror configuration to a Proxmox host.

    Reads zfs_mirrors from cluster.yaml and performs idempotent
    mirror setup: partition cloning, GUID randomization, boot config,
    mirror attach, and resilver verification.
    """
    if not config_file.exists():
        console.print(f"Config file not found: {config_file}")
        raise typer.Exit(1)

    mode = "DRY RUN" if dry_run else "APPLY"
    console.print(f"[bold]ZFS Mirror {mode}[/bold] on {host}")

    try:
        from homelab.zfs_mirror_manager import ZfsMirrorManager

        with ZfsMirrorManager(host, config_path=config_file) as mgr:
            result = mgr.apply(dry_run=dry_run)

        if not result["mirrors"]:
            console.print(f"No zfs_mirrors configured for {host}")
            raise typer.Exit(0)

        for m in result["mirrors"]:
            console.print(f"\n[bold]Pool: {m['pool']}[/bold]  status: {m['status']}")
            console.print(f"  existing: {m['existing_disk']}")
            console.print(f"  new:      {m['new_disk']}")

            if m.get("failed_checks"):
                console.print(f"  [red]Pre-flight failures: {m['failed_checks']}[/red]")

            for step in m.get("steps", []):
                icon = {"done": "[green]done[/green]",
                        "skipped": "[dim]skipped[/dim]",
                        "would_execute": "[yellow]would execute[/yellow]",
                        "failed": "[red]FAILED[/red]"}.get(step["status"], step["status"])
                console.print(f"  {step['step']}: {icon}")
                if step.get("error"):
                    console.print(f"    error: {step['error']}")
                if step.get("cmd"):
                    console.print(f"    cmd: {step['cmd']}")
                if step.get("cmds"):
                    for c in step["cmds"]:
                        console.print(f"    cmd: {c}")

            if m.get("resilver"):
                r = m["resilver"]
                console.print(f"  resilver: {r.get('scan', 'n/a')}")

        if result["success"]:
            console.print(f"\n[green]Mirror operation completed successfully[/green]")
        else:
            console.print(f"\n[red]Mirror operation had failures[/red]")
            raise typer.Exit(1)

    except ValueError as e:
        console.print(f"Configuration error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"Failed: {e}")
        logger.exception("Mirror apply error")
        raise typer.Exit(1)


@mirror_app.command("status")
def mirror_status(
    config_file: Path = typer.Option(
        "config/cluster.yaml",
        "--config", "-c",
        help="Cluster configuration file"
    ),
    host: Optional[str] = typer.Option(
        None,
        "--host", "-H",
        help="Specific host (default: all hosts with mirrors)"
    ),
) -> None:
    """
    Show ZFS mirror status for Proxmox hosts.

    Displays mirror topology, resilver progress, and disk status.
    """
    if not config_file.exists():
        console.print(f"Config file not found: {config_file}")
        raise typer.Exit(1)

    try:
        from homelab.zfs_mirror_manager import load_cluster_config, ZfsMirrorManager

        config = load_cluster_config(config_file)
        nodes = config.get("nodes", [])

        # Filter to hosts with zfs_mirrors configured
        targets = []
        for node in nodes:
            if node.get("zfs_mirrors"):
                if host is None or node["name"] == host:
                    targets.append(node["name"])

        if not targets:
            msg = f"No zfs_mirrors configured"
            if host:
                msg += f" for {host}"
            console.print(msg)
            raise typer.Exit(0)

        table = Table(title="ZFS Mirror Status")
        table.add_column("Host", style="cyan")
        table.add_column("Pool", style="blue")
        table.add_column("Mirror", style="bold")
        table.add_column("State")
        table.add_column("Disks")
        table.add_column("Scan")

        for hostname in targets:
            try:
                with ZfsMirrorManager(hostname, config=config) as mgr:
                    s = mgr.status()
                    for m in s["mirrors"]:
                        mirror_icon = "[green]Yes[/green]" if m["is_mirror"] else "[red]No[/red]"
                        disk_count = str(len(m["vdev_disks"]))
                        scan = m["scan"][:50] if m["scan"] else "n/a"
                        table.add_row(
                            hostname,
                            m["pool"],
                            mirror_icon,
                            m["state"],
                            disk_count,
                            scan,
                        )
            except Exception as e:
                table.add_row(hostname, "?", "?", f"[red]ERROR: {e}[/red]", "", "")

        console.print(table)

    except Exception as e:
        console.print(f"Failed: {e}")
        logger.exception("Mirror status error")
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
    Monitoring: config/cluster.yaml
    """
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif verbose:
        logging.getLogger().setLevel(logging.INFO)


if __name__ == "__main__":
    app()
