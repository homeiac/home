#!/bin/bash
# Trigger TTS and capture CPU spike evidence
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
MESSAGE="${1:-This is a longer test message to measure CPU usage during text to speech synthesis on the slow chief horse machine}"

echo "=== TTS CPU Spike Test ==="
echo "CPU: Intel i3-4010U @ 1.70GHz (2 cores allocated to HAOS VM)"
echo ""

# Baseline
echo "1. BASELINE (before TTS):"
echo "   Load: $(ssh root@chief-horse.maas 'cat /proc/loadavg')"
echo "   HAOS VM CPU: $(ssh root@chief-horse.maas "ps -p \$(pgrep -f 'qemu.*116') -o %cpu --no-headers" 2>/dev/null || echo "N/A")%"
echo ""

# Trigger TTS
echo "2. Triggering TTS at $(date +%H:%M:%S)..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"entity_id\": \"assist_satellite.home_assistant_voice_09f5a3_assist_satellite\", \"message\": \"$MESSAGE\"}" \
    "http://$HA_HOST:8123/api/services/assist_satellite/announce" > /dev/null

echo "   TTS synthesis started..."
echo ""

# Sample CPU every second for 10 seconds
echo "3. CPU samples during TTS (HAOS VM 116):"
echo "   Time      | HAOS VM CPU% | Load Avg"
echo "   ----------|--------------|----------"
for i in {1..10}; do
    sleep 1
    VM_CPU=$(ssh -o ConnectTimeout=2 root@chief-horse.maas "ps -p \$(pgrep -f 'qemu.*116') -o %cpu --no-headers" 2>/dev/null || echo "?")
    LOAD=$(ssh -o ConnectTimeout=2 root@chief-horse.maas "cat /proc/loadavg | cut -d' ' -f1" 2>/dev/null || echo "?")
    printf "   +%2ds      | %12s | %s\n" "$i" "$VM_CPU" "$LOAD"
done

echo ""
echo "4. AFTER TTS:"
echo "   Load: $(ssh root@chief-horse.maas 'cat /proc/loadavg')"
echo "   HAOS VM CPU: $(ssh root@chief-horse.maas "ps -p \$(pgrep -f 'qemu.*116') -o %cpu --no-headers" 2>/dev/null || echo "N/A")%"
echo ""

echo "=== Evidence ==="
echo "If VM CPU spikes to 100%+ during TTS → CPU bottleneck confirmed"
echo "If VM CPU stays low → bottleneck elsewhere (network, Voice PE)"
