#!/bin/bash
# test-nut-status.sh - Quick UPS health check via NUT
# Run on: pve (192.168.4.122)

set -e

UPS_NAME="${1:-ups}"

echo "=== NUT UPS Status Check ==="
echo ""

if ! command -v upsc &>/dev/null; then
    echo "ERROR: upsc not found. Is NUT installed?"
    exit 1
fi

if ! upsc "$UPS_NAME@localhost" &>/dev/null; then
    echo "ERROR: Cannot connect to UPS '$UPS_NAME'"
    echo "Check: systemctl status nut-server"
    exit 1
fi

echo "UPS: $UPS_NAME"
echo ""

# Key metrics
BATTERY_CHARGE=$(upsc "$UPS_NAME@localhost" battery.charge 2>/dev/null || echo "N/A")
BATTERY_RUNTIME=$(upsc "$UPS_NAME@localhost" battery.runtime 2>/dev/null || echo "N/A")
UPS_STATUS=$(upsc "$UPS_NAME@localhost" ups.status 2>/dev/null || echo "N/A")
UPS_LOAD=$(upsc "$UPS_NAME@localhost" ups.load 2>/dev/null || echo "N/A")
INPUT_VOLTAGE=$(upsc "$UPS_NAME@localhost" input.voltage 2>/dev/null || echo "N/A")
OUTPUT_VOLTAGE=$(upsc "$UPS_NAME@localhost" output.voltage 2>/dev/null || echo "N/A")

# Convert runtime to minutes
if [[ "$BATTERY_RUNTIME" != "N/A" ]]; then
    RUNTIME_MINS=$((BATTERY_RUNTIME / 60))
else
    RUNTIME_MINS="N/A"
fi

echo "┌─────────────────────────────────────┐"
echo "│ Battery Charge:  ${BATTERY_CHARGE}%"
echo "│ Battery Runtime: ${RUNTIME_MINS} minutes"
echo "│ UPS Status:      ${UPS_STATUS}"
echo "│ Load:            ${UPS_LOAD}%"
echo "│ Input Voltage:   ${INPUT_VOLTAGE}V"
echo "│ Output Voltage:  ${OUTPUT_VOLTAGE}V"
echo "└─────────────────────────────────────┘"
echo ""

# Status interpretation
case "$UPS_STATUS" in
    OL*)
        echo "✓ Status: ONLINE (on mains power)"
        ;;
    OB*)
        echo "⚠ Status: ON BATTERY"
        ;;
    LB*)
        echo "✗ Status: LOW BATTERY - shutdown imminent!"
        ;;
    *)
        echo "? Status: $UPS_STATUS"
        ;;
esac

# Tiered shutdown thresholds
echo ""
echo "Tiered Shutdown Thresholds:"
echo "  ≤40%: Shutdown pumped-piglet, still-fawn"
echo "  ≤20%: Shutdown MAAS VM (102)"
echo "  ≤10%: Shutdown chief-horse, pve"

# Check state file
STATE_FILE="/var/run/nut-shutdown-state"
if [[ -f "$STATE_FILE" ]]; then
    echo ""
    echo "Active shutdown state:"
    cat "$STATE_FILE"
fi

echo ""
echo "Full details: upsc $UPS_NAME@localhost"
