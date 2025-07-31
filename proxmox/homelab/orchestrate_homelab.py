#!/usr/bin/env python3
"""
orchestrate_homelab.py

Single script to maintain homelab infrastructure consistency.
This is the "one script to rule them all" that:

1. Provisions K3s VMs on all Proxmox nodes
2. Registers all VMs and critical services in MAAS
3. Updates monitoring across all Uptime Kuma instances
4. Generates documentation from current state

Usage:
    poetry run python orchestrate_homelab.py          # Full orchestration
    poetry run python orchestrate_homelab.py --dry-run  # Show what would be done
    
Environment Requirements:
    - .env file with CRITICAL_SERVICE_* configurations
    - SSH access to Proxmox nodes and MAAS server
    - Uptime Kuma instances accessible
"""

import argparse
import sys
from pathlib import Path

# Add src directory to path so we can import homelab modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

from homelab.infrastructure_orchestrator import InfrastructureOrchestrator


def main():
    parser = argparse.ArgumentParser(
        description="Homelab Infrastructure Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    poetry run python orchestrate_homelab.py
        Full orchestration - provisions VMs, registers in MAAS, updates monitoring
    
    poetry run python orchestrate_homelab.py --dry-run
        Show what would be done without making changes
        
This script is idempotent - safe to run multiple times.
        """
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - showing what would be done:")
        print()
        print("Steps that would be executed:")
        print("1. 🚀 Provision K3s VMs on all Proxmox nodes")
        print("2. 📝 Register K3s VMs in MAAS for persistent IPs")
        print("3. 🔧 Register critical services (Uptime Kuma) in MAAS")
        print("4. 📊 Update monitoring configuration")
        print("5. 📚 Generate documentation from current state")
        print()
        print("To run for real: poetry run python orchestrate_homelab.py")
        return
    
    print("🎯 Homelab Infrastructure Orchestration")
    print("=" * 50)
    print()
    
    # Create and run orchestrator
    orchestrator = InfrastructureOrchestrator()
    results = orchestrator.orchestrate()
    
    # Print final summary
    summary = results.get("orchestration_summary", {})
    if summary.get("status") == "success":
        print()
        print("✅ All steps completed successfully!")
        print()
        print("Next steps:")
        print("- Verify DNS resolution: nslookup uptime-kuma-pve.maas")
        print("- Check monitoring: http://uptime-kuma-pve.maas:3001")
        print("- Test reboot persistence by rebooting a container")
        return 0
    else:
        print()
        print("❌ Orchestration failed!")
        print(f"Error: {summary.get('error', 'Unknown error')}")
        print()
        print("Check logs above for details.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)