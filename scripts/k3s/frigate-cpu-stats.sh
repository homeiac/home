#!/bin/bash
# Monitor Frigate CPU consumption on still-fawn K3s VM
# Bias-agnostic: shows all processes sorted by CPU usage
# Usage: ./frigate-cpu-stats.sh [interval_seconds]
# Usage: ./frigate-cpu-stats.sh --status  (one-time status report)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Status report mode
if [[ "$1" == "--status" || "$1" == "--verify" ]]; then
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║           FRIGATE SYSTEM STATUS REPORT                        ║"
    echo "║           $(date '+%Y-%m-%d %H:%M:%S')                              ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    # Collect all data first
    CONFIG=$(KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- \
        curl -s --max-time 10 http://localhost:5000/api/config 2>/dev/null)
    STATS=$(KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- \
        curl -s --max-time 10 http://localhost:5000/api/stats 2>/dev/null)

    if [[ -z "$CONFIG" || -z "$STATS" ]]; then
        echo "✗ CRITICAL: Cannot reach Frigate API"
        exit 1
    fi

    # Track issues for summary
    ISSUES=()
    WARNINGS=()

    #=== HARDWARE STATUS ===#
    echo "┌─ HARDWARE ─────────────────────────────────────────────────────┐"

    # Coral TPU
    INF_SPEED=$(echo "$STATS" | jq -r '.detectors.coral.inference_speed // 999')
    if (( $(echo "$INF_SPEED < 50" | bc -l) )); then
        echo "│ Coral TPU:     ✓ Working (${INF_SPEED}ms inference)"
    else
        echo "│ Coral TPU:     ✗ SLOW (${INF_SPEED}ms) - may be CPU fallback"
        ISSUES+=("Coral TPU slow/not working")
    fi

    # VAAPI
    VAAPI_COUNT=$(KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- \
        vainfo 2>&1 | grep -c "VAProfile" || echo "0")
    if [[ "$VAAPI_COUNT" -gt 0 ]]; then
        echo "│ VAAPI:         ✓ Working ($VAAPI_COUNT profiles)"
    else
        echo "│ VAAPI:         ✗ Not working"
        WARNINGS+=("VAAPI not available")
    fi

    # Memory
    MEM_OUT=$("$SCRIPT_DIR/exec-still-fawn.sh" "free -m" 2>/dev/null | jq -r '.["out-data"]')
    MEM_AVAIL=$(echo "$MEM_OUT" | awk '/Mem:/ {print $7}')
    MEM_TOTAL=$(echo "$MEM_OUT" | awk '/Mem:/ {print $2}')
    if [[ "$MEM_AVAIL" -gt 2000 ]]; then
        echo "│ Memory:        ✓ ${MEM_AVAIL}MB available / ${MEM_TOTAL}MB total"
    else
        echo "│ Memory:        ⚠ LOW ${MEM_AVAIL}MB available"
        WARNINGS+=("Low memory: ${MEM_AVAIL}MB")
    fi

    # USB errors
    USB_ERRORS=$("$SCRIPT_DIR/exec-still-fawn.sh" "dmesg | grep -ciE 'usb.*error|xhci.*error' || echo 0" 2>/dev/null | jq -r '.["out-data"]' | tr -d '[:space:]')
    if [[ "$USB_ERRORS" == "0" || -z "$USB_ERRORS" ]]; then
        echo "│ USB:           ✓ No errors in dmesg"
    else
        echo "│ USB:           ⚠ $USB_ERRORS errors in dmesg"
        WARNINGS+=("USB errors in dmesg")
    fi
    echo "└────────────────────────────────────────────────────────────────┘"
    echo ""

    #=== DETECTION STATUS ===#
    echo "┌─ DETECTION ───────────────────────────────────────────────────┐"

    # Detection stuck events
    STUCK_COUNT=$(KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate 2>/dev/null | \
        grep -c "Detection appears to be stuck" || echo "0")
    POD_AGE=$(KUBECONFIG=~/kubeconfig kubectl get pods -n frigate -l app=frigate -o jsonpath='{.items[0].status.startTime}' 2>/dev/null)

    if [[ "$STUCK_COUNT" -gt 0 ]]; then
        echo "│ Stuck events:  ⚠ $STUCK_COUNT since $POD_AGE"
        WARNINGS+=("Detection stuck $STUCK_COUNT times")
    else
        echo "│ Stuck events:  ✓ None since $POD_AGE"
    fi

    # Current detection rate
    DET_FPS=$(echo "$STATS" | jq -r '.detection_fps // 0')
    CORAL_CPU=$(echo "$STATS" | jq -r ".cpu_usages[(.detectors.coral.pid | tostring)].cpu // \"?\"")
    CORAL_AVG=$(echo "$STATS" | jq -r ".cpu_usages[(.detectors.coral.pid | tostring)].cpu_average // \"?\"")
    echo "│ Detection:     ${DET_FPS} det/s | Coral CPU: ${CORAL_CPU}% now, ${CORAL_AVG}% avg"

    # Per-camera breakdown
    echo "│ Cameras:"
    echo "$STATS" | jq -r '.cameras | to_entries[] | "│   \(.key): \(.value.detection_fps)/\(.value.camera_fps) det/cam fps"'

    # Check for high detection rate
    DOORBELL_DET=$(echo "$STATS" | jq -r '.cameras.reolink_doorbell.detection_fps // 0')
    DOORBELL_CAM=$(echo "$STATS" | jq -r '.cameras.reolink_doorbell.camera_fps // 5')
    RATIO=$(echo "$DOORBELL_DET / $DOORBELL_CAM" | bc -l 2>/dev/null || echo "1")
    if (( $(echo "$RATIO > 2" | bc -l) )); then
        echo "│                ⚠ doorbell det/cam ratio > 2x (motion triggering multiple regions)"
        WARNINGS+=("High doorbell detection rate")
    fi
    echo "└────────────────────────────────────────────────────────────────┘"
    echo ""

    #=== EMBEDDINGS/FACE RECOGNITION ===#
    echo "┌─ EMBEDDINGS ──────────────────────────────────────────────────┐"
    FACE_ENABLED=$(echo "$CONFIG" | jq -r '.face_recognition.enabled // false')
    EMBED_PROC=$("$SCRIPT_DIR/exec-still-fawn.sh" "ps aux | grep 'embeddings_manager' | grep -v grep" 2>/dev/null | jq -r '.["out-data"]')
    EMBED_CPU=$(echo "$EMBED_PROC" | awk '{print $3}')

    echo "│ face_recognition: $FACE_ENABLED"

    # Check OpenVINO status
    OPENVINO_FAIL=$(KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate --tail=1000 2>/dev/null | \
        grep -c "OpenVINO failed" || echo "0")
    if [[ "$OPENVINO_FAIL" -gt 0 ]]; then
        echo "│ OpenVINO:      ✗ Failed - using CPU fallback"
        ISSUES+=("OpenVINO failed, embeddings using CPU")
    else
        echo "│ OpenVINO:      ✓ Working"
    fi

    # Check if embeddings running when no person
    ACTIVE_PERSONS=$(KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- \
        curl -s "http://localhost:5000/api/events?in_progress=1&label=person" 2>/dev/null | jq 'length')
    echo "│ Active persons: $ACTIVE_PERSONS"
    echo "│ embeddings CPU: ${EMBED_CPU:-?}%"

    if [[ "$ACTIVE_PERSONS" == "0" && -n "$EMBED_CPU" ]]; then
        if (( $(echo "${EMBED_CPU:-0} > 5" | bc -l 2>/dev/null || echo 0) )); then
            echo "│                ⚠ Using CPU with no person detected"
            WARNINGS+=("Embeddings using ${EMBED_CPU}% CPU with no person")
        fi
    fi
    echo "└────────────────────────────────────────────────────────────────┘"
    echo ""

    #=== CONFIG ===#
    echo "┌─ CONFIGURATION ───────────────────────────────────────────────┐"
    echo "│ Detection resolution:"
    echo "$CONFIG" | jq -r '.cameras | to_entries[] | "│   \(.key): \(.value.detect.width)x\(.value.detect.height) @ \(.value.detect.fps)fps"'
    DOORBELL_RES=$(echo "$CONFIG" | jq -r '.cameras.reolink_doorbell.detect | "\(.width)x\(.height)"')
    if [[ "$DOORBELL_RES" == "1920x1080" ]]; then
        echo "│                ⚠ doorbell at full HD - consider lowering"
        WARNINGS+=("Doorbell detection at 1920x1080")
    fi

    MOTION_THRESH=$(echo "$CONFIG" | jq -r '.cameras.reolink_doorbell.motion.threshold // 25')
    echo "│ doorbell motion.threshold: $MOTION_THRESH"
    echo "└────────────────────────────────────────────────────────────────┘"
    echo ""

    #=== TOP PROCESSES ===#
    echo "┌─ TOP CPU CONSUMERS ───────────────────────────────────────────┐"
    "$SCRIPT_DIR/exec-still-fawn.sh" "ps aux --sort=-%cpu | head -8 | tail -7" 2>/dev/null | \
        jq -r '.["out-data"]' | awk '$3 > 1 {printf "│ %5.1f%%  %s\n", $3, $11}'
    echo "└────────────────────────────────────────────────────────────────┘"
    echo ""

    #=== SUMMARY ===#
    echo "╔════════════════════════════════════════════════════════════════╗"
    if [[ ${#ISSUES[@]} -gt 0 ]]; then
        echo "║ STATUS: ✗ ISSUES FOUND                                        ║"
        echo "╠════════════════════════════════════════════════════════════════╣"
        for issue in "${ISSUES[@]}"; do
            printf "║ ✗ %-60s ║\n" "$issue"
        done
    elif [[ ${#WARNINGS[@]} -gt 0 ]]; then
        echo "║ STATUS: ⚠ WARNINGS                                             ║"
    else
        echo "║ STATUS: ✓ ALL SYSTEMS NOMINAL                                  ║"
    fi

    if [[ ${#WARNINGS[@]} -gt 0 ]]; then
        echo "╠════════════════════════════════════════════════════════════════╣"
        for warn in "${WARNINGS[@]}"; do
            printf "║ ⚠ %-60s ║\n" "$warn"
        done
    fi
    echo "╚════════════════════════════════════════════════════════════════╝"

    exit 0
fi

INTERVAL="${1:-5}"

echo "=== Frigate CPU Monitor (still-fawn) ==="
echo "Interval: ${INTERVAL}s | Press Ctrl+C to stop"
echo "(Run with --verify for hardware check)"
echo ""

while true; do
    echo "--- $(date '+%H:%M:%S') ---"

    # Get Frigate stats via API
    STATS=$(KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate --request-timeout=10s -- \
        curl -s http://localhost:5000/api/stats 2>/dev/null || echo '{}')

    if [[ "$STATS" != "{}" ]]; then
        # Total system stats
        TOTAL_CPU=$(echo "$STATS" | jq -r '.cpu_usages["frigate.full_system"].cpu // "N/A"')
        TOTAL_AVG=$(echo "$STATS" | jq -r '.cpu_usages["frigate.full_system"].cpu_average // "N/A"')
        DETECTION_FPS=$(echo "$STATS" | jq -r '.detection_fps // "N/A"')

        echo "Total Frigate: ${TOTAL_CPU}% now, ${TOTAL_AVG}% avg | Detection FPS: ${DETECTION_FPS}"
        echo ""

        # Camera stats
        echo "Cameras (det_fps / cam_fps):"
        echo "$STATS" | jq -r '
            .cameras | to_entries | .[] |
            "  \(.key): \(.value.detection_fps)/\(.value.camera_fps) fps"
        '

        # Detector inference speed
        echo ""
        echo "Detectors:"
        echo "$STATS" | jq -r '
            .detectors | to_entries | .[] |
            "  \(.key): \(.value.inference_speed)ms inference"
        '
    else
        echo "Failed to get Frigate stats"
    fi

    # VM-level top processes (not just Frigate API)
    echo ""
    echo "VM top processes (actual CPU from ps aux):"
    "$SCRIPT_DIR/exec-still-fawn.sh" "ps aux --sort=-%cpu | head -15 | tail -14" 2>/dev/null | jq -r '.["out-data"]' | awk '$3 > 0.5 {printf "  %5.1f%%  %s\n", $3, $11}'

    # CPU time breakdown (user/system/softirq/iowait)
    echo ""
    echo "CPU time breakdown (/proc/stat):"
    "$SCRIPT_DIR/exec-still-fawn.sh" "cat /proc/stat | head -1" 2>/dev/null | jq -r '.["out-data"]' | awk '{
        total = $2+$3+$4+$5+$6+$7+$8+$9+$10
        if (total > 0) {
            printf "  user: %.1f%% | system: %.1f%% | softirq: %.1f%% | iowait: %.1f%%\n",
                $2/total*100, $4/total*100, $8/total*100, $6/total*100
        }
    }'

    # USB interrupt count (look for xhci or usb)
    echo ""
    echo "USB/interrupt activity:"
    "$SCRIPT_DIR/exec-still-fawn.sh" "grep -E 'xhci|usb|USB' /proc/interrupts | head -5" 2>/dev/null | jq -r '.["out-data"]' | awk '{printf "  %s: %s interrupts\n", $NF, $2}'

    # VM load average
    echo ""
    LOAD=$("$SCRIPT_DIR/exec-still-fawn.sh" "cat /proc/loadavg" 2>/dev/null | jq -r '.["out-data"]' | cut -d' ' -f1-3)
    echo "VM Load: $LOAD"

    echo ""
    sleep "$INTERVAL"
done
