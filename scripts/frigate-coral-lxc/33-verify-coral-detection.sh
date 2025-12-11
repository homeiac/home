#!/bin/bash
# Frigate Coral LXC - Verify Coral Detection
# GitHub Issue: #168
# Checks Coral TPU inference speed

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Verify Coral Detection ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

if [[ -z "$VMID" ]]; then
    echo "❌ ERROR: VMID not set in config.env"
    exit 1
fi

echo "Container VMID: $VMID"
echo ""

echo "1. Checking Frigate detector stats..."
STATS=$(ssh root@"$PVE_HOST" "pct exec $VMID -- curl -s http://127.0.0.1:5000/api/stats 2>/dev/null" || echo "FAILED")

if [[ "$STATS" == "FAILED" ]] || [[ -z "$STATS" ]]; then
    echo "   ❌ Could not get Frigate stats"
    exit 1
fi

echo "   Raw stats response received"

echo ""
echo "2. Parsing detector information..."

# Check if jq is available locally
if command -v jq &> /dev/null; then
    DETECTORS=$(echo "$STATS" | jq '.detectors' 2>/dev/null || echo "PARSE_FAILED")

    if [[ "$DETECTORS" == "PARSE_FAILED" ]] || [[ "$DETECTORS" == "null" ]]; then
        echo "   ⚠️  No detectors configured or parse failed"
        echo "   Raw response:"
        echo "$STATS" | head -c 500
    else
        echo "$DETECTORS" | sed 's/^/   /'

        # Check for Coral detector
        CORAL_SPEED=$(echo "$STATS" | jq -r '.detectors.coral.inference_speed // empty' 2>/dev/null)

        if [[ -n "$CORAL_SPEED" ]]; then
            echo ""
            echo "   Coral inference speed: ${CORAL_SPEED}ms"

            # Check if speed is reasonable (8-20ms is good for Coral)
            SPEED_INT=${CORAL_SPEED%.*}
            if [[ "$SPEED_INT" -gt 0 ]] && [[ "$SPEED_INT" -lt 20 ]]; then
                echo "   ✅ Coral TPU is working! (speed < 20ms)"
            elif [[ "$SPEED_INT" -ge 20 ]] && [[ "$SPEED_INT" -lt 50 ]]; then
                echo "   ⚠️  Coral speed is slower than expected (USB 2.0?)"
            else
                echo "   ❌ Coral speed is too slow or not detected properly"
            fi
        else
            echo ""
            echo "   ⚠️  No Coral detector found"
            echo "   Available detectors:"
            echo "$STATS" | jq -r '.detectors | keys[]' 2>/dev/null || echo "   (none)"
        fi
    fi
else
    echo "   (jq not available locally - showing raw output)"
    echo "$STATS" | head -c 1000
fi

echo ""
echo "=== Coral Detection Verification Complete ==="
