#!/usr/bin/env python3
"""
test_orchestrator.py - Test MAAS registration and monitoring without VM provisioning.
"""

import sys
from pathlib import Path

# Add src directory to path so we can import homelab modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

from homelab.infrastructure_orchestrator import InfrastructureOrchestrator


def test_maas_and_monitoring():
    """Test MAAS registration and monitoring without VM provisioning."""
    print("🧪 Testing MAAS Registration and Monitoring")
    print("=" * 50)
    
    orchestrator = InfrastructureOrchestrator()
    
    # Mock K3s VMs data (simulating existing VMs)
    mock_k3s_vms = [
        {"name": "k3s-vm-pve", "node": "pve", "hostname": "k3s-vm-pve"},
        {"name": "k3s-vm-fun-bedbug", "node": "fun-bedbug", "hostname": "k3s-vm-fun-bedbug"},
        {"name": "k3s-vm-still-fawn", "node": "still-fawn", "hostname": "k3s-vm-still-fawn"},
        {"name": "k3s-vm-chief-horse", "node": "chief-horse", "hostname": "k3s-vm-chief-horse"}
    ]
    
    print("📝 Testing MAAS device registration for K3s VMs...")
    step2_result = orchestrator.step2_register_k3s_vms_in_maas(mock_k3s_vms)
    print(f"Step 2 Result: {step2_result}")
    print()
    
    print("🔧 Testing critical services MAAS registration...")
    step3_result = orchestrator.step3_register_critical_services_in_maas()
    print(f"Step 3 Result: {step3_result}")
    print()
    
    print("📊 Testing monitoring configuration update...")
    step4_result = orchestrator.step4_update_monitoring()
    print(f"Step 4 Result: {step4_result}")
    print()
    
    print("✅ Test complete!")
    

if __name__ == "__main__":
    test_maas_and_monitoring()