#!/bin/bash
# 06-check-ha-vm-dns.sh
# Checks DNS configuration INSIDE the Home Assistant VM via Proxmox
# This tests from HA's perspective, not from Mac

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# HA VM details
HA_VM_ID="116"
PROXMOX_HOSTS=("chief-horse.maas" "pumped-piglet.maas" "still-fawn.maas" "fun-bedbug.maas")

echo "========================================="
echo "Checking DNS from Inside Home Assistant VM"
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
    echo "Tried: ${PROXMOX_HOSTS[*]}"
    exit 1
fi

echo ""
echo "--- HA VM DNS Configuration ---"

# Check resolv.conf inside HA VM
echo "Current /etc/resolv.conf:"
ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID -- cat /etc/resolv.conf" 2>/dev/null || \
    ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID cat /etc/resolv.conf" 2>/dev/null || \
    echo "Could not read resolv.conf (guest agent may not be installed)"

echo ""
echo "--- Testing DNS Resolution from HA VM ---"

# Test if HA can resolve frigate.app.homelab
echo "Testing: nslookup frigate.app.homelab"
ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID -- nslookup frigate.app.homelab" 2>/dev/null || \
    ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID nslookup frigate.app.homelab" 2>/dev/null || \
    echo "nslookup not available or failed"

echo ""
echo "Testing: getent hosts frigate.app.homelab"
ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID -- getent hosts frigate.app.homelab" 2>/dev/null || \
    ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID getent hosts frigate.app.homelab" 2>/dev/null || \
    echo "getent failed - DNS likely not resolving .homelab"

echo ""
echo "--- Network Connections ---"
echo "nmcli connection show:"
ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID -- nmcli connection show" 2>/dev/null || \
    ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID nmcli connection show" 2>/dev/null || \
    echo "Could not get nmcli connections"

echo ""
echo "--- Testing HTTP Access to Frigate from HA VM ---"

# Find the running Frigate pod and its service IP
echo "Finding running Frigate pod..."
FRIGATE_POD=$(KUBECONFIG=~/kubeconfig kubectl get pods -n frigate --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -z "$FRIGATE_POD" ]]; then
    echo "ERROR: No running Frigate pod found"
    FRIGATE_LB_IP=""
else
    echo "Running pod: $FRIGATE_POD"

    # Get the app label from the running pod
    APP_LABEL=$(KUBECONFIG=~/kubeconfig kubectl get pod -n frigate "$FRIGATE_POD" -o jsonpath='{.metadata.labels.app}' 2>/dev/null || echo "")
    echo "App label: $APP_LABEL"

    # Find the service with matching selector
    FRIGATE_LB_IP=$(KUBECONFIG=~/kubeconfig kubectl get svc -n frigate -o json 2>/dev/null | \
        jq -r ".items[] | select(.spec.selector.app == \"$APP_LABEL\") | .status.loadBalancer.ingress[0].ip" 2>/dev/null | head -1 || echo "")
fi

if [[ -z "$FRIGATE_LB_IP" ]]; then
    echo "ERROR: Could not determine Frigate LoadBalancer IP"
else
    echo "Frigate LoadBalancer IP: $FRIGATE_LB_IP"
fi

echo ""
echo "Testing: curl http://frigate.app.homelab/api/version (via Traefik port 80)"
ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID -- curl -s --max-time 10 http://frigate.app.homelab/api/version" 2>/dev/null || \
    echo "curl to frigate.app.homelab FAILED"

echo ""
echo "Testing: curl http://$FRIGATE_LB_IP:5000/api/version (Frigate direct LB IP)"
ssh "root@$HA_HOST" "qm guest exec $HA_VM_ID -- curl -s --max-time 10 http://$FRIGATE_LB_IP:5000/api/version" 2>/dev/null || \
    echo "curl to Frigate direct IP failed"

echo ""
echo "========================================="
echo "If hostname curl failed but direct IP worked:"
echo "  -> DNS resolution is broken, run: ./07-fix-ha-vm-dns.sh"
echo "If both worked:"
echo "  -> DNS is fine, update Frigate integration URL in HA"
echo "========================================="
