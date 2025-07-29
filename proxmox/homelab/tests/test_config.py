"""Tests for config module."""

import os
from unittest import mock

import pytest

from homelab.config import Config


def test_get_nodes_with_valid_env(mock_env):
    """Test get_nodes with valid environment variables."""
    nodes = Config.get_nodes()
    
    # Find nodes by name rather than relying on specific order/count
    node_names = [node["name"] for node in nodes]
    assert "pve" in node_names
    assert "still-fawn" in node_names
    assert "chief-horse" in node_names
    
    # Test specific node configuration
    pve_node = next(node for node in nodes if node["name"] == "pve")
    assert pve_node["storage"] == "local-zfs"
    assert pve_node["cpu_ratio"] == 0.5
    assert pve_node["memory_ratio"] == 0.5
    
    still_fawn_node = next(node for node in nodes if node["name"] == "still-fawn")
    assert still_fawn_node["cpu_ratio"] == 0.8
    assert still_fawn_node["memory_ratio"] == 0.8


def test_get_nodes_empty_env(monkeypatch):
    """Test get_nodes with no NODE_* environment variables."""
    # Clear all NODE_* variables
    for i in range(1, 10):
        monkeypatch.delenv(f"NODE_{i}", raising=False)
    
    nodes = Config.get_nodes()
    assert nodes == []


def test_get_network_ifaces_for_valid_index(mock_env):
    """Test get_network_ifaces_for with valid network interfaces."""
    # Index 0 corresponds to NETWORK_IFACES_1
    ifaces = Config.get_network_ifaces_for(0)
    assert ifaces == ["vmbr0", "vmbr25gbe"]
    
    # Index 1 corresponds to NETWORK_IFACES_2
    ifaces = Config.get_network_ifaces_for(1)
    assert ifaces == ["vmbr25gbe"]
    
    # Index 2 corresponds to NETWORK_IFACES_3
    ifaces = Config.get_network_ifaces_for(2)
    assert ifaces == ["vmbr0", "vmbr1", "vmbr2"]


def test_get_network_ifaces_for_missing_index(monkeypatch):
    """Test get_network_ifaces_for with missing network interface config."""
    monkeypatch.delenv("NETWORK_IFACES_1", raising=False)
    
    ifaces = Config.get_network_ifaces_for(0)
    assert ifaces == []


def test_get_network_ifaces_for_empty_string(monkeypatch):
    """Test get_network_ifaces_for with empty string config."""
    monkeypatch.setenv("NETWORK_IFACES_1", "")
    
    ifaces = Config.get_network_ifaces_for(0)
    assert ifaces == []


def test_get_network_ifaces_for_whitespace_handling(monkeypatch):
    """Test get_network_ifaces_for handles whitespace correctly."""
    monkeypatch.setenv("NETWORK_IFACES_1", " vmbr0 , vmbr1 , ")
    
    ifaces = Config.get_network_ifaces_for(0)
    assert ifaces == ["vmbr0", "vmbr1"]


def test_config_attributes_with_defaults(monkeypatch, temp_ssh_key):
    """Test that config attributes have correct default values."""
    # Clear environment variables to test defaults
    for var in ["ISO_NAME", "ISO_URL", "VM_NAME_TEMPLATE", "CLOUD_USER", "CLOUD_PASSWORD"]:
        monkeypatch.delenv(var, raising=False)
    
    # Reload the module to test defaults
    import importlib
    from homelab import config
    importlib.reload(config)
    
    assert config.Config.ISO_NAME == "ubuntu-24.04.2-desktop-amd64.iso"
    assert "releases.ubuntu.com" in config.Config.ISO_URL
    assert config.Config.VM_NAME_TEMPLATE == "k3s-vm-{node}"
    assert config.Config.CLOUD_USER == "ubuntu"
    assert config.Config.CLOUD_PASSWORD == "ubuntu"


def test_cloud_ip_config_formatting(monkeypatch, temp_ssh_key):
    """Test CLOUD_IP_CONFIG formatting logic."""
    # Test with 'ip=' prefix
    monkeypatch.setenv("CLOUD_IP_CONFIG", "ip=192.168.1.100/24")
    
    import importlib
    from homelab import config
    importlib.reload(config)
    
    assert config.Config.CLOUD_IP_CONFIG == "ip=192.168.1.100/24"
    
    # Test without 'ip=' prefix
    monkeypatch.setenv("CLOUD_IP_CONFIG", "dhcp")
    importlib.reload(config)
    
    assert config.Config.CLOUD_IP_CONFIG == "ip=dhcp"


def test_pve_ips_parsing(monkeypatch, temp_ssh_key):
    """Test PVE_IPS parsing from comma-separated string."""
    monkeypatch.setenv("PVE_IPS", "192.168.1.100, 192.168.1.101 ,192.168.1.102")
    
    import importlib
    from homelab import config
    importlib.reload(config)
    
    expected = ["192.168.1.100", "192.168.1.101", "192.168.1.102"]
    assert config.Config.PVE_IPS == expected


def test_pve_ips_empty_string(monkeypatch, temp_ssh_key):
    """Test PVE_IPS with empty string."""
    monkeypatch.setenv("PVE_IPS", "")
    
    import importlib
    from homelab import config
    importlib.reload(config)
    
    assert config.Config.PVE_IPS == []


def test_vm_start_timeout_parsing(monkeypatch, temp_ssh_key):
    """Test VM_START_TIMEOUT parsing as integer."""
    monkeypatch.setenv("VM_START_TIMEOUT", "300")
    
    import importlib
    from homelab import config
    importlib.reload(config)
    
    assert config.Config.VM_START_TIMEOUT == 300
    assert isinstance(config.Config.VM_START_TIMEOUT, int)


def test_get_nodes_missing_ratios(monkeypatch, temp_ssh_key):
    """Test get_nodes handles missing CPU/memory ratios gracefully."""
    # Setup NODE_1 but without CPU_RATIO_1 or MEMORY_RATIO_1
    monkeypatch.setenv("NODE_1", "test-node")
    monkeypatch.setenv("STORAGE_1", "local-zfs")
    monkeypatch.delenv("CPU_RATIO_1", raising=False)
    monkeypatch.delenv("MEMORY_RATIO_1", raising=False)
    
    nodes = Config.get_nodes()
    
    # Should return empty list when ratios are missing
    assert nodes == []