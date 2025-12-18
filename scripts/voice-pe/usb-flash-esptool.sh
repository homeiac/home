#!/bin/bash
# Flash Voice PE via USB using esptool (bypasses Docker USB issues on Mac)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ESPTOOL="/Users/10381054/Library/Python/3.9/bin/esptool.py"
FIRMWARE="$SCRIPT_DIR/.esphome/build/home-assistant-voice-09f5a3/.pioenvs/home-assistant-voice-09f5a3/firmware.factory.bin"

echo "=== USB Flash with esptool ==="
echo ""

# Check esptool
if [[ ! -f "$ESPTOOL" ]]; then
    echo "Installing esptool..."
    pip3 install esptool
    ESPTOOL=$(which esptool.py)
fi

# Find USB device
USB_DEVICE=$(ls /dev/cu.usbmodem* 2>/dev/null | head -1)
if [[ -z "$USB_DEVICE" ]]; then
    echo "ERROR: No USB device found. Connect USB-C cable to Voice PE."
    exit 1
fi
echo "USB Device: $USB_DEVICE"

# Check firmware exists
if [[ ! -f "$FIRMWARE" ]]; then
    echo "ERROR: Firmware not found at $FIRMWARE"
    echo ""
    echo "Run docker-compile.sh first to build the firmware."
    exit 1
fi
echo "Firmware: $FIRMWARE ($(du -h "$FIRMWARE" | cut -f1))"
echo ""

# Flash
echo "Flashing..."
$ESPTOOL --chip esp32s3 --port "$USB_DEVICE" --baud 460800 \
    write_flash 0x0 "$FIRMWARE"

echo ""
echo "=== Flash complete! Device will reboot ==="
