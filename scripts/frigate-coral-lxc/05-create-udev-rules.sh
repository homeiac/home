#!/bin/bash
# Frigate Coral LXC - Create Udev Rules
# GitHub Issue: #168
# Creates /etc/udev/rules.d/98-coral.rules

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Create Udev Rules ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

RULES_FILE="/etc/udev/rules.d/98-coral.rules"
RULES_CONTENT='SUBSYSTEMS=="usb", ATTRS{idVendor}=="1a6e", ATTRS{idProduct}=="089a", MODE="0666", GROUP="plugdev"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="18d1", ATTRS{idProduct}=="9302", MODE="0666", GROUP="plugdev"'

echo "1. Creating udev rules file..."
ssh root@"$PVE_HOST" "cat > $RULES_FILE << 'EOF'
$RULES_CONTENT
EOF"

echo "   ✅ Created $RULES_FILE"

echo ""
echo "2. Verifying file contents..."
ssh root@"$PVE_HOST" "cat $RULES_FILE"

echo ""
echo "=== Udev Rules Created ==="
echo ""
echo "NEXT: Run 06-reload-udev.sh to apply rules"
