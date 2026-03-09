#!/bin/bash
# frigate-watchdog.sh - External Frigate health watchdog (runs on pve, outside K3s)
# Location on pve: /opt/nut/scripts/frigate-watchdog.sh
#
# Why: The in-cluster CronJob health checker can't alert when the cluster itself
# is degraded (node NotReady, etcd issues, scheduler down). This runs on the
# Proxmox host as a cron job, completely independent of K3s.
#
# Checks:
#   1. Frigate API reachable (via MetalLB IP)
#   2. Majority of cameras have frames (camera_fps > 0)
#
# Alerts via ntfy.sh + SMS (same channels as UPS alerts)
#
# Usage: ./frigate-watchdog.sh
#        FRIGATE_URL=http://192.168.4.81:5000 ./frigate-watchdog.sh

set -euo pipefail

# Source environment (SMS credentials deployed by NUT K8s Job)
ENV_FILE="${ENV_FILE:-/opt/nut/.env}"
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"

FRIGATE_URL="${FRIGATE_URL:-http://192.168.4.81:5000}"
NTFY_TOPIC="${NTFY_TOPIC:-homelab-frigate-watchdog}"
STATE_FILE="/var/run/frigate-watchdog-state"
LOG_FILE="/var/log/frigate-watchdog.log"
API_TIMEOUT=10

# SMS Gateway settings (shared with nut-notify.sh)
SMS_GATEWAY_IP="${SMS_GATEWAY_IP:-192.0.0.4}"
SMS_GATEWAY_PORT="${SMS_GATEWAY_PORT:-8082}"
SMS_GATEWAY_TOKEN="${SMS_GATEWAY_TOKEN:-}"
SMS_RECIPIENT="${SMS_RECIPIENT:-}"

# Cameras to skip (flaky WiFi, known intermittent)
SKIP_CAMERAS="${SKIP_CAMERAS:-reolink_doorbell}"

log() {
    local level="$1"
    shift
    local msg="$*"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $msg" >> "$LOG_FILE"
}

send_sms() {
    local message="$1"
    if [[ -z "$SMS_GATEWAY_TOKEN" ]] || [[ -z "$SMS_RECIPIENT" ]]; then
        log "DEBUG" "SMS not configured, skipping"
        return 0
    fi

    local gateway_ip
    gateway_ip=$(ip route show dev wlan0 2>/dev/null | grep default | awk '{print $3}' || true)

    for ip in "${SMS_GATEWAY_IP}" "${gateway_ip}"; do
        [[ -z "$ip" ]] && continue
        if curl -s -X POST "http://${ip}:${SMS_GATEWAY_PORT}/" \
            -H "Authorization: ${SMS_GATEWAY_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{\"to\": \"${SMS_RECIPIENT}\", \"message\": \"${message}\"}" \
            --connect-timeout 5 --max-time 10 2>/dev/null; then
            log "INFO" "SMS sent via ${ip}"
            return 0
        fi
    done
    log "WARN" "SMS delivery failed - could not reach gateway"
}

send_alert() {
    local title="$1"
    local body="$2"
    local priority="${3:-high}"

    # ntfy.sh push notification
    curl -s \
        -H "Title: [FRIGATE] $title" \
        -H "Priority: $priority" \
        -H "Tags: camera,warning" \
        -d "$body" \
        "https://ntfy.sh/${NTFY_TOPIC}" 2>/dev/null &

    # SMS via Pixel 7 gateway
    send_sms "[FRIGATE] ${title}"

    log "ALERT" "Sent: $title"
}

get_state() {
    if [[ -f "$STATE_FILE" ]]; then
        cat "$STATE_FILE"
    else
        echo "ok:0"
    fi
}

set_state() {
    echo "$1" > "$STATE_FILE"
}

main() {
    # Fetch Frigate stats
    local stats
    if ! stats=$(curl -s --max-time "$API_TIMEOUT" "${FRIGATE_URL}/api/stats" 2>/dev/null); then
        log "ERROR" "Frigate API unreachable at ${FRIGATE_URL}"

        local prev_state
        prev_state=$(get_state)
        local prev_status="${prev_state%%:*}"
        local prev_count="${prev_state##*:}"
        local fail_count=$((prev_count + 1))

        set_state "down:${fail_count}"

        # Alert on 2nd consecutive failure (10 min of downtime with 5-min cron)
        if [[ "$fail_count" -eq 2 ]]; then
            send_alert "Frigate UNREACHABLE" "Frigate API at ${FRIGATE_URL} has been unreachable for ~10 minutes. K3s cluster may be degraded. Check: ssh root@pumped-piglet.maas 'qm guest exec 105 -- bash -c \"sudo k3s kubectl get pods -n frigate\"'"
        # Reminder every 30 min (6 checks)
        elif [[ "$fail_count" -gt 2 ]] && [[ $((fail_count % 6)) -eq 0 ]]; then
            local mins=$((fail_count * 5))
            send_alert "Frigate STILL DOWN (${mins}min)" "Frigate has been unreachable for ~${mins} minutes. Manual intervention needed."
        fi
        return 0
    fi

    # Validate JSON response
    if ! echo "$stats" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        log "ERROR" "Frigate API returned invalid JSON"
        return 0
    fi

    # Check cameras
    local camera_check
    camera_check=$(echo "$stats" | python3 -c "
import sys, json

stats = json.load(sys.stdin)
cameras = stats.get('cameras', {})
skip = set('${SKIP_CAMERAS}'.split(','))

total = 0
down = []
for name, cam in cameras.items():
    if name in skip:
        continue
    total += 1
    fps = float(cam.get('camera_fps', 0))
    if fps < 1:
        down.append(name)

if total == 0:
    print('no_cameras:0:0')
elif len(down) > total / 2:
    print(f'majority_down:{len(down)}:{total}:' + ','.join(down))
else:
    print(f'ok:{len(down)}:{total}')
" 2>/dev/null)

    if [[ -z "$camera_check" ]]; then
        log "WARN" "Failed to parse camera stats"
        return 0
    fi

    local status="${camera_check%%:*}"
    local prev_state
    prev_state=$(get_state)
    local prev_status="${prev_state%%:*}"

    case "$status" in
        ok)
            if [[ "$prev_status" != "ok" ]]; then
                local prev_count="${prev_state##*:}"
                if [[ "$prev_count" -ge 2 ]]; then
                    send_alert "Frigate RECOVERED" "Frigate is back online and cameras are working." "default"
                fi
                log "INFO" "Recovered - cameras OK"
            else
                log "INFO" "Healthy - ${camera_check}"
            fi
            set_state "ok:0"
            ;;
        majority_down)
            local rest="${camera_check#*:}"
            local down_count="${rest%%:*}"
            rest="${rest#*:}"
            local total="${rest%%:*}"
            local cam_names="${rest#*:}"

            local prev_count="${prev_state##*:}"
            local fail_count=$((prev_count + 1))
            set_state "cameras_down:${fail_count}"

            log "WARN" "Cameras down: ${down_count}/${total} - ${cam_names}"

            if [[ "$fail_count" -eq 2 ]]; then
                send_alert "Cameras DOWN (${down_count}/${total})" "Majority of cameras have no frames: ${cam_names}. Frigate API is responsive but cameras are not streaming. Check network/camera power."
            elif [[ "$fail_count" -gt 2 ]] && [[ $((fail_count % 6)) -eq 0 ]]; then
                local mins=$((fail_count * 5))
                send_alert "Cameras STILL DOWN ${mins}min (${down_count}/${total})" "Cameras down for ~${mins}min: ${cam_names}"
            fi
            ;;
        no_cameras)
            log "WARN" "No monitored cameras found"
            set_state "no_cameras:1"
            ;;
    esac
}

main "$@"
