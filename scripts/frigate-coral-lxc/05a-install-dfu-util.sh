#!/bin/bash
# Frigate Coral LXC - Install dfu-util
# GitHub Issue: #168
# Reference: docs/source/md/coral-tpu-automation-runbook.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Install dfu-util ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

echo "1. Checking if dfu-util is already installed..."
if ssh root@"$PVE_HOST" "which dfu-util" 2>/dev/null; then
    echo "   ✅ dfu-util already installed"
    ssh root@"$PVE_HOST" "dfu-util --version" | head -1
else
    echo "   Installing dfu-util..."
    ssh root@"$PVE_HOST" "apt update && apt install -y dfu-util"
    echo "   ✅ dfu-util installed"
fi

echo ""
echo "2. Verifying installation..."
ssh root@"$PVE_HOST" "dfu-util --version" | head -1

echo ""
echo "=== dfu-util Installation Complete ==="
echo ""
echo "NEXT: Run 05b-download-firmware.sh"
