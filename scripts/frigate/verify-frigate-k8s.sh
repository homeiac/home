#!/bin/bash
#
# verify-frigate-k8s.sh
#
# Verify Frigate Kubernetes instance is healthy and ready
# Checks: pod status, cameras, MQTT, face recognition
# Exit codes: 0 = all healthy, 1 = issues found
#

set -euo pipefail

# Configuration
FRIGATE_URL="http://frigate.app.homelab"
NAMESPACE="frigate"
EXPECTED_CAMERAS=("old_ip_camera" "trendnet_ip_572w" "reolink_doorbell")
MQTT_CLIENT_ID="frigate-k8s"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track overall health
ALL_HEALTHY=true

echo "========================================="
echo "Frigate Kubernetes Instance Verification"
echo "========================================="
echo ""
echo "Frigate URL: $FRIGATE_URL"
echo "Namespace: $NAMESPACE"
echo "Kubeconfig: $KUBECONFIG"
echo ""

# Function to print status
print_status() {
    local status=$1
    local message=$2
    if [[ "$status" == "ok" ]]; then
        echo -e "${GREEN}✓${NC} $message"
    elif [[ "$status" == "warn" ]]; then
        echo -e "${YELLOW}⚠${NC} $message"
    else
        echo -e "${RED}✗${NC} $message"
        ALL_HEALTHY=false
    fi
}

# 1. Check Kubernetes pod status
echo "1. Checking Kubernetes pod status..."
if ! kubectl --kubeconfig="$KUBECONFIG" get namespace "$NAMESPACE" &>/dev/null; then
    print_status "fail" "Namespace '$NAMESPACE' not found"
else
    POD_STATUS=$(kubectl --kubeconfig="$KUBECONFIG" get pods -n "$NAMESPACE" -l app=frigate -o json)
    POD_COUNT=$(echo "$POD_STATUS" | jq -r '.items | length')

    if [[ "$POD_COUNT" -eq 0 ]]; then
        print_status "fail" "No Frigate pods found in namespace"
    else
        POD_NAME=$(echo "$POD_STATUS" | jq -r '.items[0].metadata.name')
        POD_PHASE=$(echo "$POD_STATUS" | jq -r '.items[0].status.phase')
        POD_READY=$(echo "$POD_STATUS" | jq -r '.items[0].status.conditions[] | select(.type=="Ready") | .status')

        if [[ "$POD_PHASE" == "Running" ]] && [[ "$POD_READY" == "True" ]]; then
            print_status "ok" "Pod $POD_NAME is Running and Ready"
        else
            print_status "fail" "Pod $POD_NAME is $POD_PHASE (Ready: $POD_READY)"
        fi
    fi
fi
echo ""

# 2. Check Frigate API version
echo "2. Checking Frigate API version..."
FRIGATE_VERSION=$(curl -sf "$FRIGATE_URL/api/version" || echo "")
if [[ -n "$FRIGATE_VERSION" ]]; then
    print_status "ok" "Frigate version: $FRIGATE_VERSION"
else
    print_status "fail" "Cannot access Frigate API at $FRIGATE_URL"
fi
echo ""

# 3. Check cameras
echo "3. Checking camera status..."
FRIGATE_CONFIG=$(curl -sf "$FRIGATE_URL/api/config" || echo "{}")
CONFIGURED_CAMERAS=$(echo "$FRIGATE_CONFIG" | jq -r '.cameras | keys[]' 2>/dev/null || echo "")

if [[ -z "$CONFIGURED_CAMERAS" ]]; then
    print_status "fail" "No cameras found in Frigate config"
else
    CAMERA_COUNT=$(echo "$CONFIGURED_CAMERAS" | wc -l | tr -d ' ')
    print_status "ok" "Found $CAMERA_COUNT cameras configured"

    # Check each expected camera
    for camera in "${EXPECTED_CAMERAS[@]}"; do
        if echo "$CONFIGURED_CAMERAS" | grep -q "^${camera}$"; then
            # Check if camera is enabled
            ENABLED=$(echo "$FRIGATE_CONFIG" | jq -r ".cameras.${camera}.enabled")
            FACE_RECOG=$(echo "$FRIGATE_CONFIG" | jq -r ".cameras.${camera}.face_recognition.enabled")

            if [[ "$ENABLED" == "true" ]]; then
                FACE_STATUS=""
                if [[ "$FACE_RECOG" == "true" ]]; then
                    FACE_STATUS=" (face recognition: enabled)"
                fi
                print_status "ok" "Camera '$camera' is enabled$FACE_STATUS"
            else
                print_status "warn" "Camera '$camera' is disabled"
            fi
        else
            print_status "fail" "Expected camera '$camera' not found"
        fi
    done
fi
echo ""

# 4. Check MQTT connection
echo "4. Checking MQTT configuration..."
MQTT_ENABLED=$(echo "$FRIGATE_CONFIG" | jq -r '.mqtt.enabled')
MQTT_HOST=$(echo "$FRIGATE_CONFIG" | jq -r '.mqtt.host')
MQTT_CID=$(echo "$FRIGATE_CONFIG" | jq -r '.mqtt.client_id')

if [[ "$MQTT_ENABLED" == "true" ]]; then
    print_status "ok" "MQTT is enabled"
    print_status "ok" "MQTT host: $MQTT_HOST"

    if [[ "$MQTT_CID" == "$MQTT_CLIENT_ID" ]]; then
        print_status "ok" "MQTT client_id: $MQTT_CID (correct for K8s instance)"
    else
        print_status "warn" "MQTT client_id: $MQTT_CID (expected: $MQTT_CLIENT_ID)"
    fi
else
    print_status "fail" "MQTT is disabled"
fi
echo ""

# 5. Check face recognition global setting
echo "5. Checking face recognition..."
FACE_RECOG_ENABLED=$(echo "$FRIGATE_CONFIG" | jq -r '.face_recognition.enabled')
FACE_RECOG_MODEL=$(echo "$FRIGATE_CONFIG" | jq -r '.face_recognition.model_size')

if [[ "$FACE_RECOG_ENABLED" == "true" ]]; then
    print_status "ok" "Face recognition is enabled (model: $FACE_RECOG_MODEL)"
else
    print_status "fail" "Face recognition is disabled"
fi
echo ""

# 6. Check camera streaming status via stats
echo "6. Checking camera streaming status..."
FRIGATE_STATS=$(curl -sf "$FRIGATE_URL/api/stats" || echo "{}")
CAMERA_STATS=$(echo "$FRIGATE_STATS" | jq -r '.cameras // {}')

if [[ "$CAMERA_STATS" == "{}" ]]; then
    print_status "warn" "No camera statistics available (may still be initializing)"
else
    for camera in "${EXPECTED_CAMERAS[@]}"; do
        if echo "$FRIGATE_CONFIG" | jq -e ".cameras.${camera}" > /dev/null 2>&1; then
            CAMERA_FPS=$(echo "$CAMERA_STATS" | jq -r ".${camera}.camera_fps // 0")
            PROCESS_FPS=$(echo "$CAMERA_STATS" | jq -r ".${camera}.process_fps // 0")

            if (( $(echo "$CAMERA_FPS > 0" | bc -l) )); then
                print_status "ok" "Camera '$camera' is streaming (camera_fps: $CAMERA_FPS, process_fps: $PROCESS_FPS)"
            else
                print_status "fail" "Camera '$camera' is not streaming (fps: $CAMERA_FPS)"
            fi
        fi
    done
fi
echo ""

# 7. Check GPU acceleration (if available)
echo "7. Checking hardware acceleration..."
HWACCEL=$(echo "$FRIGATE_CONFIG" | jq -r '.ffmpeg.hwaccel_args')
if [[ "$HWACCEL" == *"nvidia"* ]] || [[ "$HWACCEL" == *"cuda"* ]]; then
    print_status "ok" "NVIDIA GPU acceleration is configured"
elif [[ "$HWACCEL" != "null" ]] && [[ -n "$HWACCEL" ]]; then
    print_status "ok" "Hardware acceleration: $HWACCEL"
else
    print_status "warn" "No hardware acceleration configured"
fi
echo ""

# Summary
echo "========================================="
echo "VERIFICATION SUMMARY"
echo "========================================="
if [[ "$ALL_HEALTHY" == true ]]; then
    echo -e "${GREEN}✓ All checks passed - Frigate K8s instance is healthy${NC}"
    echo ""
    echo "Frigate is ready to be integrated with Home Assistant"
    exit 0
else
    echo -e "${RED}✗ Some checks failed - review issues above${NC}"
    echo ""
    echo "Please resolve issues before switching Home Assistant integration"
    exit 1
fi
