#!/bin/bash
# nut-notify.sh - Tiered shutdown script for NUT UPS events
# Location on pve: /opt/nut/scripts/nut-notify.sh (symlinked to /root/nut-notify.sh)
#
# Tiered shutdown based on battery level:
#   40%: Shutdown heavy hosts (pumped-piglet, still-fawn)
#   20%: Shutdown MAAS VM (102)
#   10%: Shutdown chief-horse, then pve itself

set -e

# Source environment (secrets deployed by K8s Job)
ENV_FILE="${ENV_FILE:-/opt/nut/.env}"
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"

LOG_FILE="/var/log/nut-notify.log"
STATE_FILE="/var/run/nut-shutdown-state"
UPS_NAME="${UPSNAME:-ups}"

# Notification settings
HOSTNAME=$(hostname)

# SMS Gateway settings (Pixel 7 hotspot - out-of-band when internet is down)
SMS_GATEWAY_IP="${SMS_GATEWAY_IP:-192.0.0.4}"
SMS_GATEWAY_PORT="${SMS_GATEWAY_PORT:-8082}"
SMS_GATEWAY_TOKEN="${SMS_GATEWAY_TOKEN:-}"
SMS_RECIPIENT="${SMS_RECIPIENT:-}"

TIER1_THRESHOLD=40
TIER2_THRESHOLD=20
TIER3_THRESHOLD=10

TIER1_HOSTS=("pumped-piglet.maas" "still-fawn.maas")
TIER3_HOSTS=("chief-horse.maas")
MAAS_VMID=102

log() {
    local level="$1"
    shift
    local msg="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $msg" | tee -a "$LOG_FILE"
    logger -t nut-notify "[$level] $msg"
}

send_sms() {
    local message="$1"
    if [[ -z "$SMS_GATEWAY_TOKEN" ]] || [[ -z "$SMS_RECIPIENT" ]]; then
        log "DEBUG" "SMS not configured, skipping"
        return 0
    fi

    # Try configured IP first, then try wlan0 gateway (for hotspot fallback)
    local gateway_ip
    gateway_ip=$(ip route show dev wlan0 2>/dev/null | grep default | awk '{print $3}')

    for ip in "${SMS_GATEWAY_IP}" "${gateway_ip}"; do
        [[ -z "$ip" ]] && continue
        log "INFO" "Trying SMS gateway at ${ip}:${SMS_GATEWAY_PORT}"
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

send_notification() {
    local subject="$1"
    local body="$2"
    local charge=$(get_battery_charge)
    local runtime=$(upsc "$UPS_NAME@localhost" battery.runtime 2>/dev/null || echo "unknown")
    local runtime_mins=$((runtime / 60))
    local t1=$(tier_done 1 && echo "DONE" || echo "pending")
    local t2=$(tier_done 2 && echo "DONE" || echo "pending")
    local t3=$(tier_done 3 && echo "DONE" || echo "pending")

    # Build message (avoiding colons at line start for YAML compatibility)
    local full_body="${body} | Battery=${charge}% | Runtime=${runtime_mins}min | Host=${HOSTNAME} | Tiers: T1=${t1} T2=${t2} T3=${t3}"

    # Send via ntfy.sh (works even when K8s/Prometheus is down)
    curl -s -H "Title: [HOMELAB UPS] $subject" -H "Priority: high" -H "Tags: electric_plug,warning" -d "$full_body" "https://ntfy.sh/homelab-pve-ups-alerts" 2>/dev/null &

    # Send SMS via Pixel 7 hotspot (out-of-band - works even when internet is down)
    local sms_msg="[UPS] ${subject} - ${charge}% (${runtime_mins}min)"
    send_sms "$sms_msg"

    log "INFO" "Notification sent: $subject"
}

get_battery_charge() {
    local charge
    charge=$(upsc "$UPS_NAME@localhost" battery.charge 2>/dev/null || echo "0")
    echo "${charge%.*}"
}

get_ups_status() {
    upsc "$UPS_NAME@localhost" ups.status 2>/dev/null || echo "UNKNOWN"
}

tier_done() {
    local tier="$1"
    [[ -f "$STATE_FILE" ]] && grep -q "^TIER${tier}_DONE$" "$STATE_FILE"
}

mark_tier_done() {
    local tier="$1"
    echo "TIER${tier}_DONE" >> "$STATE_FILE"
    log "INFO" "Marked Tier $tier as complete"
}

reset_state() {
    if [[ -f "$STATE_FILE" ]]; then
        rm -f "$STATE_FILE"
        log "INFO" "Reset shutdown state - power restored"
    fi
}

shutdown_host() {
    local host="$1"
    log "WARN" "Initiating shutdown of $host"
    if ssh -o ConnectTimeout=10 -o BatchMode=yes "root@$host" "shutdown -h now" 2>/dev/null; then
        log "INFO" "Shutdown command sent to $host"
        return 0
    else
        log "ERROR" "Failed to send shutdown to $host"
        return 1
    fi
}

shutdown_local_vm() {
    local vmid="$1"
    log "WARN" "Initiating shutdown of local VM $vmid"
    if qm shutdown "$vmid" --timeout 60 2>/dev/null; then
        log "INFO" "Shutdown initiated for VM $vmid"
        return 0
    else
        log "WARN" "Graceful shutdown failed, forcing stop of VM $vmid"
        qm stop "$vmid" --timeout 30 2>/dev/null || true
        return 0
    fi
}

execute_tier1() {
    if tier_done 1; then
        log "DEBUG" "Tier 1 already executed, skipping"
        return 0
    fi
    log "WARN" "=== TIER 1 SHUTDOWN: Heavy hosts (battery <= ${TIER1_THRESHOLD}%) ==="
    send_notification "Tier 1 Shutdown" "Shutting down heavy hosts: pumped-piglet, still-fawn (GPU/K3s workers)"
    for host in "${TIER1_HOSTS[@]}"; do
        shutdown_host "$host" &
    done
    wait
    mark_tier_done 1
}

execute_tier2() {
    if tier_done 2; then
        log "DEBUG" "Tier 2 already executed, skipping"
        return 0
    fi
    log "WARN" "=== TIER 2 SHUTDOWN: MAAS VM (battery <= ${TIER2_THRESHOLD}%) ==="
    send_notification "Tier 2 Shutdown" "Shutting down MAAS VM (DHCP/DNS server)"
    shutdown_local_vm "$MAAS_VMID"
    mark_tier_done 2
}

execute_tier3() {
    if tier_done 3; then
        log "DEBUG" "Tier 3 already executed, skipping"
        return 0
    fi
    log "CRIT" "=== TIER 3 SHUTDOWN: Critical infrastructure (battery <= ${TIER3_THRESHOLD}%) ==="
    send_notification "Tier 3 - FINAL SHUTDOWN" "Shutting down all remaining infrastructure. pve will shutdown in 10 seconds. Goodbye!"
    for host in "${TIER3_HOSTS[@]}"; do
        shutdown_host "$host" &
    done
    wait
    mark_tier_done 3
    sleep 10
    log "CRIT" "Initiating pve shutdown..."
    shutdown -h now "UPS battery critical - emergency shutdown"
}

process_battery_level() {
    local charge
    charge=$(get_battery_charge)
    log "INFO" "Current battery charge: ${charge}%"

    if [[ "$charge" -le "$TIER3_THRESHOLD" ]]; then
        execute_tier1
        execute_tier2
        execute_tier3
    elif [[ "$charge" -le "$TIER2_THRESHOLD" ]]; then
        execute_tier1
        execute_tier2
    elif [[ "$charge" -le "$TIER1_THRESHOLD" ]]; then
        execute_tier1
    fi
}

main() {
    local notify_type="${NOTIFYTYPE:-UNKNOWN}"
    local ups_name="${UPSNAME:-ups}"
    local battery_charge
    local ups_status

    battery_charge=$(get_battery_charge)
    ups_status=$(get_ups_status)

    log "INFO" "Event: $notify_type | UPS: $ups_name | Battery: ${battery_charge}% | Status: $ups_status"

    case "$notify_type" in
        ONLINE)
            log "INFO" "Power restored - UPS back online"
            send_notification "Power Restored" "Mains power has been restored. UPS back online."
            reset_state
            ;;
        ONBATT)
            log "WARN" "Running on battery power!"
            send_notification "POWER OUTAGE - On Battery" "Power outage detected! Running on UPS battery power. Tiered shutdown will begin if battery drops below 40%."
            process_battery_level
            ;;
        LOWBATT)
            log "CRIT" "Low battery warning from UPS!"
            send_notification "LOW BATTERY - Emergency Shutdown" "UPS battery critically low! Executing full tiered shutdown of all hosts."
            execute_tier1
            execute_tier2
            execute_tier3
            ;;
        FSD)
            log "CRIT" "Forced shutdown requested!"
            send_notification "FORCED SHUTDOWN" "Forced shutdown signal received. Executing emergency shutdown of all hosts."
            execute_tier1
            execute_tier2
            execute_tier3
            ;;
        COMMOK)
            log "INFO" "Communication with UPS restored"
            ;;
        COMMBAD)
            log "WARN" "Lost communication with UPS"
            ;;
        SHUTDOWN)
            log "CRIT" "System shutdown initiated by UPS"
            ;;
        REPLBATT)
            log "WARN" "UPS battery needs replacement"
            ;;
        *)
            log "DEBUG" "Unhandled event type: $notify_type"
            ;;
    esac
}

main "$@"
