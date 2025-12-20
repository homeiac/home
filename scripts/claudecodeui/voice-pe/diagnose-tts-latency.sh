#!/bin/bash
# Diagnose TTS latency on Voice PE
# Checks chief-horse CPU (Proxmox host running HAOS VM 116)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    MQTT_USER=$(grep "^MQTT_USER=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
    MQTT_PASS=$(grep "^MQTT_PASS=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
MQTT_HOST="${MQTT_HOST:-homeassistant.maas}"
MQTT_AUTH=""
[[ -n "$MQTT_USER" ]] && MQTT_AUTH="-u $MQTT_USER -P $MQTT_PASS"

echo "=== TTS Latency Diagnosis ==="
echo ""

# 1. Check chief-horse CPU info
echo "1. Chief-horse (Proxmox host) CPU info:"
ssh root@chief-horse.maas "cat /proc/cpuinfo | grep 'model name' | head -1"
ssh root@chief-horse.maas "nproc"
echo ""

# 2. Check HAOS VM config
echo "2. HAOS VM (116) resource allocation:"
ssh root@chief-horse.maas "qm config 116 | grep -E '^(cores|memory|cpu)'"
echo ""

# 3. Current CPU load on chief-horse
echo "3. Current CPU load on chief-horse:"
ssh root@chief-horse.maas "uptime"
echo ""

# 4. Check if Wyoming/Piper is running
echo "4. Checking for Piper/Wyoming processes in HAOS:"
# Use API to check addons
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/hassio/addons" 2>/dev/null | \
    jq -r '.data.addons[] | select(.name | test("piper|wyoming|whisper"; "i")) | "\(.name): \(.state)"' || echo "Could not query addons"
echo ""

# 5. Test TTS with timing
echo "5. Running TTS test with timing..."
echo "   Starting CPU monitor on chief-horse..."

# Start CPU monitoring in background
ssh root@chief-horse.maas "vmstat 1 10" > /tmp/cpu_during_tts.txt 2>&1 &
CPU_PID=$!

sleep 1

# Record start time
START=$(date +%s.%N)

# Trigger TTS via announce
echo "   Triggering TTS announce..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "entity_id": "assist_satellite.home_assistant_voice_09f5a3_assist_satellite",
        "message": "Testing TTS latency measurement"
    }' \
    "http://$HA_HOST:8123/api/services/assist_satellite/announce" > /dev/null

# Wait for it to complete (approximate)
sleep 8

END=$(date +%s.%N)
DURATION=$(echo "$END - $START" | bc)

echo "   TTS API call + speech took approximately: ${DURATION}s"
echo ""

# Wait for CPU monitoring to finish
wait $CPU_PID 2>/dev/null || true

echo "6. CPU during TTS (vmstat output):"
cat /tmp/cpu_during_tts.txt | tail -12
echo ""

# 7. Check HA logs for TTS timing
echo "7. Recent TTS-related logs (last 30 seconds):"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/error_log" 2>/dev/null | \
    grep -iE "piper|tts|wyoming|assist" | tail -10 || echo "No TTS logs found in error log"
echo ""

# 8. Check Voice PE satellite state
echo "8. Voice PE satellite current state:"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "http://$HA_HOST:8123/api/states/assist_satellite.home_assistant_voice_09f5a3_assist_satellite" | \
    jq '{state, last_changed}'
echo ""

echo "=== Summary ==="
echo "If CPU shows high usage (low idle) during TTS, chief-horse CPU is likely the bottleneck."
echo "Piper TTS is CPU-intensive, especially on older/slower CPUs."
echo ""
echo "Potential fixes:"
echo "  1. Allocate more cores to HAOS VM 116"
echo "  2. Move TTS to a faster machine (cloud or dedicated)"
echo "  3. Use lighter TTS model in Piper"
echo "  4. Use cloud TTS (Google, Amazon)"
