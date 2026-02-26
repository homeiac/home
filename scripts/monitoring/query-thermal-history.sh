#!/bin/bash
# Query Prometheus for historical temperature and fan speed data for a given node
# Usage: ./query-thermal-history.sh [--hours N] [--node INSTANCE]
#
# Requires: kubectl access to the k3s cluster, jq
# Uses port-forward to reach Prometheus inside the cluster

set -euo pipefail

HOURS=24
INSTANCE="192.168.4.17:9100"  # still-fawn by default
STEP="5m"
PROM_PORT=9091  # local port for port-forward

usage() {
    echo "Usage: $0 [--hours N] [--node INSTANCE] [--step STEP]"
    echo ""
    echo "  --hours N        Hours of history to query (default: 24)"
    echo "  --node INSTANCE  Prometheus instance label (default: 192.168.4.17:9100 = still-fawn)"
    echo "  --step STEP      Query resolution step (default: 5m)"
    echo ""
    echo "Known nodes:"
    echo "  192.168.4.17:9100   still-fawn"
    echo "  192.168.4.175:9100  pumped-piglet"
    echo "  192.168.4.19:9100   chief-horse"
    echo "  192.168.4.172:9100  fun-bedbug"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hours) HOURS="$2"; shift 2 ;;
        --node)  INSTANCE="$2"; shift 2 ;;
        --step)  STEP="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown arg: $1"; usage ;;
    esac
done

# Determine Prometheus service
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
PROM_SVC="svc/kube-prometheus-stack-prometheus"
PROM_NS="monitoring"

echo "=== Thermal History Query ==="
echo "Node:  $INSTANCE"
echo "Range: last ${HOURS}h (step: $STEP)"
echo ""

# Start port-forward in background
echo "Starting port-forward to Prometheus..."
kubectl port-forward -n "$PROM_NS" "$PROM_SVC" "${PROM_PORT}:9090" &>/dev/null &
PF_PID=$!
trap "kill $PF_PID 2>/dev/null || true" EXIT

# Wait for port-forward to be ready
for i in $(seq 1 10); do
    if curl -s "http://localhost:${PROM_PORT}/-/ready" &>/dev/null; then
        break
    fi
    sleep 1
done

PROM_URL="http://localhost:${PROM_PORT}"
END=$(date +%s)
START=$((END - HOURS * 3600))

query_range() {
    local query="$1"
    local desc="$2"
    curl -s --fail -G "${PROM_URL}/api/v1/query_range" \
        --data-urlencode "query=${query}" \
        --data-urlencode "start=${START}" \
        --data-urlencode "end=${END}" \
        --data-urlencode "step=${STEP}" 2>/dev/null
}

format_temps() {
    local json="$1"
    local desc="$2"
    echo "$json" | jq -r --arg desc "$desc" '
        .data.result[] |
        .metric as $m |
        .values |
        (map(.[1] | tonumber) | min) as $min |
        (map(.[1] | tonumber) | max) as $max |
        (map(.[1] | tonumber) | add / length) as $avg |
        "\($m.chip // "unknown") \($m.sensor // $m.label // "unknown") | min: \($min | . * 10 | round / 10)°C  avg: \($avg | . * 10 | round / 10)°C  max: \($max | . * 10 | round / 10)°C"
    ' 2>/dev/null || echo "  (no data)"
}

format_fans() {
    local json="$1"
    curl_out=$(echo "$json" | jq -r '
        .data.result[] |
        .metric as $m |
        .values |
        (map(.[1] | tonumber) | min) as $min |
        (map(.[1] | tonumber) | max) as $max |
        (map(.[1] | tonumber) | add / length) as $avg |
        "\($m.chip // "unknown") \($m.sensor // $m.label // "unknown") | min: \($min | round) RPM  avg: \($avg | round) RPM  max: \($max | round) RPM"
    ' 2>/dev/null || echo "  (no data)")
    echo "$curl_out"
}

# --- Temperature metrics ---
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 TEMPERATURE (node_hwmon_temp_celsius)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
TEMP_JSON=$(query_range "node_hwmon_temp_celsius{instance=\"${INSTANCE}\"}" "temperature")
if echo "$TEMP_JSON" | jq -e '.data.result | length > 0' &>/dev/null; then
    format_temps "$TEMP_JSON" "temperature"
else
    echo "  No hwmon temp data. Trying node_thermal_zone_temp..."
    TEMP_JSON=$(query_range "node_thermal_zone_temp{instance=\"${INSTANCE}\"}" "thermal_zone")
    format_temps "$TEMP_JSON" "thermal_zone"
fi

# --- Fan speed metrics ---
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌀 FAN SPEED (node_hwmon_fan_rpm)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
FAN_JSON=$(query_range "node_hwmon_fan_rpm{instance=\"${INSTANCE}\"}" "fan")
if echo "$FAN_JSON" | jq -e '.data.result | length > 0' &>/dev/null; then
    format_fans "$FAN_JSON"
else
    echo "  No fan RPM data found"
fi

# --- Dump raw time series for detailed analysis ---
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📈 HOURLY TEMPERATURE AVERAGES (last ${HOURS}h)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Re-query with 1h step for readable hourly averages
HOURLY_TEMP=$(query_range "avg by (sensor, chip) (node_hwmon_temp_celsius{instance=\"${INSTANCE}\"})" "hourly_temp")
if echo "$HOURLY_TEMP" | jq -e '.data.result | length > 0' &>/dev/null; then
    # Get the hottest sensor for hourly breakdown
    echo "$HOURLY_TEMP" | jq -r '
        .data.result[] |
        .metric as $m |
        "\n  \($m.chip // "?") / \($m.sensor // "?")",
        (.values[] | "    \(.[0] | strftime("%Y-%m-%d %H:%M"))  \(.[1] | tonumber | . * 10 | round / 10)°C")
    ' 2>/dev/null || echo "  (parse error)"
else
    echo "  (no data)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📈 HOURLY FAN SPEED AVERAGES (last ${HOURS}h)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

HOURLY_FAN=$(query_range "avg by (sensor, chip) (node_hwmon_fan_rpm{instance=\"${INSTANCE}\"})" "hourly_fan")
if echo "$HOURLY_FAN" | jq -e '.data.result | length > 0' &>/dev/null; then
    echo "$HOURLY_FAN" | jq -r '
        .data.result[] |
        .metric as $m |
        "\n  \($m.chip // "?") / \($m.sensor // "?")",
        (.values[] | "    \(.[0] | strftime("%Y-%m-%d %H:%M"))  \(.[1] | tonumber | round) RPM")
    ' 2>/dev/null || echo "  (parse error)"
else
    echo "  (no data)"
fi

echo ""
echo "Done. Port-forward cleaned up."
