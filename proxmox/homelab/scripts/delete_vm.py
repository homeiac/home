#!/usr/bin/env python3
"""
Simple VM deletion script.

Deletes a VM by VMID from a specified Proxmox node.
After deletion, use the idempotent provisioning system to recreate VMs.
"""

import logging
import sys
import time
from pathlib import Path

# Add homelab package to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from homelab.proxmox_api import ProxmoxClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def delete_vm(node_name: str, vmid: int) -> bool:
    """
    Delete VM if it exists on the specified node.

    Args:
        node_name: Proxmox node name (e.g., 'still-fawn')
        vmid: VM ID to delete

    Returns:
        True if VM was deleted, False if it didn't exist
    """
    try:
        logger.info(f"🔍 Connecting to node {node_name}")
        client = ProxmoxClient(node_name)
        proxmox = client.proxmox

        # Check if VM exists
        try:
            vm_status = proxmox.nodes(node_name).qemu(vmid).status.current.get()
            vm_name = vm_status.get('name', f'VM-{vmid}')
            logger.info(f"✅ Found VM: {vm_name} (ID: {vmid}, status: {vm_status.get('status')})")
        except Exception:
            logger.info(f"ℹ️  VM {vmid} does not exist on {node_name}")
            return False

        # Stop VM if running
        if vm_status.get("status") == "running":
            logger.info(f"⏹️  Stopping VM {vmid}")
            proxmox.nodes(node_name).qemu(vmid).status.stop.post()

            # Wait for VM to stop
            timeout = time.time() + 30
            while time.time() < timeout:
                status = proxmox.nodes(node_name).qemu(vmid).status.current.get()
                if status.get("status") == "stopped":
                    logger.info(f"✅ VM {vmid} stopped")
                    break
                time.sleep(2)
            else:
                logger.warning(f"⚠️  VM {vmid} did not stop in time, forcing deletion")

        # Delete VM
        logger.info(f"🗑️  Deleting VM {vmid} ({vm_name})")
        proxmox.nodes(node_name).qemu(vmid).delete()

        # Wait a bit for deletion to complete
        time.sleep(3)

        # Verify deletion
        try:
            proxmox.nodes(node_name).qemu(vmid).status.current.get()
            logger.warning(f"⚠️  VM {vmid} still exists after deletion")
            return False
        except Exception:
            logger.info(f"✅ Successfully deleted VM {vmid}")
            return True

    except Exception as e:
        logger.error(f"❌ Error deleting VM {vmid}: {e}")
        raise


def main():
    """Main execution function."""
    if len(sys.argv) != 3:
        print("Usage: poetry run python scripts/delete_vm.py <node_name> <vmid>")
        print("Example: poetry run python scripts/delete_vm.py still-fawn 108")
        sys.exit(1)

    node_name = sys.argv[1]
    vmid = int(sys.argv[2])

    logger.info("=" * 60)
    logger.info(f"🗑️  VM Deletion Script")
    logger.info("=" * 60)
    logger.info(f"Node: {node_name}")
    logger.info(f"VMID: {vmid}")
    logger.info("=" * 60)

    try:
        deleted = delete_vm(node_name, vmid)

        if deleted:
            logger.info("\n" + "=" * 60)
            logger.info("✅ VM deletion completed successfully")
            logger.info("=" * 60)
            logger.info("\n📍 Next steps:")
            logger.info("1. Run idempotent provisioning:")
            logger.info("   cd proxmox/homelab && poetry run python -m homelab.main")
            logger.info("2. This will detect the missing VM and recreate it")
            logger.info("3. Then join to k3s cluster (manual step for now)")
        else:
            logger.info("ℹ️  No VM found to delete")

        sys.exit(0)

    except Exception as e:
        logger.error(f"\n❌ VM deletion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
