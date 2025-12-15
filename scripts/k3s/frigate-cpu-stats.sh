#!/bin/bash
# Monitor Frigate CPU consumption on still-fawn K3s VM
# Bias-agnostic: shows all processes sorted by CPU usage
# Usage: ./frigate-cpu-stats.sh [interval_seconds]
# Usage: ./frigate-cpu-stats.sh --status  (one-time status report, auto-saved)
# Usage: ./frigate-cpu-stats.sh --compare (compare with previous report)
# Usage: ./frigate-cpu-stats.sh --history (list saved reports)
# Usage: ./frigate-cpu-stats.sh --at "HH:MM" (what happened around this time today)
# Usage: ./frigate-cpu-stats.sh --at "YYYY-MM-DD HH:MM" (what happened at specific datetime)
# Usage: ./frigate-cpu-stats.sh --window "06:00-08:00" (events in time window)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORTS_DIR="$SCRIPT_DIR/doorbell-analysis/reports"
mkdir -p "$REPORTS_DIR"

# Get latest report for comparison
get_latest_report() {
    ls -t "$REPORTS_DIR"/status-*.json 2>/dev/null | head -1
}

# History mode - list saved reports
if [[ "$1" == "--history" ]]; then
    echo "=== Saved Frigate Status Reports ==="
    ls -la "$REPORTS_DIR"/status-*.json 2>/dev/null | tail -10 || echo "No reports saved yet"
    exit 0
fi

# Time-specific investigation: --at "HH:MM" or --at "YYYY-MM-DD HH:MM"
if [[ "$1" == "--at" ]]; then
    TIME_QUERY="$2"
    if [[ -z "$TIME_QUERY" ]]; then
        echo "Usage: $0 --at \"HH:MM\" or --at \"YYYY-MM-DD HH:MM\""
        echo "Example: $0 --at \"06:30\""
        echo "Example: $0 --at \"2025-12-15 06:30\""
        exit 1
    fi

    # If only time provided, assume today
    if [[ "$TIME_QUERY" =~ ^[0-9]{2}:[0-9]{2}$ ]]; then
        DATE_PART=$(date '+%Y-%m-%d')
        TIME_QUERY="$DATE_PART $TIME_QUERY"
    fi

    # Extract hour for grep pattern
    HOUR=$(echo "$TIME_QUERY" | grep -oE '[0-9]{2}:[0-9]{2}' | cut -d: -f1)
    PREV_HOUR=$(printf "%02d" $((10#$HOUR - 1)))
    NEXT_HOUR=$(printf "%02d" $((10#$HOUR + 1)))

    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║     WHAT HAPPENED AROUND $TIME_QUERY?                    ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    # Get logs (try to get enough history)
    LOGS=$(KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate --since=24h 2>/dev/null)

    # Build grep pattern for the time window
    # Use the bracketed local timestamp format: [YYYY-MM-DD HH:MM:SS]
    DATE_GREP=$(echo "$TIME_QUERY" | cut -d' ' -f1)
    # Match local time in brackets like [2025-12-15 06:xx or [15/Dec/2025:06:
    TIME_PATTERN="\[${DATE_GREP} ${PREV_HOUR}:|\[${DATE_GREP} ${HOUR}:|\[${DATE_GREP} ${NEXT_HOUR}:"

    echo "┌─ DETECTION STUCK EVENTS ──────────────────────────────────────┐"
    STUCK=$(echo "$LOGS" | grep "Detection appears to be stuck" | grep -E "$DATE_GREP" | grep -E "$TIME_PATTERN" || true)
    if [[ -n "$STUCK" ]]; then
        echo "$STUCK" | sed 's/.*\[\([0-9-]* [0-9:]*\)\].*/│ \1 - Detection stuck/' | head -10
    else
        echo "│ None in this window"
    fi
    echo "└────────────────────────────────────────────────────────────────┘"
    echo ""

    echo "┌─ DETECTOR RESTARTS ───────────────────────────────────────────┐"
    RESTARTS=$(echo "$LOGS" | grep -iE "Restarting detection|detector.*start" | grep -E "$DATE_GREP" | grep -E "$TIME_PATTERN" || true)
    if [[ -n "$RESTARTS" ]]; then
        echo "$RESTARTS" | sed 's/.*\[\([0-9-]* [0-9:]*\)\].*/│ \1 - Detector restart/' | head -10
    else
        echo "│ None in this window"
    fi
    echo "└────────────────────────────────────────────────────────────────┘"
    echo ""

    echo "┌─ CONFIG/MASK CHANGES ─────────────────────────────────────────┐"
    CONFIG_CHANGES=$(echo "$LOGS" | grep -iE "config|mask|zone|reload" | grep -E "$DATE_GREP" | grep -E "$TIME_PATTERN" || true)
    if [[ -n "$CONFIG_CHANGES" ]]; then
        echo "$CONFIG_CHANGES" | sed 's/.*\[\([0-9-]* [0-9:]*\)\].*frigate\.\([^ ]*\).*/│ \1 - \2/' | head -10
    else
        echo "│ None in this window"
    fi
    echo "└────────────────────────────────────────────────────────────────┘"
    echo ""

    echo "┌─ CAMERA EVENTS ───────────────────────────────────────────────┐"
    CAM=$(echo "$LOGS" | grep -iE "camera|ffmpeg|stream|timeout|disconnect" | grep -E "$DATE_GREP" | grep -E "$TIME_PATTERN" || true)
    if [[ -n "$CAM" ]]; then
        echo "$CAM" | head -10 | while read -r line; do
            TS=$(echo "$line" | grep -oE '\[[0-9-]+ [0-9:]+\]' | tr -d '[]')
            # Extract camera name or error type
            if echo "$line" | grep -q "timeout"; then
                echo "│ $TS - Stream timeout"
            elif echo "$line" | grep -q "disconnect"; then
                echo "│ $TS - Camera disconnect"
            elif echo "$line" | grep -q "error"; then
                echo "│ $TS - Stream error"
            else
                echo "│ $TS - Camera event"
            fi
        done
    else
        echo "│ None in this window"
    fi
    echo "└────────────────────────────────────────────────────────────────┘"
    echo ""

    echo "┌─ ERRORS ──────────────────────────────────────────────────────┐"
    ERRS=$(echo "$LOGS" | grep -iE "error|exception|failed" | grep -v "OpenVINO" | grep -E "$DATE_GREP" | grep -E "$TIME_PATTERN" || true)
    if [[ -n "$ERRS" ]]; then
        echo "$ERRS" | head -10 | while read -r line; do
            TS=$(echo "$line" | grep -oE '\[[0-9-]+ [0-9:]+\]' | tr -d '[]' || echo "unknown")
            MSG=$(echo "$line" | grep -oE '(error|Error|ERROR)[^"]*' | head -1 | cut -c1-50)
            echo "│ $TS - $MSG"
        done
    else
        echo "│ None in this window"
    fi
    echo "└────────────────────────────────────────────────────────────────┘"
    echo ""

    echo "┌─ ALL ACTIVITY (raw, ±1 hour) ─────────────────────────────────┐"
    ALL=$(echo "$LOGS" | grep -E "$DATE_GREP" | grep -E "$TIME_PATTERN" | grep -v "127.0.0.1.*HTTP" | head -20 || true)
    if [[ -n "$ALL" ]]; then
        echo "$ALL" | head -15 | while read -r line; do
            echo "│ $(echo "$line" | cut -c1-70)"
        done
        COUNT=$(echo "$ALL" | wc -l | tr -d ' ')
        if [[ "$COUNT" -gt 15 ]]; then
            echo "│ ... and $((COUNT - 15)) more lines"
        fi
    else
        echo "│ No log entries found in this window"
        echo "│ Note: Pod logs may not go back this far"
    fi
    echo "└────────────────────────────────────────────────────────────────┘"

    exit 0
fi

# Time window investigation: --window "06:00-08:00"
if [[ "$1" == "--window" ]]; then
    WINDOW="$2"
    if [[ -z "$WINDOW" || ! "$WINDOW" =~ ^[0-9]{2}:[0-9]{2}-[0-9]{2}:[0-9]{2}$ ]]; then
        echo "Usage: $0 --window \"HH:MM-HH:MM\""
        echo "Example: $0 --window \"06:00-08:00\""
        exit 1
    fi

    START_HOUR=$(echo "$WINDOW" | cut -d- -f1 | cut -d: -f1)
    END_HOUR=$(echo "$WINDOW" | cut -d- -f2 | cut -d: -f1)
    TODAY=$(date '+%Y-%m-%d')

    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║     EVENTS IN WINDOW: $TODAY $WINDOW                    ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    LOGS=$(KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate --since=24h 2>/dev/null)

    # Build hour pattern - match bracketed local timestamps [YYYY-MM-DD HH:
    HOUR_PATTERN=""
    for h in $(seq -f "%02g" $((10#$START_HOUR)) $((10#$END_HOUR))); do
        [[ -n "$HOUR_PATTERN" ]] && HOUR_PATTERN="$HOUR_PATTERN|"
        HOUR_PATTERN="${HOUR_PATTERN}\[${TODAY} ${h}:"
    done

    echo "┌─ EVENT SUMMARY ───────────────────────────────────────────────┐"
    STUCK_CT=$(echo "$LOGS" | grep "Detection appears to be stuck" | grep "$TODAY" | grep -cE "$HOUR_PATTERN" || echo 0)
    RESTART_CT=$(echo "$LOGS" | grep "Restarting detection" | grep "$TODAY" | grep -cE "$HOUR_PATTERN" || echo 0)
    ERROR_CT=$(echo "$LOGS" | grep -iE "error|failed" | grep -v "OpenVINO" | grep "$TODAY" | grep -cE "$HOUR_PATTERN" || echo 0)
    echo "│ Detection stuck:   $STUCK_CT events"
    echo "│ Detector restarts: $RESTART_CT"
    echo "│ Errors:            $ERROR_CT"
    echo "└────────────────────────────────────────────────────────────────┘"
    echo ""

    echo "┌─ TIMELINE ────────────────────────────────────────────────────┐"
    echo "$LOGS" | grep "$TODAY" | grep -E "$HOUR_PATTERN" | \
        grep -iE "stuck|restart|error|config|mask|start|stop" | \
        grep -v "OpenVINO" | head -30 | while read -r line; do
            TS=$(echo "$line" | grep -oE '\[[0-9-]+ [0-9:]+\]' | tr -d '[]')
            if echo "$line" | grep -q "stuck"; then
                echo "│ $TS ⚠ STUCK"
            elif echo "$line" | grep -q -i "restart"; then
                echo "│ $TS 🔄 RESTART"
            elif echo "$line" | grep -q -i "error"; then
                echo "│ $TS ❌ ERROR"
            elif echo "$line" | grep -q -i "config\|mask"; then
                echo "│ $TS 🔧 CONFIG"
            else
                echo "│ $TS 📝 EVENT"
            fi
        done || echo "│ No significant events in window"
    echo "└────────────────────────────────────────────────────────────────┘"

    exit 0
fi

# Compare mode - show diff between last two reports
if [[ "$1" == "--compare" ]]; then
    REPORTS=($(ls -t "$REPORTS_DIR"/status-*.json 2>/dev/null | head -2))
    if [[ ${#REPORTS[@]} -lt 2 ]]; then
        echo "Need at least 2 reports to compare. Found: ${#REPORTS[@]}"
        exit 1
    fi

    CURRENT="${REPORTS[0]}"
    PREVIOUS="${REPORTS[1]}"

    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║           FRIGATE STATUS COMPARISON                           ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Previous: $(basename "$PREVIOUS")"
    echo "Current:  $(basename "$CURRENT")"
    echo ""

    # Compare key metrics
    echo "┌─ CHANGES ─────────────────────────────────────────────────────┐"

    PREV_DET=$(jq -r '.detection_fps' "$PREVIOUS")
    CURR_DET=$(jq -r '.detection_fps' "$CURRENT")
    echo "│ Detection FPS:    $PREV_DET → $CURR_DET"

    PREV_CORAL=$(jq -r '.coral_cpu_avg' "$PREVIOUS")
    CURR_CORAL=$(jq -r '.coral_cpu_avg' "$CURRENT")
    echo "│ Coral CPU avg:    $PREV_CORAL% → $CURR_CORAL%"

    PREV_STUCK=$(jq -r '.stuck_count' "$PREVIOUS")
    CURR_STUCK=$(jq -r '.stuck_count' "$CURRENT")
    echo "│ Stuck events:     $PREV_STUCK → $CURR_STUCK"

    PREV_THRESH=$(jq -r '.motion_threshold' "$PREVIOUS")
    CURR_THRESH=$(jq -r '.motion_threshold' "$CURRENT")
    if [[ "$PREV_THRESH" != "$CURR_THRESH" ]]; then
        echo "│ Motion threshold: $PREV_THRESH → $CURR_THRESH ⚠ CHANGED"
    fi

    PREV_MEM=$(jq -r '.memory_avail_mb' "$PREVIOUS")
    CURR_MEM=$(jq -r '.memory_avail_mb' "$CURRENT")
    echo "│ Memory avail:     ${PREV_MEM}MB → ${CURR_MEM}MB"

    PREV_INF=$(jq -r '.inference_speed_ms' "$PREVIOUS")
    CURR_INF=$(jq -r '.inference_speed_ms' "$CURRENT")
    echo "│ Inference speed:  ${PREV_INF}ms → ${CURR_INF}ms"

    echo "└────────────────────────────────────────────────────────────────┘"

    # Show full config diff if exists
    PREV_CONFIG=$(jq -r '.config_snapshot' "$PREVIOUS" 2>/dev/null)
    CURR_CONFIG=$(jq -r '.config_snapshot' "$CURRENT" 2>/dev/null)
    if [[ "$PREV_CONFIG" != "$CURR_CONFIG" && -n "$PREV_CONFIG" && -n "$CURR_CONFIG" ]]; then
        echo ""
        echo "┌─ CONFIG CHANGES ──────────────────────────────────────────────┐"
        diff <(echo "$PREV_CONFIG" | jq -S .) <(echo "$CURR_CONFIG" | jq -S .) 2>/dev/null | head -20 || echo "│ (diff failed)"
        echo "└────────────────────────────────────────────────────────────────┘"
    fi

    exit 0
fi

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
    MEM_OUT=$("$SCRIPT_DIR/exec-still-fawn.sh" "free -m" 2>/dev/null | jq -r '.["out-data"]' 2>/dev/null || echo "")
    MEM_AVAIL=$(echo "$MEM_OUT" | awk '/Mem:/ {print $7}' | tr -d '\n')
    MEM_TOTAL=$(echo "$MEM_OUT" | awk '/Mem:/ {print $2}' | tr -d '\n')
    # Fallback if parsing failed
    [[ -z "$MEM_AVAIL" || "$MEM_AVAIL" == "0" ]] && MEM_AVAIL="N/A"
    [[ -z "$MEM_TOTAL" || "$MEM_TOTAL" == "0" ]] && MEM_TOTAL="N/A"
    if [[ "$MEM_AVAIL" != "N/A" && "$MEM_AVAIL" -gt 2000 ]]; then
        echo "│ Memory:        ✓ ${MEM_AVAIL}MB available / ${MEM_TOTAL}MB total"
    elif [[ "$MEM_AVAIL" == "N/A" ]]; then
        echo "│ Memory:        ? Unable to query"
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
    OPENVINO_FAIL_RAW=$(KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate --tail=1000 2>/dev/null | \
        grep -c "OpenVINO failed" 2>/dev/null) || true
    OPENVINO_FAIL="${OPENVINO_FAIL_RAW:-0}"
    OPENVINO_FAIL="${OPENVINO_FAIL//[^0-9]/}"  # Keep only digits
    [[ -z "$OPENVINO_FAIL" ]] && OPENVINO_FAIL=0
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

    #=== RECENT LOG EVENTS ===#
    echo "┌─ RECENT LOG EVENTS (last 6 hours) ───────────────────────────┐"
    LOGS=$(KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate --since=6h 2>/dev/null)

    # Detection stuck events with timestamps
    STUCK_TIMES=$(echo "$LOGS" | grep "Detection appears to be stuck" | tail -5 | \
        sed 's/.*\[\([0-9-]* [0-9:]*\)\].*/│ STUCK: \1/')
    if [[ -n "$STUCK_TIMES" ]]; then
        echo "$STUCK_TIMES"
    fi

    # Config reloads
    CONFIG_RELOADS=$(echo "$LOGS" | grep -iE "config.*reload|reload.*config|configuration changed" | tail -3 | \
        sed 's/.*\[\([0-9-]* [0-9:]*\)\].*/│ CONFIG RELOAD: \1/')
    if [[ -n "$CONFIG_RELOADS" ]]; then
        echo "$CONFIG_RELOADS"
    fi

    # Detector restarts
    DETECTOR_RESTARTS=$(echo "$LOGS" | grep -iE "detector.*start|starting.*detect|Restarting detection" | tail -3 | \
        sed 's/.*\[\([0-9-]* [0-9:]*\)\].*/│ DETECTOR RESTART: \1/')
    if [[ -n "$DETECTOR_RESTARTS" ]]; then
        echo "$DETECTOR_RESTARTS"
    fi

    # Camera disconnects/reconnects
    CAM_EVENTS=$(echo "$LOGS" | grep -iE "camera.*disconnect|camera.*connect|stream.*error|ffmpeg.*error" | tail -3 | \
        sed 's/.*\[\([0-9-]* [0-9:]*\)\].*\(camera\|ffmpeg\)/│ CAM: \1 -/')
    if [[ -n "$CAM_EVENTS" ]]; then
        echo "$CAM_EVENTS"
    fi

    # Motion mask changes
    MASK_EVENTS=$(echo "$LOGS" | grep -iE "motion.*mask|mask.*update|zone.*update" | tail -3 | \
        sed 's/.*\[\([0-9-]* [0-9:]*\)\].*/│ MASK: \1/')
    if [[ -n "$MASK_EVENTS" ]]; then
        echo "$MASK_EVENTS"
    fi

    # Errors
    ERRORS=$(echo "$LOGS" | grep -iE "error|exception|failed" | grep -v "OpenVINO failed" | tail -3 | \
        sed 's/.*\[\([0-9-]* [0-9:]*\)\].*\(ERROR\|error\|Error\).*/│ ERROR: \1/')
    if [[ -n "$ERRORS" ]]; then
        echo "$ERRORS"
    fi

    # If no events found
    if [[ -z "$STUCK_TIMES" && -z "$CONFIG_RELOADS" && -z "$DETECTOR_RESTARTS" && -z "$CAM_EVENTS" && -z "$MASK_EVENTS" && -z "$ERRORS" ]]; then
        echo "│ No significant events in last 6 hours"
    fi
    echo "└────────────────────────────────────────────────────────────────┘"
    echo ""

    # Store log summary for JSON
    LOG_EVENTS_JSON=$(cat << LOGJSON
{
  "stuck_events_last_6h": $(echo "$LOGS" | grep -c "Detection appears to be stuck" || echo 0),
  "config_reloads": $(echo "$LOGS" | grep -ciE "config.*reload|reload.*config" || echo 0),
  "detector_restarts": $(echo "$LOGS" | grep -c "Restarting detection" || echo 0),
  "camera_errors": $(echo "$LOGS" | grep -ciE "camera.*disconnect|stream.*error|ffmpeg.*error" || echo 0),
  "last_stuck_time": "$(echo "$LOGS" | grep "Detection appears to be stuck" | tail -1 | sed 's/.*\[\([0-9-]* [0-9:]*\)\].*/\1/' || echo "")",
  "last_error": "$(echo "$LOGS" | grep -iE "error|exception|failed" | grep -v "OpenVINO" | tail -1 | cut -c1-100 || echo "")"
}
LOGJSON
)

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

    # Save JSON report for comparison
    REPORT_FILE="$REPORTS_DIR/status-$(date '+%Y%m%d-%H%M%S').json"

    # Get doorbell config for snapshot
    DOORBELL_CONFIG=$(echo "$CONFIG" | jq '.cameras.reolink_doorbell // {}')

    cat > "$REPORT_FILE" << EOF
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "timestamp_local": "$(date '+%Y-%m-%d %H:%M:%S %Z')",
  "detection_fps": $DET_FPS,
  "coral_cpu_now": "${CORAL_CPU}",
  "coral_cpu_avg": "${CORAL_AVG}",
  "inference_speed_ms": $INF_SPEED,
  "stuck_count": $STUCK_COUNT,
  "memory_avail_mb": "${MEM_AVAIL}",
  "memory_total_mb": "${MEM_TOTAL}",
  "motion_threshold": $MOTION_THRESH,
  "usb_errors": "${USB_ERRORS:-0}",
  "vaapi_profiles": $VAAPI_COUNT,
  "face_recognition_enabled": $FACE_ENABLED,
  "openvino_failures": $OPENVINO_FAIL,
  "cameras": {
    "old_ip_camera": $(echo "$STATS" | jq '.cameras.old_ip_camera'),
    "trendnet_ip_572w": $(echo "$STATS" | jq '.cameras.trendnet_ip_572w'),
    "reolink_doorbell": $(echo "$STATS" | jq '.cameras.reolink_doorbell')
  },
  "doorbell_detect_resolution": "$DOORBELL_RES",
  "config_snapshot": $(echo "$DOORBELL_CONFIG" | jq -c '.'),
  "log_events": $LOG_EVENTS_JSON
}
EOF

    echo ""
    echo "📊 Report saved: $REPORT_FILE"

    # Show comparison if previous report exists
    PREV_REPORT=$(ls -t "$REPORTS_DIR"/status-*.json 2>/dev/null | sed -n '2p')
    if [[ -n "$PREV_REPORT" ]]; then
        PREV_DET=$(jq -r '.detection_fps' "$PREV_REPORT")
        PREV_CORAL=$(jq -r '.coral_cpu_avg' "$PREV_REPORT")
        PREV_STUCK=$(jq -r '.stuck_count' "$PREV_REPORT")
        PREV_TIME=$(jq -r '.timestamp_local' "$PREV_REPORT")

        echo ""
        echo "┌─ vs PREVIOUS ($PREV_TIME) ──────────────────────┐"
        echo "│ Detection FPS: $PREV_DET → $DET_FPS"
        echo "│ Coral CPU avg: $PREV_CORAL% → ${CORAL_AVG}%"
        echo "│ Stuck events:  $PREV_STUCK → $STUCK_COUNT"
        echo "└────────────────────────────────────────────────────────────────┘"
    fi

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
