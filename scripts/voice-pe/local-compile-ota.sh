#!/bin/bash
# Compile ESPHome firmware locally on Mac and OTA flash to Voice PE
# Much faster than compiling on HAOS (2-core VM)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ESPHOME_BIN="/Users/10381054/Library/Python/3.9/bin/esphome"
VOICE_PE_IP="192.168.86.245"
LOCAL_YAML="$SCRIPT_DIR/voice-pe-config.yaml"

# Check if we have the YAML
if [[ ! -f "$LOCAL_YAML" ]]; then
    echo "ERROR: $LOCAL_YAML not found"
    echo ""
    echo "To get the YAML from HAOS:"
    echo "  $SCRIPT_DIR/fetch-esphome-yaml.sh"
    exit 1
fi

ACTION="${1:-run}"

case "$ACTION" in
    compile)
        echo "=== Compiling ESPHome firmware locally ==="
        time $ESPHOME_BIN compile "$LOCAL_YAML"
        echo ""
        echo "Firmware compiled. To flash OTA:"
        echo "  $0 upload"
        ;;
    upload)
        echo "=== OTA flashing to Voice PE ($VOICE_PE_IP) ==="
        $ESPHOME_BIN upload "$LOCAL_YAML" --device "$VOICE_PE_IP"
        ;;
    run)
        echo "=== Compile + OTA flash to Voice PE ==="
        echo "Compiling..."
        time $ESPHOME_BIN compile "$LOCAL_YAML"
        echo ""
        echo "Flashing OTA to $VOICE_PE_IP..."
        $ESPHOME_BIN upload "$LOCAL_YAML" --device "$VOICE_PE_IP"
        ;;
    logs)
        echo "=== Streaming logs from Voice PE ==="
        $ESPHOME_BIN logs "$LOCAL_YAML" --device "$VOICE_PE_IP"
        ;;
    *)
        echo "Usage: $0 [compile|upload|run|logs]"
        echo ""
        echo "  compile - Compile firmware locally (fast)"
        echo "  upload  - OTA flash to device"
        echo "  run     - Compile + upload (default)"
        echo "  logs    - Stream device logs"
        exit 1
        ;;
esac
