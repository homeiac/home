"""
Command-line interface for Crucible storage management.
Provides user-friendly access to all storage and VM operations.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.json import JSON
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from homelab.crucible_config import CrucibleConfig
from homelab.enhanced_vm_manager import CrucibleVMManager
from homelab.oxide_storage_api import DiskCreate, DiskSource, SnapshotCreate

# Initialize CLI app and console
app = typer.Typer(
    name="crucible",
    help="Crucible Storage Management CLI",
    add_completion=False
)
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s"
)


# === CONFIGURATION COMMANDS ===

config_app = typer.Typer(help="Configuration management commands")
app.add_typer(config_app, name="config")


@config_app.command("init")
def init_config(
    project_id: str = typer.Option("homelab", help="Project identifier"),
    output: Optional[Path] = typer.Option(None, help="Configuration output file")
) -> None:
    """Initialize Crucible configuration."""
    console.print("🚀 Initializing Crucible configuration...")
    
    try:
        config = CrucibleConfig.from_environment()
        config.validate()
        
        if output:
            with open(output, "w") as f:
                json.dump(config.to_dict(), f, indent=2)
            console.print(f"✅ Configuration saved to {output}")
        else:
            console.print(JSON(json.dumps(config.to_dict(), indent=2)))
    
    except Exception as e:
        console.print(f"❌ Failed to initialize configuration: {e}")
        raise typer.Exit(1)


@config_app.command("validate")
def validate_config(
    config_file: Optional[Path] = typer.Option(None, help="Configuration file to validate")
) -> None:
    """Validate Crucible configuration."""
    console.print("🔍 Validating configuration...")
    
    try:
        if config_file and config_file.exists():
            with open(config_file) as f:
                config_dict = json.load(f)
            # TODO: Create config from dict
            config = CrucibleConfig.from_environment()
        else:
            config = CrucibleConfig.from_environment()
        
        config.validate()
        console.print("✅ Configuration is valid")
        
        # Display configuration summary
        table = Table(title="Configuration Summary")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Storage Sleds", str(len(config.storage_sleds)))
        table.add_row("Replication Factor", str(config.replication_factor))
        table.add_row("Deployment Mode", config.deployment_mode)
        table.add_row("Mocking Enabled", str(config.enable_mocking))
        
        console.print(table)
    
    except Exception as e:
        console.print(f"❌ Configuration validation failed: {e}")
        raise typer.Exit(1)


# === STORAGE COMMANDS ===

storage_app = typer.Typer(help="Storage management commands")
app.add_typer(storage_app, name="storage")


@storage_app.command("status")
def storage_status(
    project_id: str = typer.Option("homelab", help="Project ID"),
    enable_mocking: bool = typer.Option(False, help="Enable mock backend")
) -> None:
    """Show storage cluster status."""
    
    async def _show_status() -> None:
        vm_manager = CrucibleVMManager(project_id, enable_mocking)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Getting cluster status...", total=None)
            status = await vm_manager.get_storage_cluster_status()
            progress.update(task, completed=True)
        
        cluster_info = status["storage_cluster"]
        
        # Main status table
        table = Table(title="Storage Cluster Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total Sleds", str(cluster_info["total_sleds"]))
        table.add_row("Online Sleds", str(cluster_info["online_sleds"]))
        table.add_row("Total Volumes", str(cluster_info["total_volumes"]))
        table.add_row("Total Snapshots", str(cluster_info["total_snapshots"]))
        
        # Capacity information
        total_gb = cluster_info["total_capacity_bytes"] / (1024**3)
        used_gb = cluster_info["used_capacity_bytes"] / (1024**3)
        free_gb = cluster_info["free_capacity_bytes"] / (1024**3)
        
        table.add_row("Total Capacity", f"{total_gb:.1f} GB")
        table.add_row("Used Capacity", f"{used_gb:.1f} GB")
        table.add_row("Free Capacity", f"{free_gb:.1f} GB")
        
        console.print(table)
        
        # Sled details table
        if cluster_info.get("sleds"):
            sled_table = Table(title="Storage Sled Details")
            sled_table.add_column("IP", style="cyan")
            sled_table.add_column("Hostname", style="blue")
            sled_table.add_column("Status", style="green")
            sled_table.add_column("Capacity", style="yellow")
            
            for sled_ip, sled_info in cluster_info["sleds"].items():
                status_icon = "🟢" if sled_info.get("is_online") else "🔴"
                capacity_gb = sled_info.get("total_capacity_bytes", 0) / (1024**3)
                
                sled_table.add_row(
                    sled_ip,
                    sled_info.get("hostname", "unknown"),
                    f"{status_icon} {'Online' if sled_info.get('is_online') else 'Offline'}",
                    f"{capacity_gb:.1f} GB"
                )
            
            console.print(sled_table)
    
    asyncio.run(_show_status())


@storage_app.command("list-disks")
def list_disks(
    project_id: str = typer.Option("homelab", help="Project ID"),
    enable_mocking: bool = typer.Option(False, help="Enable mock backend")
) -> None:
    """List all storage disks."""
    
    async def _list_disks() -> None:
        vm_manager = CrucibleVMManager(project_id, enable_mocking)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Fetching disks...", total=None)
            disks = await vm_manager.storage_api.disk_list()
            progress.update(task, completed=True)
        
        if not disks:
            console.print("No disks found in project.")
            return
        
        table = Table(title=f"Storage Disks - Project: {project_id}")
        table.add_column("Name", style="cyan")
        table.add_column("ID", style="blue")
        table.add_column("Size", style="green")
        table.add_column("State", style="yellow")
        table.add_column("Created", style="magenta")
        
        for disk in disks:
            size_gb = disk["size"] / (1024**3)
            table.add_row(
                disk["name"],
                disk["id"][:8] + "...",
                f"{size_gb:.1f} GB",
                disk["state"],
                disk["time_created"][:10]
            )
        
        console.print(table)
    
    asyncio.run(_list_disks())


@storage_app.command("create-disk")
def create_disk(
    name: str = typer.Argument(..., help="Disk name"),
    size_gb: int = typer.Option(10, help="Disk size in GB"),
    description: Optional[str] = typer.Option(None, help="Disk description"),
    project_id: str = typer.Option("homelab", help="Project ID"),
    enable_mocking: bool = typer.Option(False, help="Enable mock backend")
) -> None:
    """Create a new storage disk."""
    
    async def _create_disk() -> None:
        vm_manager = CrucibleVMManager(project_id, enable_mocking)
        
        disk_request = DiskCreate(
            name=name,
            description=description or f"Disk created via CLI",
            size=size_gb * (1024**3),  # Convert GB to bytes
            disk_source=DiskSource.BLANK,
            block_size=512
        )
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Creating disk {name}...", total=None)
            disk = await vm_manager.storage_api.disk_create(disk_request)
            progress.update(task, completed=True)
        
        console.print(f"✅ Created disk: {disk['name']} (ID: {disk['id']})")
        console.print(f"   Size: {size_gb} GB")
        console.print(f"   State: {disk['state']}")
    
    asyncio.run(_create_disk())


# === VM COMMANDS ===

vm_app = typer.Typer(help="Virtual machine management commands")
app.add_typer(vm_app, name="vm")


@vm_app.command("create")
def create_vm(
    name: str = typer.Argument(..., help="VM name"),
    node: str = typer.Argument(..., help="Proxmox node name"),
    disk_size_gb: int = typer.Option(50, help="Boot disk size in GB"),
    memory_mb: int = typer.Option(4096, help="RAM in MB"),
    cpu_cores: int = typer.Option(2, help="CPU cores"),
    project_id: str = typer.Option("homelab", help="Project ID"),
    enable_mocking: bool = typer.Option(False, help="Enable mock backend")
) -> None:
    """Create a VM with Crucible storage."""
    
    async def _create_vm() -> None:
        vm_manager = CrucibleVMManager(project_id, enable_mocking)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Creating VM {name}...", total=None)
            
            result = await vm_manager.create_vm_with_storage(
                vm_name=name,
                node_name=node,
                disk_size_gb=disk_size_gb,
                memory_mb=memory_mb,
                cpu_cores=cpu_cores
            )
            
            progress.update(task, completed=True)
        
        if result["status"] == "success":
            console.print(f"✅ Successfully created VM: {name}")
            
            vm_info = result["vm"]
            table = Table(title=f"VM Details: {name}")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("VMID", str(vm_info["vmid"]))
            table.add_row("Node", vm_info["node"])
            table.add_row("Memory", f"{vm_info['memory_mb']} MB")
            table.add_row("CPU Cores", str(vm_info["cpu_cores"]))
            table.add_row("Boot Disk Size", f"{vm_info['disk_size_gb']} GB")
            table.add_row("Storage Disk ID", vm_info["disk_id"])
            
            console.print(table)
        else:
            console.print(f"❌ Failed to create VM: {name}")
    
    asyncio.run(_create_vm())


@vm_app.command("list")
def list_vms(
    project_id: str = typer.Option("homelab", help="Project ID"),
    enable_mocking: bool = typer.Option(False, help="Enable mock backend")
) -> None:
    """List all managed VMs."""
    
    async def _list_vms() -> None:
        vm_manager = CrucibleVMManager(project_id, enable_mocking)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Fetching VMs...", total=None)
            vms = await vm_manager.list_managed_vms()
            progress.update(task, completed=True)
        
        if not vms:
            console.print("No managed VMs found.")
            return
        
        table = Table(title=f"Managed VMs - Project: {project_id}")
        table.add_column("Name", style="cyan")
        table.add_column("VMID", style="blue")
        table.add_column("Node", style="green")
        table.add_column("Memory", style="yellow")
        table.add_column("Disk Size", style="magenta")
        table.add_column("Status", style="red")
        
        for vm in vms:
            if "error" not in vm:
                config = vm.get("configuration", {})
                table.add_row(
                    vm["vm_name"],
                    str(config.get("vmid", "N/A")),
                    config.get("node", "N/A"),
                    f"{config.get('memory_mb', 0)} MB",
                    f"{config.get('disk_size_gb', 0)} GB",
                    "Running" if "proxmox_status" in vm else "Unknown"
                )
            else:
                table.add_row(
                    vm["vm_name"],
                    "N/A",
                    "N/A",
                    "N/A",
                    "N/A",
                    f"Error: {vm['error']}"
                )
        
        console.print(table)
    
    asyncio.run(_list_vms())


@vm_app.command("clone")
def clone_vm(
    source: str = typer.Argument(..., help="Source VM name"),
    target: str = typer.Argument(..., help="Target VM name"),
    node: str = typer.Argument(..., help="Target Proxmox node"),
    snapshot_name: Optional[str] = typer.Option(None, help="Specific snapshot name"),
    project_id: str = typer.Option("homelab", help="Project ID"),
    enable_mocking: bool = typer.Option(False, help="Enable mock backend")
) -> None:
    """Clone a VM from storage snapshot."""
    
    async def _clone_vm() -> None:
        vm_manager = CrucibleVMManager(project_id, enable_mocking)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Cloning {source} to {target}...", total=None)
            
            result = await vm_manager.clone_vm_from_snapshot(
                source_vm_name=source,
                target_vm_name=target,
                node_name=node,
                snapshot_name=snapshot_name
            )
            
            progress.update(task, completed=True)
        
        if result["status"] == "success":
            console.print(f"✅ Successfully cloned {source} to {target}")
        else:
            console.print(f"❌ Failed to clone VM")
    
    asyncio.run(_clone_vm())


# === MAIN ENTRY POINT ===

@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging")
) -> None:
    """
    Crucible Storage Management CLI
    
    Manage distributed storage and VMs with Oxide-style APIs.
    """
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif verbose:
        logging.getLogger().setLevel(logging.INFO)


if __name__ == "__main__":
    app()