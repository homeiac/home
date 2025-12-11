#!/bin/bash
# Frigate Coral LXC - Check Prerequisites
# GitHub Issue: #168
# Verifies required packages on Proxmox host

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Prerequisites Check ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

# Check packages on remote host
echo "1. Checking usbutils..."
if ssh root@"$PVE_HOST" "dpkg -l | grep -q usbutils"; then
    echo "   ✅ usbutils installed"
else
    echo "   ❌ usbutils NOT installed"
    echo "   Fix: ssh root@$PVE_HOST 'apt install -y usbutils'"
    exit 1
fi

echo ""
echo "2. Checking lsusb command..."
if ssh root@"$PVE_HOST" "which lsusb > /dev/null 2>&1"; then
    echo "   ✅ lsusb available"
else
    echo "   ❌ lsusb NOT available"
    exit 1
fi

echo ""
echo "3. Checking jq..."
if ssh root@"$PVE_HOST" "which jq > /dev/null 2>&1"; then
    echo "   ✅ jq available"
else
    echo "   ⚠️  jq not installed (optional, for JSON parsing)"
    echo "   Fix: ssh root@$PVE_HOST 'apt install -y jq'"
fi

echo ""
echo "4. Checking pct command..."
if ssh root@"$PVE_HOST" "which pct > /dev/null 2>&1"; then
    echo "   ✅ pct available (Proxmox container tools)"
else
    echo "   ❌ pct NOT available - is this a Proxmox host?"
    exit 1
fi

echo ""
echo "=== Prerequisites Check Complete ==="
