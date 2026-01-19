#!/bin/bash
# Check Crossplane EnvironmentVM status with clear error messages
# Usage: ./check-vm-status.sh [VM_NAME] [KUBECONFIG]
#
# Examples:
#   ./check-vm-status.sh k3s-vm-fun-bedbug
#   ./check-vm-status.sh k3s-vm-fun-bedbug ~/kubeconfig

set -e

VM_NAME="${1:-}"
KUBECONFIG_PATH="${2:-$HOME/kubeconfig}"

if [[ -z "$VM_NAME" ]]; then
    echo "Usage: $0 <VM_NAME> [KUBECONFIG]"
    echo ""
    echo "List all EnvironmentVMs:"
    KUBECONFIG="$KUBECONFIG_PATH" kubectl get environmentvms.virtualenvironmentvm.crossplane.io -A 2>/dev/null || echo "Failed to list VMs"
    exit 1
fi

export KUBECONFIG="$KUBECONFIG_PATH"

echo "=== EnvironmentVM: $VM_NAME ==="
echo ""

# Get full status via JSON - reliable even when kubectl describe fails
STATUS=$(kubectl get environmentvms.virtualenvironmentvm.crossplane.io "$VM_NAME" -o json 2>/dev/null)

if [[ -z "$STATUS" ]]; then
    echo "ERROR: VM not found: $VM_NAME"
    exit 1
fi

# Extract key info using jq
echo "Basic Info:"
echo "$STATUS" | jq -r '
"  VMID: \(.status.atProvider.vmId // "N/A")
  Node: \(.status.atProvider.nodeName // "N/A")
  Name: \(.status.atProvider.name // "N/A")
  Started: \(.status.atProvider.started // "N/A")"'

echo ""
echo "Conditions:"
echo "$STATUS" | jq -r '.status.conditions[] | "  [\(.type)] \(.status) - \(.reason)"'

echo ""
echo "Error Messages (if any):"
ERRORS=$(echo "$STATUS" | jq -r '.status.conditions[] | select(.message != null and .status == "False") | .message' 2>/dev/null)

if [[ -n "$ERRORS" && "$ERRORS" != "null" ]]; then
    echo "$ERRORS" | while read -r line; do
        echo "  [ERROR] $line"
    done
else
    echo "  [OK] No errors"
fi

echo ""
echo "Proxmox Status:"
NODE=$(echo "$STATUS" | jq -r '.status.atProvider.nodeName // "unknown"')
VMID=$(echo "$STATUS" | jq -r '.status.atProvider.vmId // "unknown"')

if [[ "$NODE" != "unknown" && "$VMID" != "unknown" ]]; then
    ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${NODE}.maas" "qm status $VMID" 2>&1 || echo "  Failed to query Proxmox"
else
    echo "  Cannot query - node or vmid unknown"
fi
