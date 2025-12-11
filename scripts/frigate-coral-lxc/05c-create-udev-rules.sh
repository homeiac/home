#!/bin/bash
# Frigate Coral LXC - Create Udev Rules with Firmware Loading
# GitHub Issue: #168
# Reference: docs/source/md/coral-tpu-automation-runbook.md
#
# This creates udev rules that:
# 1. Set correct permissions for Coral USB (0666)
# 2. Auto-load firmware via dfu-util when Coral detected in bootloader mode (1a6e:089a)
# 3. Coral then re-enumerates as 18d1:9302 (Google Inc - ready to use)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

RULES_FILE="/etc/udev/rules.d/95-coral-init.rules"
FIRMWARE_PATH="/usr/local/lib/firmware/apex_latest_single_ep.bin"

echo "=== Frigate Coral LXC - Create Udev Rules ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

echo "1. Verifying prerequisites..."
if ! ssh root@"$PVE_HOST" "which dfu-util" >/dev/null 2>&1; then
    echo "   ❌ dfu-util not installed. Run 05a-install-dfu-util.sh first"
    exit 1
fi
echo "   ✅ dfu-util installed"

if ! ssh root@"$PVE_HOST" "test -f $FIRMWARE_PATH" 2>/dev/null; then
    echo "   ❌ Firmware not found at $FIRMWARE_PATH. Run 05b-download-firmware.sh first"
    exit 1
fi
echo "   ✅ Firmware exists"

echo ""
echo "2. Creating udev rules file..."

# Remove old incomplete rules if they exist
ssh root@"$PVE_HOST" "rm -f /etc/udev/rules.d/98-coral.rules 2>/dev/null || true"

ssh root@"$PVE_HOST" "cat > $RULES_FILE << 'EOF'
# Coral USB TPU udev rules
# Reference: docs/source/md/coral-tpu-automation-runbook.md
#
# Auto-initialize Coral when detected in bootloader mode (1a6e:089a)
# dfu-util loads firmware, device re-enumerates as 18d1:9302 (Google Inc)
ACTION==\"add\", SUBSYSTEM==\"usb\", ATTR{idVendor}==\"1a6e\", ATTR{idProduct}==\"089a\", RUN+=\"/usr/bin/dfu-util -D /usr/local/lib/firmware/apex_latest_single_ep.bin -d 1a6e:089a -R\"

# Permissions for both states (bootloader and initialized)
SUBSYSTEMS==\"usb\", ATTRS{idVendor}==\"1a6e\", ATTRS{idProduct}==\"089a\", MODE=\"0666\", GROUP=\"plugdev\"
SUBSYSTEMS==\"usb\", ATTRS{idVendor}==\"18d1\", ATTRS{idProduct}==\"9302\", MODE=\"0666\", GROUP=\"plugdev\"
EOF"

echo "   ✅ Created $RULES_FILE"

echo ""
echo "3. Verifying file contents..."
ssh root@"$PVE_HOST" "cat $RULES_FILE"

echo ""
echo "=== Udev Rules Created ==="
echo ""
echo "NEXT: Run 06-reload-udev.sh to apply rules and initialize Coral"
