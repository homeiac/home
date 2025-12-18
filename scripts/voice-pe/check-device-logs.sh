#!/bin/bash
# Check Voice PE ESPHome logs and HA connection status
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

echo "=== Voice PE Status ==="
echo ""

echo "1. HA Entity State:"
curl -s --max-time 10 -H "Authorization: Bearer $HA_TOKEN" \
    "http://192.168.1.122:8123/api/states/assist_satellite.home_assistant_voice_09f5a3_assist_satellite" 2>/dev/null | jq '{state, last_changed, last_updated}'

echo ""
echo "2. ESPHome API connection (port 6053):"
nc -zv 192.168.86.245 6053 2>&1 | head -3

echo ""
echo "3. Streaming ESPHome logs (10 seconds)..."
cd "$SCRIPT_DIR"
timeout 10 docker run --rm -v "$(pwd):/config" --network host ghcr.io/esphome/esphome:2025.11.5 logs "/config/voice-pe-config.yaml" --device 192.168.86.245 2>&1 | tail -30 || true
