#!/bin/bash
# Frigate Coral LXC - Create Hookscript
# GitHub Issue: #168
# Deploys the Coral USB reset hookscript to the Proxmox host

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Create Hookscript ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

if [[ -z "$VMID" ]]; then
    echo "❌ ERROR: VMID not set in config.env"
    exit 1
fi

HOOKSCRIPT_PATH="/var/lib/vz/snippets/coral-lxc-hook-$VMID.sh"
TEMPLATE_FILE="$SCRIPT_DIR/hookscript-template.sh"

echo "Container VMID: $VMID"
echo "Hookscript path: $HOOKSCRIPT_PATH"
echo ""

echo "1. Ensuring snippets directory exists..."
ssh root@"$PVE_HOST" "mkdir -p /var/lib/vz/snippets"
echo "   ✅ Directory ready"

echo ""
echo "2. Deploying hookscript..."
scp "$TEMPLATE_FILE" root@"$PVE_HOST":"$HOOKSCRIPT_PATH"
echo "   ✅ Hookscript deployed"

echo ""
echo "3. Setting executable permissions..."
ssh root@"$PVE_HOST" "chmod +x $HOOKSCRIPT_PATH"
echo "   ✅ Permissions set"

echo ""
echo "4. Verifying deployment..."
ssh root@"$PVE_HOST" "ls -la $HOOKSCRIPT_PATH"
ssh root@"$PVE_HOST" "file $HOOKSCRIPT_PATH"

echo ""
echo "=== Hookscript Created ==="
echo ""
echo "NEXT: Run 21-attach-hookscript.sh to attach to container"
