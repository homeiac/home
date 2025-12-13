#!/bin/bash
# 07-fix-ha-vm-dns.sh
# Fixes DNS configuration INSIDE the Home Assistant VM via Proxmox
# Sets OPNsense (192.168.4.1) as the DNS server for HA

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# HA VM details
HA_VM_ID="116"
PROXMOX_HOSTS=("chief-horse.maas" "pumped-piglet.maas" "still-fawn.maas" "fun-bedbug.maas")
OPNSENSE_DNS="192.168.4.1"

echo "========================================="
echo "Fixing DNS on Home Assistant VM"
echo "========================================="
echo ""

# Find which Proxmox host has the HA VM
HA_HOST=""
for host in "${PROXMOX_HOSTS[@]}"; do
    echo -n "Checking $host... "
    STATUS=$(timeout 10 ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@$host" "qm status $HA_VM_ID 2>/dev/null" 2>/dev/null || echo "")
    if echo "$STATUS" | grep -q "running"; then
        HA_HOST="$host"
        echo "FOUND (running)"
        break
    elif echo "$STATUS" | grep -q "stopped"; then
        echo "VM exists but stopped"
    else
        echo "not here"
    fi
done

if [[ -z "$HA_HOST" ]]; then
    echo ""
    echo "ERROR: Could not find running HA VM $HA_VM_ID on any Proxmox host"
    exit 1
fi

echo ""
echo "--- Current DNS Configuration ---"
ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID -- nmcli connection show" 2>/dev/null || true

echo ""
echo "--- Applying DNS Fix ---"
echo "Setting DNS to $OPNSENSE_DNS on primary interface..."

# Get the primary connection name (usually "Supervisor enp0s18" or similar)
CONN_NAME=$(ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID -- nmcli -t -f NAME connection show --active" 2>/dev/null | head -1 || echo "")

if [[ -z "$CONN_NAME" ]]; then
    echo "Could not determine active connection name"
    echo "Trying common names..."
    CONN_NAME="Supervisor enp0s18"
fi

echo "Using connection: $CONN_NAME"

# Apply the DNS fix
echo "Running: nmcli connection modify \"$CONN_NAME\" ipv4.dns \"$OPNSENSE_DNS\""
ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID -- nmcli connection modify '$CONN_NAME' ipv4.dns '$OPNSENSE_DNS'" 2>/dev/null || \
    echo "Failed to modify connection - may need manual fix"

echo "Running: nmcli connection reload"
ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID -- nmcli connection reload" 2>/dev/null || true

echo "Running: nmcli connection up \"$CONN_NAME\""
ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID -- nmcli connection up '$CONN_NAME'" 2>/dev/null || true

echo ""
echo "--- Verifying Fix ---"
echo "Testing DNS resolution for frigate.app.homelab..."
sleep 2

ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID -- getent hosts frigate.app.homelab" 2>/dev/null && \
    echo "SUCCESS: frigate.app.homelab resolves!" || \
    echo "FAILED: DNS still not resolving .homelab"

echo ""
echo "========================================="
echo "Fix Applied"
echo "========================================="
echo ""
echo "Verify with: ./06-check-ha-vm-dns.sh"
echo "Full test:   ./04-verify-frigate-app-homelab-works.sh"
