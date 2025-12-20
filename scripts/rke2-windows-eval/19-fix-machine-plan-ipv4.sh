#!/bin/bash
# Fix IPv6 to IPv4 in Windows machine plan secret
set -e

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
RANCHER_VM_IP="${RANCHER_VM_IP:-192.168.4.200}"
WINDOWS_SECRET_NAME="custom-1d789e8a6c45-machine-plan"

echo "=== Fixing Machine Plan Secret ==="
echo ""

# Get the Windows machine plan
echo "Fetching Windows machine plan: ${WINDOWS_SECRET_NAME}"
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get secret/${WINDOWS_SECRET_NAME} -n fleet-default -o json'" > /tmp/machine-plan.json

# Show current server URL
echo ""
echo "Current config (before fix):"
PLAN_B64=$(jq -r '.data.plan' /tmp/machine-plan.json)
echo "$PLAN_B64" | base64 -d | jq -r '.files[] | select(.path | contains("50-rancher")) | .content' | base64 -d | grep server

# Fix IPv6 in the full plan JSON structure
echo ""
echo "Fixing IPv6 addresses..."
PLAN_JSON=$(echo "$PLAN_B64" | base64 -d)
FIXED_PLAN=$(echo "$PLAN_JSON" | sed 's/\[2600:1700:7270:933e::1ac2\]/192.168.4.202/g')

# Re-encode
FIXED_PLAN_B64=$(echo "$FIXED_PLAN" | base64 | tr -d '\n')

# Create patch JSON file
cat > /tmp/plan-patch.json << EOF
{"data":{"plan":"${FIXED_PLAN_B64}"}}
EOF

# Upload and apply patch
echo "Uploading patch..."
scp /tmp/plan-patch.json root@${PROXMOX_HOST}:/tmp/plan-patch.json
ssh root@${PROXMOX_HOST} "scp /tmp/plan-patch.json ubuntu@${RANCHER_VM_IP}:/tmp/plan-patch.json"

echo "Applying patch..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml patch secret/${WINDOWS_SECRET_NAME} -n fleet-default --type=merge --patch-file=/tmp/plan-patch.json'"

# Verify
echo ""
echo "Verifying fix..."
ssh root@${PROXMOX_HOST} "ssh ubuntu@${RANCHER_VM_IP} 'sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get secret/${WINDOWS_SECRET_NAME} -n fleet-default -o jsonpath={.data.plan}'" | base64 -d | jq -r '.files[] | select(.path | contains("50-rancher")) | .content' | base64 -d | grep server

echo ""
echo "=== Done ==="
echo "Now restart the Windows node rancher-wins service to pick up the new config"
