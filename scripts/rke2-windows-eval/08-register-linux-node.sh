#!/bin/bash
# Register Linux control plane node to RKE2 cluster via Rancher
# IMPORTANT: This script sets node-ip to force IPv4 registration
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    source "${SCRIPT_DIR}/.env"
fi

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
LINUX_VM_IP="${LINUX_VM_IP:-192.168.4.202}"

# Registration token - UPDATE THESE when recreating cluster
RANCHER_TOKEN="${RANCHER_TOKEN:-UPDATE_ME}"
RANCHER_CA_CHECKSUM="${RANCHER_CA_CHECKSUM:-UPDATE_ME}"

if [[ "$RANCHER_TOKEN" == "UPDATE_ME" ]]; then
    echo "ERROR: RANCHER_TOKEN not set in .env"
    echo "Get the token from Rancher UI cluster registration command"
    exit 1
fi

echo "=== Registering Linux Control Plane Node ==="
echo ""
echo "Node IP: ${LINUX_VM_IP} (will be advertised to Rancher)"
echo ""

# Check SSH connectivity
if ! ssh root@${PROXMOX_HOST} "ssh -o StrictHostKeyChecking=no ubuntu@${LINUX_VM_IP} uptime" 2>/dev/null; then
    echo "ERROR: Cannot SSH to ubuntu@${LINUX_VM_IP} via ${PROXMOX_HOST}"
    exit 1
fi

# Verify IPv6 is disabled
echo "Verifying IPv6 is disabled..."
IPV6_CHECK=$(ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} 'ip addr show | grep inet6 | grep -v \"::1\" | wc -l'" 2>/dev/null)
if [[ "$IPV6_CHECK" != "0" ]]; then
    echo "WARNING: IPv6 addresses found on node. Disabling now..."
    ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} 'sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1; sudo sysctl -w net.ipv6.conf.default.disable_ipv6=1'"
fi

# Pre-create RKE2 config directory with node-ip setting
# This ensures RKE2 uses IPv4 when it starts
echo "Pre-configuring RKE2 to use IPv4 node-ip..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} '
    sudo mkdir -p /etc/rancher/rke2
    echo \"node-ip: ${LINUX_VM_IP}\" | sudo tee /etc/rancher/rke2/config.yaml
'"

echo ""
echo "Running registration command on VM 202..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} 'curl --insecure -fL https://rancher.homelab/system-agent-install.sh | sudo sh -s - --server https://rancher.homelab --label cattle.io/os=linux --token ${RANCHER_TOKEN} --ca-checksum ${RANCHER_CA_CHECKSUM} --etcd --controlplane --worker'"

echo ""
echo "=== Registration Complete ==="
echo "Check Rancher UI for node status"
echo ""
echo "Verify node-ip with:"
echo "  ssh root@${PROXMOX_HOST} \"ssh ubuntu@${LINUX_VM_IP} 'sudo cat /etc/rancher/rke2/config.yaml'\""
