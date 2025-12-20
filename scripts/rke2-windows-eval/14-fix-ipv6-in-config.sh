#!/bin/bash
# Fix IPv6 address in RKE2 config - replace with IPv4
set -e

WINDOWS_VM_IP="192.168.4.201"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true
WINDOWS_PASSWORD="${WINDOWS_PASSWORD:-}"
CONTROL_PLANE_IPV4="192.168.4.202"
CONTROL_PLANE_IPV6="2600:1700:7270:933e::1ac2"

win_ssh() {
    sshpass -p "${WINDOWS_PASSWORD}" ssh -o StrictHostKeyChecking=no Administrator@${WINDOWS_VM_IP} "$@"
}

echo "=== Fixing IPv6 in RKE2 Config ==="
echo ""

echo "Stopping services..."
win_ssh "sc stop rke2 2>nul & sc stop rancher-wins 2>nul & echo stopped" || true
sleep 5

echo ""
echo "Current config:"
win_ssh "type C:\\etc\\rancher\\rke2\\config.yaml.d\\50-rancher.yaml"

echo ""
echo "Replacing IPv6 with IPv4..."
# Use PowerShell to do the replacement
win_ssh "powershell -Command \"\\\$c = Get-Content 'C:\\etc\\rancher\\rke2\\config.yaml.d\\50-rancher.yaml' -Raw; \\\$c = \\\$c -replace '\\[${CONTROL_PLANE_IPV6}\\]', '${CONTROL_PLANE_IPV4}'; Set-Content 'C:\\etc\\rancher\\rke2\\config.yaml.d\\50-rancher.yaml' -Value \\\$c -NoNewline\""

echo ""
echo "Updated config:"
win_ssh "type C:\\etc\\rancher\\rke2\\config.yaml.d\\50-rancher.yaml"

echo ""
echo "Also updating load balancer config..."
win_ssh "echo {\"ServerURL\": \"https://${CONTROL_PLANE_IPV4}:9345\", \"ServerAddresses\": []} > C:\\var\\lib\\rancher\\rke2\\agent\\etc\\rke2-agent-load-balancer.json"
win_ssh "type C:\\var\\lib\\rancher\\rke2\\agent\\etc\\rke2-agent-load-balancer.json"

echo ""
echo "Starting services..."
win_ssh "sc start rancher-wins"
sleep 3
win_ssh "sc start rke2"

echo ""
echo "=== Done. Monitor with: ==="
echo "./11-check-windows-logs.sh"
