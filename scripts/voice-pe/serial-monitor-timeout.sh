#!/bin/bash
# Serial monitor with hard timeout - won't hang
# Uses timeout command to guarantee termination
#
# Usage: ./serial-monitor-timeout.sh [device] [duration] [filter]
# Example: ./serial-monitor-timeout.sh /dev/cu.usbmodem12201 30 "api|error"

set -e

DEVICE="${1:-/dev/cu.usbmodem12201}"
DURATION="${2:-15}"
FILTER="${3:-}"  # Optional grep pattern

if [[ ! -e "$DEVICE" ]]; then
    echo "ERROR: Device $DEVICE not found"
    echo "Available devices:"
    ls /dev/cu.usb* 2>/dev/null || echo "  (none)"
    exit 1
fi

echo "=== ESP32 Serial Monitor (timeout: ${DURATION}s) ==="
echo "Device: $DEVICE"
[[ -n "$FILTER" ]] && echo "Filter: $FILTER"
echo "=========================================="
echo ""

# Use timeout to guarantee termination
# The inner script handles the serial connection
if [[ -n "$FILTER" ]]; then
    # With filter - use stdbuf to prevent grep buffering
    timeout --signal=KILL $((DURATION + 5)) bash -c "
        ~/.platformio/penv/bin/python << 'PYEOF' | stdbuf -oL grep -iE '$FILTER'
import serial
import time
import sys

device = '$DEVICE'
duration = $DURATION

try:
    ser = serial.Serial(device, 115200, timeout=1)
    print(f'Connected to {device}', flush=True)

    # Trigger ESP32 reset
    ser.dtr = False
    ser.rts = True
    time.sleep(0.1)
    ser.dtr = True
    ser.rts = False
    time.sleep(0.1)
    ser.dtr = False

    start = time.time()
    while time.time() - start < duration:
        if ser.in_waiting:
            try:
                line = ser.readline().decode('utf-8', errors='replace').rstrip()
                if line:
                    print(line, flush=True)
            except Exception as e:
                print(f'[decode error: {e}]', flush=True)
        else:
            time.sleep(0.05)

    ser.close()
except serial.SerialException as e:
    print(f'Serial error: {e}', flush=True)
    sys.exit(1)
except KeyboardInterrupt:
    sys.exit(0)
PYEOF
" || true
else
    # No filter - direct output
    timeout --signal=KILL $((DURATION + 5)) ~/.platformio/penv/bin/python << PYEOF || true
import serial
import time
import sys

device = "$DEVICE"
duration = $DURATION

try:
    ser = serial.Serial(device, 115200, timeout=1)
    print(f"Connected to {device}", flush=True)

    # Trigger ESP32 reset
    ser.dtr = False
    ser.rts = True
    time.sleep(0.1)
    ser.dtr = True
    ser.rts = False
    time.sleep(0.1)
    ser.dtr = False

    start = time.time()
    while time.time() - start < duration:
        if ser.in_waiting:
            try:
                line = ser.readline().decode('utf-8', errors='replace').rstrip()
                if line:
                    print(line, flush=True)
            except Exception as e:
                print(f"[decode error: {e}]", flush=True)
        else:
            time.sleep(0.05)

    ser.close()
except serial.SerialException as e:
    print(f"Serial error: {e}", flush=True)
    sys.exit(1)
except KeyboardInterrupt:
    sys.exit(0)
PYEOF
fi

echo ""
echo "=== Done (${DURATION}s limit) ==="
