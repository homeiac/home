#!/bin/bash
# Trace packets during Voice PE TTS to identify latency source
# This script captures network traffic while triggering a TTS announcement
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

if [[ -z "$HA_TOKEN" ]]; then
    echo "ERROR: HA_TOKEN not found in $ENV_FILE"
    exit 1
fi

MESSAGE="${1:-Test message one two three}"
CAPTURE_DURATION="${2:-30}"

echo "=== Voice PE TTS Packet Trace ==="
echo "Message: $MESSAGE"
echo "Capture duration: ${CAPTURE_DURATION}s"
echo ""

# Check if we can reach chief-horse
if ! ssh -o ConnectTimeout=5 root@chief-horse.maas "true" 2>/dev/null; then
    echo "ERROR: Cannot SSH to chief-horse.maas"
    exit 1
fi

echo "1. Starting packet capture on chief-horse vmbr2..."
ssh root@chief-horse.maas "timeout $CAPTURE_DURATION tcpdump -i vmbr2 host 192.168.86.245 -n -tttt 2>&1" > /tmp/voice-pe-packets.txt &
CAPTURE_PID=$!

sleep 2

echo "2. Recording start time..."
START_TIME=$(date +%s.%N)
echo "   Start: $(date)"

echo "3. Triggering TTS announce..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"entity_id\": \"assist_satellite.home_assistant_voice_09f5a3_assist_satellite\", \"message\": \"$MESSAGE\"}" \
    "http://192.168.1.122:8123/api/services/assist_satellite/announce" > /dev/null

echo "4. Waiting for TTS to complete (listen for audio)..."
echo "   Press Ctrl+C when audio finishes playing"
echo ""

# Wait for capture to finish or user interrupt
wait $CAPTURE_PID 2>/dev/null || true

END_TIME=$(date +%s.%N)
DURATION=$(echo "$END_TIME - $START_TIME" | bc)

echo ""
echo "5. Capture complete after ${DURATION}s"
echo ""

echo "=== Packet Analysis ==="
echo ""

# Count packets
TOTAL_PACKETS=$(wc -l < /tmp/voice-pe-packets.txt)
echo "Total packets captured: $TOTAL_PACKETS"
echo ""

# Show first and last few packets
echo "First 10 packets:"
head -10 /tmp/voice-pe-packets.txt
echo ""

echo "Last 10 packets:"
tail -10 /tmp/voice-pe-packets.txt
echo ""

# Analyze packet timing
echo "=== Timing Analysis ==="
echo "Looking for gaps > 100ms between packets..."
awk '
BEGIN { prev_ts = 0 }
{
    # Extract timestamp (format: 2025-12-15 HH:MM:SS.microseconds)
    split($2, time_parts, ":")
    split(time_parts[3], sec_parts, ".")
    ts = time_parts[1] * 3600 + time_parts[2] * 60 + sec_parts[1] + sec_parts[2] / 1000000

    if (prev_ts > 0) {
        gap = ts - prev_ts
        if (gap > 0.1) {  # > 100ms
            printf "  GAP: %.3fs between packets at %s\n", gap, $2
        }
    }
    prev_ts = ts
}
' /tmp/voice-pe-packets.txt

echo ""
echo "Full capture saved to: /tmp/voice-pe-packets.txt"
echo ""
echo "=== Key Questions to Answer ==="
echo "1. Are there long gaps between packets? (indicates sender throttling)"
echo "2. Is traffic on port 6053 (ESPHome) or port 8123 (HTTP)?"
echo "3. How many bytes transferred vs time elapsed?"
