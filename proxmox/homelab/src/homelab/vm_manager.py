from homelab.proxmox_api import ProxmoxClient
from homelab.resource_manager import ResourceManager
from homelab.gpu_manager import GPUManager
from homelab.config import Config


class VMManager:
    """Handles VM creation on Proxmox."""

    def vm_exists(proxmox, node_name):
        """Check if a VM with the given naming convention exists on the node."""
        expected_name = f"k3s-vm-{node_name.replace('_', '-')}"

        for vm in proxmox.nodes(node_name).qemu.get():
            if vm.get("name") == expected_name:
                return vm["vmid"]  # VM already exists

        return None


    def get_next_available_vmid(proxmox):
        """Finds the next available VM ID in Proxmox, ensuring no conflicts with both VMs and Containers."""

        used_ids = set()

        # Get all VM IDs
        for pve_node in proxmox.nodes.get():
            for vm in proxmox.nodes(pve_node['node']).qemu.get():
                used_ids.add(int(vm["vmid"]))

        # Get all LXC container IDs
        for pve_node in proxmox.nodes.get():
            for container in proxmox.nodes(pve_node['node']).lxc.get():
                used_ids.add(int(container["vmid"]))

        # Start looking for an available VMID from 100 upwards
        for vmid in range(100, 9999):
            if vmid not in used_ids:
                return vmid

        raise Exception("No available VM IDs found!")

    @staticmethod
    def create_or_update_vm():
        """Create VM on each Proxmox node with optimal resource allocation."""
        nodes = Config.get_nodes()
        for node in nodes:
            client = ProxmoxClient(node["name"])

            vmid = VMManager.vm_exists(client.proxmox, node["name"])

            # Check if a VM with the expected name already exists
            if not vmid:
                node_status = client.get_node_status()
                vm_cpus, vm_memory = ResourceManager.calculate_vm_resources(
                    node_status, node["cpu_ratio"], node["memory_ratio"]
                )

                vmid = VMManager.get_next_available_vmid(client.proxmox)
                vm_name = f"k3s-vm-{node['name']}"

                print(
                    f"Creating VM {vm_name} on {node['name']} with {vm_cpus} CPUs and {vm_memory // (1024 * 1024)} MB memory."
                )
                client.proxmox.nodes(node["name"]).qemu.create(
                    vmid=vmid,
                    name=vm_name,
                    cores=vm_cpus,
                    memory=vm_memory // (1024 * 1024),  # Convert bytes to MB
                    storage=node["storage"],
                    cdrom=f"{node['storage']}:iso/{Config.ISO_NAME}",
                    net0="virtio,bridge=vmbr0",
                )
                print(f"VM {vm_name} created on {node['name']}.")
            else:
                print(f"⚠️ VM named k3s-vm-{node['name']} already exists on {node['name']}. Creation skipped.")

            GPUManager.attach_gpu_to_vm(node["name"], vmid)
