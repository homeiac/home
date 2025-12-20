#!/bin/bash
# Flash a specific firmware file to Voice PE
set -e

ESPTOOL="/Users/10381054/Library/Python/3.9/bin/esptool.py"
FIRMWARE="${1:?Usage: $0 <firmware.bin>}"

if [[ ! -f "$FIRMWARE" ]]; then
    echo "ERROR: File not found: $FIRMWARE"
    exit 1
fi

USB_DEVICE=$(ls /dev/cu.usbmodem* 2>/dev/null | head -1)
if [[ -z "$USB_DEVICE" ]]; then
    echo "ERROR: No USB device found"
    exit 1
fi

echo "=== Flashing $FIRMWARE to $USB_DEVICE ==="
"$ESPTOOL" --chip esp32s3 --port "$USB_DEVICE" --baud 460800 write_flash 0x0 "$FIRMWARE"
echo ""
echo "=== Flash complete! Device will reboot ==="
