#!/bin/bash
# Compile ESPHome firmware using Docker (same image as HAOS)
# Much faster than HAOS VM - uses all Mac cores
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ESPHOME_IMAGE="ghcr.io/esphome/esphome:2025.12.4"
VOICE_PE_IP="192.168.86.10"
CONFIG_FILE="${1:-voice-pe-config.yaml}"

cd "$SCRIPT_DIR"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: $CONFIG_FILE not found in $SCRIPT_DIR"
    exit 1
fi

if [[ ! -f "secrets.yaml" ]]; then
    echo "ERROR: secrets.yaml not found in $SCRIPT_DIR"
    exit 1
fi

# Decrypt SOPS-encrypted secrets.yaml for Docker
# Docker can't access the age key, so we decrypt to a temp file
SOPS_KEY="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"
if head -1 secrets.yaml | grep -q "ENC\[AES256"; then
    if [[ ! -f "$SOPS_KEY" ]]; then
        echo "ERROR: secrets.yaml is SOPS-encrypted but age key not found at $SOPS_KEY"
        exit 1
    fi
    echo "Decrypting secrets.yaml..."
    SOPS_AGE_KEY_FILE="$SOPS_KEY" sops -d secrets.yaml > secrets.decrypted.yaml
    SECRETS_DECRYPTED=true
    # Swap in decrypted secrets for compilation
    mv secrets.yaml secrets.yaml.enc
    mv secrets.decrypted.yaml secrets.yaml
    trap 'mv -f "$SCRIPT_DIR/secrets.yaml.enc" "$SCRIPT_DIR/secrets.yaml" 2>/dev/null; rm -f "$SCRIPT_DIR/secrets.decrypted.yaml" 2>/dev/null' EXIT
else
    SECRETS_DECRYPTED=false
fi

ACTION="${2:-compile}"

# Test docker is working first
echo "Testing docker..."
if ! timeout 10 docker info >/dev/null 2>&1; then
    echo "ERROR: Docker not responding. Is Docker Desktop running?"
    exit 1
fi
echo "Docker OK"

run_docker() {
    echo "Running: docker run --rm -v $SCRIPT_DIR:/config $ESPHOME_IMAGE $*"
    docker run --rm -v "$SCRIPT_DIR:/config" "$ESPHOME_IMAGE" "$@"
    local rc=$?
    if [[ $rc -ne 0 ]]; then
        echo "ERROR: Docker command failed with exit code $rc"
        exit 1
    fi
}

case "$ACTION" in
    compile)
        echo "=== Compiling with Docker ($ESPHOME_IMAGE) ==="
        time run_docker compile "/config/$CONFIG_FILE"
        ;;
    upload)
        echo "=== USB upload ==="
        "$SCRIPT_DIR/usb-flash-esptool.sh"
        ;;
    run)
        echo "=== Compile + USB Upload ==="
        time run_docker compile "/config/$CONFIG_FILE"
        echo ""
        echo "=== USB uploading ==="
        "$SCRIPT_DIR/usb-flash-esptool.sh"
        ;;
    logs)
        echo "=== Streaming logs from $VOICE_PE_IP ==="
        docker run --rm -it -v "$SCRIPT_DIR:/config" --network host "$ESPHOME_IMAGE" logs "/config/$CONFIG_FILE" --device "$VOICE_PE_IP"
        ;;
    *)
        echo "Usage: $0 [config.yaml] [compile|upload|run|logs]"
        echo ""
        echo "  compile - Compile firmware (default)"
        echo "  upload  - USB flash to device"
        echo "  run     - Compile + USB upload"
        echo "  logs    - Stream device logs"
        ;;
esac
