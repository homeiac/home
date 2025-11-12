#!/usr/bin/env python3
"""
VM provisioning only - skips ISO management.

Runs only the VMManager.create_or_update_vm() which is idempotent
and will detect missing VMs and create them.
"""

import sys
from pathlib import Path

# Add homelab package to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from homelab.vm_manager import VMManager

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Idempotent VM Provisioning")
    print("=" * 60)
    print("This will:")
    print("  - Check all configured nodes for expected VMs")
    print("  - Create any missing VMs")
    print("  - Skip existing VMs")
    print("=" * 60)
    print()

    VMManager.create_or_update_vm()

    print()
    print("=" * 60)
    print("✅ VM provisioning completed")
    print("=" * 60)
