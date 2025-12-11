#!/bin/bash
# Frigate Coral LXC - Verify Cameras
# GitHub Issue: #168
#
# Verifies cameras are streaming and object detection is working.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Verify Cameras ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo "Container: $VMID"
echo ""

# Check container is running
echo "1. Checking container status..."
STATUS=$(ssh root@"$PVE_HOST" "pct status $VMID" 2>/dev/null | awk '{print $2}')
if [ "$STATUS" != "running" ]; then
    echo "   ❌ Container $VMID is not running"
    exit 1
fi
echo "   ✅ Container is running"

# Check Frigate API
echo ""
echo "2. Checking Frigate API..."
API_RESPONSE=$(ssh root@"$PVE_HOST" "pct exec $VMID -- curl -s http://127.0.0.1:5000/api/config 2>/dev/null" || echo "FAILED")
if [ "$API_RESPONSE" = "FAILED" ] || [ -z "$API_RESPONSE" ]; then
    echo "   ❌ Frigate API not responding"
    echo "   Wait for Frigate to start, or check logs:"
    echo "   ssh root@$PVE_HOST \"pct exec $VMID -- journalctl -u frigate -n 50\""
    exit 1
fi
echo "   ✅ Frigate API responding"

# Get camera list
echo ""
echo "3. Checking configured cameras..."
CAMERAS=$(ssh root@"$PVE_HOST" "pct exec $VMID -- curl -s http://127.0.0.1:5000/api/config 2>/dev/null" | jq -r '.cameras | keys[]' 2>/dev/null || echo "")
if [ -z "$CAMERAS" ]; then
    echo "   ❌ No cameras found in config"
    exit 1
fi

CAMERA_COUNT=$(echo "$CAMERAS" | wc -l | tr -d ' ')
echo "   Found $CAMERA_COUNT cameras:"
echo "$CAMERAS" | while read cam; do
    echo "   - $cam"
done

# Check each camera's status
echo ""
echo "4. Checking camera status..."
for cam in $CAMERAS; do
    CAM_STATS=$(ssh root@"$PVE_HOST" "pct exec $VMID -- curl -s http://127.0.0.1:5000/api/$cam 2>/dev/null" || echo "{}")

    # Check if camera is detecting (has recent frame)
    CAMERA_FPS=$(echo "$CAM_STATS" | jq -r '.camera_fps // 0' 2>/dev/null || echo "0")
    DETECTION_FPS=$(echo "$CAM_STATS" | jq -r '.detection_fps // 0' 2>/dev/null || echo "0")
    PROCESS_FPS=$(echo "$CAM_STATS" | jq -r '.process_fps // 0' 2>/dev/null || echo "0")

    if [ "$CAMERA_FPS" != "0" ] && [ "$CAMERA_FPS" != "null" ]; then
        echo "   ✅ $cam: camera_fps=$CAMERA_FPS, detection_fps=$DETECTION_FPS, process_fps=$PROCESS_FPS"
    else
        echo "   ⚠️  $cam: Not receiving frames (camera_fps=0)"
        echo "      Check RTSP URL and credentials"
    fi
done

# Check detector stats
echo ""
echo "5. Checking Coral detector..."
DETECTOR_STATS=$(ssh root@"$PVE_HOST" "pct exec $VMID -- curl -s http://127.0.0.1:5000/api/stats 2>/dev/null" | jq '.detectors' 2>/dev/null || echo "{}")
INFERENCE_SPEED=$(echo "$DETECTOR_STATS" | jq -r '.coral.inference_speed // .ov.inference_speed // "N/A"' 2>/dev/null)
DETECTOR_TYPE=$(echo "$DETECTOR_STATS" | jq -r 'keys[0]' 2>/dev/null || echo "unknown")

echo "   Detector: $DETECTOR_TYPE"
echo "   Inference speed: ${INFERENCE_SPEED}ms"

if [ "$DETECTOR_TYPE" = "coral" ]; then
    echo "   ✅ Using Coral TPU"
else
    echo "   ⚠️  Not using Coral (using: $DETECTOR_TYPE)"
fi

# Check for recent detections
echo ""
echo "6. Checking recent detections..."
EVENTS=$(ssh root@"$PVE_HOST" "pct exec $VMID -- curl -s 'http://127.0.0.1:5000/api/events?limit=5' 2>/dev/null" || echo "[]")
EVENT_COUNT=$(echo "$EVENTS" | jq 'length' 2>/dev/null || echo "0")

if [ "$EVENT_COUNT" -gt 0 ]; then
    echo "   ✅ Found $EVENT_COUNT recent detection events"
    echo "$EVENTS" | jq -r '.[] | "   - \(.label) on \(.camera) at \(.start_time | todate)"' 2>/dev/null | head -5
else
    echo "   ⚠️  No recent detections (this is normal if cameras just started)"
fi

# Summary
echo ""
echo "=== Camera Verification Summary ==="
echo ""
echo "Cameras configured: $CAMERA_COUNT"
echo "Detector: $DETECTOR_TYPE (${INFERENCE_SPEED}ms)"
echo "Recent events: $EVENT_COUNT"
echo ""
echo "Access Frigate UI at: http://<FRIGATE_IP>:5000"
echo ""
echo "To check Frigate logs:"
echo "  ssh root@$PVE_HOST \"pct exec $VMID -- cat /dev/shm/logs/frigate/current | tail -50\""
