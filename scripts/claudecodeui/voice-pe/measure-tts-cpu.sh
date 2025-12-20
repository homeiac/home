#!/bin/bash
# Measure CPU usage during TTS to prove CPU bottleneck
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

HA_HOST="${HA_HOST:-homeassistant.maas}"
MESSAGE="${1:-Testing CPU usage during text to speech synthesis}"

echo "=== TTS CPU Measurement ==="
echo "Host: chief-horse.maas (Intel i3-4010U @ 1.70GHz)"
echo "Message: $MESSAGE"
echo ""

# Get baseline CPU
echo "1. Baseline CPU (before TTS):"
ssh root@chief-horse.maas "grep 'cpu ' /proc/stat" > /tmp/cpu_before.txt
cat /tmp/cpu_before.txt
IDLE_BEFORE=$(ssh root@chief-horse.maas "awk '/^cpu / {print \$5}' /proc/stat")
echo "   Idle ticks: $IDLE_BEFORE"
echo ""

# Start vmstat in background on chief-horse
echo "2. Starting CPU monitor..."
ssh root@chief-horse.maas "vmstat 1 15" > /tmp/vmstat_tts.txt 2>&1 &
VMSTAT_PID=$!

sleep 1

# Trigger TTS
echo "3. Triggering TTS at $(date +%H:%M:%S)..."
START_TIME=$(date +%s.%N)

curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"entity_id\": \"assist_satellite.home_assistant_voice_09f5a3_assist_satellite\",
        \"message\": \"$MESSAGE\"
    }" \
    "http://$HA_HOST:8123/api/services/assist_satellite/announce" > /dev/null

echo "   API call returned at $(date +%H:%M:%S)"
echo "   (TTS is now synthesizing and playing...)"
echo ""

# Wait for TTS to complete (estimate based on message length)
# Rough estimate: 1 second per 10 characters at slow speed
MSG_LEN=${#MESSAGE}
WAIT_TIME=$(( (MSG_LEN / 10) + 5 ))
echo "4. Waiting ${WAIT_TIME}s for TTS to complete..."
sleep $WAIT_TIME

END_TIME=$(date +%s.%N)
DURATION=$(echo "$END_TIME - $START_TIME" | bc)

# Kill vmstat
kill $VMSTAT_PID 2>/dev/null || true
wait $VMSTAT_PID 2>/dev/null || true

# Get after CPU
echo ""
echo "5. CPU after TTS:"
ssh root@chief-horse.maas "grep 'cpu ' /proc/stat" > /tmp/cpu_after.txt
cat /tmp/cpu_after.txt
IDLE_AFTER=$(ssh root@chief-horse.maas "awk '/^cpu / {print \$5}' /proc/stat")
echo "   Idle ticks: $IDLE_AFTER"
echo ""

# Calculate CPU usage
IDLE_DIFF=$((IDLE_AFTER - IDLE_BEFORE))
echo "6. Analysis:"
echo "   Total time: ${DURATION}s"
echo "   Idle ticks consumed: $IDLE_DIFF"
echo ""

# Show vmstat output (CPU columns: us=user, sy=system, id=idle, wa=wait)
echo "7. CPU usage timeline (vmstat - look at 'id' column for idle %):"
echo "   procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----"
echo "    r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st"
cat /tmp/vmstat_tts.txt | tail -15
echo ""

echo "=== Interpretation ==="
echo "If 'id' (idle) drops to <20% during TTS, CPU is the bottleneck."
echo "Look for spikes in 'us' (user) during synthesis."
