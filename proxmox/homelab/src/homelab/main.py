"""Main entry point for homelab infrastructure provisioning."""

import os

from homelab.config import Config
from homelab.iso_manager import IsoManager
from homelab.k3s_manager import K3sManager
from homelab.vm_manager import VMManager


def join_vms_to_k3s() -> None:
    """
    Ensure all VMs are joined to k3s cluster.

    Idempotent: Skips VMs already in cluster.
    Gracefully handles missing K3S_EXISTING_NODE_IP.
    """
    # Get existing cluster node IP from environment
    existing_node_ip = os.getenv("K3S_EXISTING_NODE_IP")
    if not existing_node_ip:
        print("⚠️  K3S_EXISTING_NODE_IP not set, skipping k3s join")
        return

    k3s = K3sManager()

    # Get cluster token once (will be reused for all nodes)
    try:
        token = k3s.get_cluster_token(existing_node_ip)
    except RuntimeError as e:
        print(f"⚠️  Could not get k3s token: {e}")
        print("⚠️  Skipping k3s join")
        return

    # Join each configured node
    for node in Config.get_nodes():
        name = node["name"]
        vm_hostname = Config.VM_NAME_TEMPLATE.format(node=name)

        # Check if already in cluster
        if k3s.node_in_cluster(vm_hostname):
            print(f"✅ {vm_hostname} already in cluster, skipping")
            continue

        # Install k3s and join cluster
        print(f"🔄 Joining {vm_hostname} to k3s cluster...")
        try:
            server_url = f"https://{existing_node_ip}:6443"
            k3s.install_k3s(vm_hostname, token, server_url)
            print(f"✅ {vm_hostname} joined cluster")
        except RuntimeError as e:
            print(f"❌ Failed to join {vm_hostname}: {e}")
            continue


def main() -> None:
    """Main entry point - fully idempotent provisioning."""
    print("=" * 60)
    print("🚀 Homelab Infrastructure Provisioning")
    print("=" * 60)

    # Phase 1: Ensure ISOs present
    print("\n📀 Phase 1: ISO Management")
    IsoManager.download_iso()
    IsoManager.upload_iso_to_nodes()

    # Phase 2: Ensure VMs exist and healthy
    print("\n🖥️  Phase 2: VM Provisioning")
    VMManager.create_or_update_vm()

    # Phase 3: Ensure VMs joined to k3s cluster
    print("\n☸️  Phase 3: K3s Cluster Join")
    join_vms_to_k3s()

    print("\n" + "=" * 60)
    print("✅ Provisioning Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
