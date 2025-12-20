#!/bin/bash
# Disable IPv6 on Linux control plane and update Rancher
set -e

# Source credentials if available
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    source "${SCRIPT_DIR}/.env"
fi

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
LINUX_VM_IP="${LINUX_VM_IP:-192.168.4.202}"

echo "=== Disabling IPv6 on Linux Control Plane ==="
echo ""

# Disable IPv6 on eth0
echo "Disabling IPv6 on Linux control plane..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} 'sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1 && sudo sysctl -w net.ipv6.conf.default.disable_ipv6=1 && sudo sysctl -w net.ipv6.conf.eth0.disable_ipv6=1'"

echo ""
echo "Persisting IPv6 disable..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} 'echo \"net.ipv6.conf.all.disable_ipv6 = 1\" | sudo tee -a /etc/sysctl.conf; echo \"net.ipv6.conf.default.disable_ipv6 = 1\" | sudo tee -a /etc/sysctl.conf'"

echo ""
echo "Current IP addresses:"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} 'ip addr show eth0 | grep inet'"

echo ""
echo "Restarting RKE2 on control plane..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} 'sudo systemctl restart rke2-agent || sudo systemctl restart rke2-server'"

echo ""
echo "=== Done ==="
echo "The Linux control plane is now IPv4-only."
echo "You may need to delete and re-register the Windows node:"
echo "1. Delete the Windows machine from Rancher UI"
echo "2. Re-run ./09-register-windows-node.sh"
