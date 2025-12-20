#!/bin/bash
# Fix RKE2 IPv6 issue - force IPv4 for control plane connection
set -e

WINDOWS_VM_IP="192.168.4.201"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true
WINDOWS_PASSWORD="${WINDOWS_PASSWORD:-}"
CONTROL_PLANE_IP="192.168.4.202"

win_ssh() {
    sshpass -p "${WINDOWS_PASSWORD}" ssh -o StrictHostKeyChecking=no Administrator@${WINDOWS_VM_IP} "$@"
}

echo "=== Fixing RKE2 IPv6 Issue ==="
echo ""

echo "Current load balancer config:"
win_ssh "type C:\\var\\lib\\rancher\\rke2\\agent\\etc\\rke2-agent-load-balancer.json"
echo ""

echo "Stopping rke2 service..."
win_ssh "sc stop rke2"
sleep 5

echo ""
echo "Updating load balancer config to use IPv4..."
win_ssh "powershell -Command \"@'{\\\"ServerURL\\\": \\\"https://${CONTROL_PLANE_IP}:9345\\\", \\\"ServerAddresses\\\": []}' | Out-File -FilePath 'C:\\var\\lib\\rancher\\rke2\\agent\\etc\\rke2-agent-load-balancer.json' -Encoding ascii -NoNewline\""

echo ""
echo "New load balancer config:"
win_ssh "type C:\\var\\lib\\rancher\\rke2\\agent\\etc\\rke2-agent-load-balancer.json"

echo ""
echo "Starting rke2 service..."
win_ssh "sc start rke2"
sleep 5

echo ""
echo "Service status:"
win_ssh "sc query rke2"

echo ""
echo "=== Done. Check event log in a few seconds ==="
