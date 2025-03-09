from homelab.proxmox_api import ProxmoxClient
from homelab.resource_manager import ResourceManager
from homelab.config import Config


class VMManager:
    """Handles VM creation on Proxmox."""

    @staticmethod
    def create_vm():
        """Create VM on each Proxmox node with optimal resource allocation."""
        nodes = Config.get_nodes()
        for node in nodes:
            client = ProxmoxClient(node["name"])
            node_status = client.get_node_status()
            vm_cpus, vm_memory = ResourceManager.calculate_vm_resources(
                node_status, node["cpu_ratio"], node["memory_ratio"]
            )

            vmid = 100 + nodes.index(node)  # Assign VM ID dynamically
            vm_name = f"k3s_vm_{node['name']}"

            print(
                f"Creating VM {vm_name} on {node['name']} with {vm_cpus} CPUs and {vm_memory // (1024 * 1024)} MB memory."
            )
            client.proxmox.nodes(node["name"]).qemu.create(
                vmid=vmid,
                name=vm_name,
                cores=vm_cpus,
                memory=vm_memory // (1024 * 1024),  # Convert bytes to MB
                storage=node["storage"],
                iso=f"{node['storage']}:iso/{Config.ISO_NAME}",
                net0="virtio,bridge=vmbr0",
            )
            print(f"VM {vm_name} created on {node['name']}.")
