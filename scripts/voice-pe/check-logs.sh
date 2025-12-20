#!/bin/bash
# Check ESPHome logs from Voice PE
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ESPHOME_IMAGE="ghcr.io/esphome/esphome:2025.11.5"
VOICE_PE_IP="192.168.86.245"
TIMEOUT="${1:-20}"

cd "$SCRIPT_DIR"
echo "=== Voice PE Logs (${TIMEOUT}s timeout) ==="
timeout "$TIMEOUT" docker run --rm --network host -v "$(pwd):/config" "$ESPHOME_IMAGE" logs "/config/voice-pe-config.yaml" --device "$VOICE_PE_IP" 2>&1 || true
