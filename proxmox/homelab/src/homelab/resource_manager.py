import math


class ResourceManager:
    """Handles resource allocation for VMs."""

    @staticmethod
    def calculate_vm_resources(node_info, cpu_ratio, mem_ratio):
        """Dynamically allocate VM resources based on host availability."""
        total_cpus = node_info["cpuinfo"]["cpus"]
        total_memory = node_info["memory"]["total"]

        vm_cpus = max(1, math.floor(total_cpus * cpu_ratio))
        vm_memory = max(
            512 * 1024 * 1024, math.floor(total_memory * mem_ratio)
        )  # Minimum 512MB

        return vm_cpus, vm_memory
