#!/bin/bash
# Check ESPHome logs from Voice PE
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ESPHOME_IMAGE="ghcr.io/esphome/esphome:2025.11.5"

cd "$SCRIPT_DIR"
docker run --rm -v "$(pwd):/config" "$ESPHOME_IMAGE" logs "/config/voice-pe-config.yaml" --device 192.168.86.245
