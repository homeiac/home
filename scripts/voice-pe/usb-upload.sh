#!/bin/bash
# USB upload to Voice PE (bypasses WiFi entirely)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ESPHOME_IMAGE="ghcr.io/esphome/esphome:2025.11.5"

cd "$SCRIPT_DIR"

echo "=== USB Upload to Voice PE ==="
echo ""
echo "1. Connect USB-C cable from Mac to Voice PE"
echo "2. Check for serial port:"
ls -la /dev/cu.usb* /dev/tty.usb* 2>/dev/null || echo "   No USB serial devices found yet"
echo ""

if [[ -n "$1" ]]; then
    DEVICE="$1"
    echo "Using device: $DEVICE"
    docker run --rm -v "$(pwd):/config" --device="$DEVICE" "$ESPHOME_IMAGE" \
        upload "/config/voice-pe-config.yaml" --device "$DEVICE"
else
    echo "Usage: $0 /dev/cu.usbserial-XXXX"
    echo ""
    echo "After connecting USB, find the port with:"
    echo "  ls /dev/cu.usb*"
fi
