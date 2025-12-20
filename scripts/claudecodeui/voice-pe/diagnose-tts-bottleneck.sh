#!/bin/bash
# Diagnose TTS bottleneck - check CPU, network, disk during TTS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"

echo "=== TTS Bottleneck Diagnosis ==="
echo ""

# Check chief-horse current state
echo "1. Chief-horse baseline:"
ssh root@chief-horse.maas "echo 'Load: ' \$(cat /proc/loadavg | cut -d' ' -f1-3)"
ssh root@chief-horse.maas "echo 'HAOS VM CPU: ' \$(ps -p \$(pgrep -f 'qemu.*116' | head -1) -o %cpu --no-headers 2>/dev/null || echo N/A)%"
echo ""

# Trigger TTS in background
echo "2. Triggering TTS..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "assist_satellite.home_assistant_voice_09f5a3_assist_satellite", "message": "One two three four five"}' \
    "http://$HA_HOST:8123/api/services/assist_satellite/announce" &
CURL_PID=$!

echo "3. Sampling CPU every 2s for 20s..."
echo "   Time | Load  | HAOS VM CPU"
echo "   -----|-------|------------"
for i in {1..10}; do
    sleep 2
    LOAD=$(ssh -o ConnectTimeout=2 root@chief-horse.maas "cat /proc/loadavg | cut -d' ' -f1" 2>/dev/null || echo "?")
    VM_CPU=$(ssh -o ConnectTimeout=2 root@chief-horse.maas "ps -p \$(pgrep -f 'qemu.*116' | head -1) -o %cpu --no-headers" 2>/dev/null || echo "?")
    printf "   %3ds | %5s | %s%%\n" "$((i*2))" "$LOAD" "$VM_CPU"
done

wait $CURL_PID 2>/dev/null || true

echo ""
echo "4. Check Voice PE state:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/assist_satellite.home_assistant_voice_09f5a3_assist_satellite" | jq '{state}'
