#!/bin/bash
# Compile ESPHome firmware using Docker (same image as HAOS)
# Much faster than HAOS VM - uses all Mac cores
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ESPHOME_IMAGE="ghcr.io/esphome/esphome:2025.11.5"
VOICE_PE_IP="192.168.86.245"
CONFIG_FILE="${1:-voice-pe-config.yaml}"

cd "$SCRIPT_DIR"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: $CONFIG_FILE not found"
    exit 1
fi

if [[ ! -f "secrets.yaml" ]]; then
    echo "ERROR: secrets.yaml not found"
    exit 1
fi

ACTION="${2:-compile}"

case "$ACTION" in
    compile)
        echo "=== Compiling with Docker ($ESPHOME_IMAGE) ==="
        time docker run --rm -v "$(pwd):/config" "$ESPHOME_IMAGE" compile "/config/$CONFIG_FILE"
        ;;
    upload)
        echo "=== OTA upload to $VOICE_PE_IP ==="
        docker run --rm -v "$(pwd):/config" --network host "$ESPHOME_IMAGE" upload "/config/$CONFIG_FILE" --device "$VOICE_PE_IP"
        ;;
    run)
        echo "=== Compile + Upload ==="
        time docker run --rm -v "$(pwd):/config" "$ESPHOME_IMAGE" compile "/config/$CONFIG_FILE"
        echo ""
        echo "=== Uploading to $VOICE_PE_IP ==="
        docker run --rm -v "$(pwd):/config" --network host "$ESPHOME_IMAGE" upload "/config/$CONFIG_FILE" --device "$VOICE_PE_IP"
        ;;
    logs)
        echo "=== Streaming logs from $VOICE_PE_IP ==="
        docker run --rm -it -v "$(pwd):/config" --network host "$ESPHOME_IMAGE" logs "/config/$CONFIG_FILE" --device "$VOICE_PE_IP"
        ;;
    *)
        echo "Usage: $0 [config.yaml] [compile|upload|run|logs]"
        echo ""
        echo "  compile - Compile firmware (default)"
        echo "  upload  - OTA flash to device"
        echo "  run     - Compile + upload"
        echo "  logs    - Stream device logs"
        ;;
esac
