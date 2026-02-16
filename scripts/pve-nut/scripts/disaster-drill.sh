#!/bin/bash
# disaster-drill.sh - Monthly SMS gateway test (disaster recovery drill)
# Location on pve: /opt/nut/scripts/disaster-drill.sh
# Scheduled via cron: First Saturday of each month at 10:00 AM
#
# Tests that SMS notifications work via Pixel 7 hotspot (out-of-band channel)
# when main internet/K8s infrastructure is down.

set -e

# Source environment (secrets deployed by K8s Job)
ENV_FILE="${ENV_FILE:-/opt/nut/.env}"
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"

LOG_FILE="/var/log/nut-disaster-drill.log"
HOSTNAME=$(hostname)

log() {
    local level="$1"
    shift
    local msg="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $msg" | tee -a "$LOG_FILE"
    logger -t nut-disaster-drill "[$level] $msg"
}

log "INFO" "=== Monthly UPS Disaster Drill ==="
log "INFO" "Host: $HOSTNAME"
log "INFO" "Date: $(date)"

# Check if SMS is configured
if [[ -z "$SMS_GATEWAY_TOKEN" ]] || [[ -z "$SMS_RECIPIENT" ]]; then
    log "ERROR" "SMS not configured - SMS_GATEWAY_TOKEN or SMS_RECIPIENT missing"
    log "ERROR" "Check /opt/nut/.env"
    exit 1
fi

# Try configured IP first, then try wlan0 gateway (for hotspot fallback)
gateway_ip=$(ip route show dev wlan0 2>/dev/null | grep default | awk '{print $3}')

success=false
for ip in "${SMS_GATEWAY_IP}" "${gateway_ip}"; do
    [[ -z "$ip" ]] && continue
    log "INFO" "Trying SMS gateway at ${ip}:${SMS_GATEWAY_PORT}"

    message="[DRILL] Monthly UPS disaster drill - $(date '+%Y-%m-%d %H:%M'). SMS notifications working. Host: ${HOSTNAME}"

    http_code=$(curl -s -w '%{http_code}' -o /tmp/sms-response.txt -X POST "http://${ip}:${SMS_GATEWAY_PORT}/" \
        -H "Authorization: ${SMS_GATEWAY_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"to\": \"${SMS_RECIPIENT}\", \"message\": \"${message}\"}" \
        --connect-timeout 10 --max-time 15 2>/dev/null || echo "000")

    log "DEBUG" "HTTP response code: $http_code"

    if [[ "$http_code" == "200" ]] || [[ "$http_code" == "204" ]]; then
        log "INFO" "SMS sent successfully via ${ip}"
        success=true
        break
    else
        log "WARN" "SMS failed via ${ip} (HTTP $http_code)"
        [[ -f /tmp/sms-response.txt ]] && cat /tmp/sms-response.txt >> "$LOG_FILE"
    fi
done

if $success; then
    log "INFO" "=== Disaster Drill PASSED ==="
    log "INFO" "Check your phone for the test SMS message."
    exit 0
else
    log "ERROR" "=== Disaster Drill FAILED ==="
    log "ERROR" "Could not send SMS via any gateway!"
    log "ERROR" "Check:"
    log "ERROR" "  1. Pixel 7 hotspot is enabled"
    log "ERROR" "  2. SMS Gateway app is running on Pixel 7"
    log "ERROR" "  3. pve can connect to hotspot WiFi"
    log "ERROR" "  4. /opt/nut/.env has correct credentials"
    exit 1
fi
