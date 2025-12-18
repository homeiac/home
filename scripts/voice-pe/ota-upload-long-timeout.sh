#!/bin/bash
# OTA upload with very long timeout for slow WiFi (power-save issue)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ESPHOME_IMAGE="ghcr.io/esphome/esphome:2025.11.5"
VOICE_PE_IP="192.168.86.245"
TIMEOUT="${1:-900}"  # Default 15 minutes

cd "$SCRIPT_DIR"

echo "=== OTA Upload with ${TIMEOUT}s timeout ==="
echo "Device: $VOICE_PE_IP"
echo ""

docker run --rm -v "$(pwd):/config" --network host "$ESPHOME_IMAGE" \
    upload "/config/voice-pe-config.yaml" \
    --device "$VOICE_PE_IP" \
    --timeout "$TIMEOUT"
