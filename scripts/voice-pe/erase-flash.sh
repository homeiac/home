#!/bin/bash
# Erase Voice PE flash completely
set -e

ESPTOOL="/Users/10381054/Library/Python/3.9/bin/esptool.py"

USB_DEVICE=$(ls /dev/cu.usbmodem* 2>/dev/null | head -1)
if [[ -z "$USB_DEVICE" ]]; then
    echo "ERROR: No USB device found"
    exit 1
fi

echo "=== Erasing flash on $USB_DEVICE ==="
"$ESPTOOL" --chip esp32s3 --port "$USB_DEVICE" erase_flash
