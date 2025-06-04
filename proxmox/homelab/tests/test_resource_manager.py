import pytest

from homelab.resource_manager import ResourceManager


def test_calculate_vm_resources_standard():
    """CPU and memory should scale with provided ratios."""
    node_info = {
        "cpuinfo": {"cpus": 8},
        "memory": {"total": 8 * 1024 ** 3},
    }

    cpus, memory = ResourceManager.calculate_vm_resources(node_info, 0.5, 0.5)

    assert cpus == 4
    assert memory == 4 * 1024 ** 3


def test_calculate_vm_resources_minimums():
    """Ensure minimum CPU and memory allocations are enforced."""
    node_info = {
        "cpuinfo": {"cpus": 4},
        "memory": {"total": 4 * 1024 ** 3},
    }

    cpus, memory = ResourceManager.calculate_vm_resources(node_info, 0.0, 0.0)

    assert cpus == 1
    assert memory == 512 * 1024 ** 2
