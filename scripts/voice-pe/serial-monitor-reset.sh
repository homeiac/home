#!/bin/bash
# Serial monitor with ESP32 reset trigger
# Sends DTR/RTS toggle to trigger reset and capture boot logs
#
# Usage: ./serial-monitor-reset.sh [device] [duration_seconds]

set -e

DEVICE="${1:-/dev/cu.usbmodem12201}"
DURATION="${2:-15}"

if [[ ! -e "$DEVICE" ]]; then
    echo "ERROR: Device $DEVICE not found"
    echo "Available devices:"
    ls /dev/cu.usb* 2>/dev/null || echo "  (none)"
    exit 1
fi

echo "=== ESP32 Serial Monitor (with reset) ==="
echo "Device: $DEVICE"
echo "Duration: ${DURATION}s"
echo "=========================================="
echo ""

~/.platformio/penv/bin/python << EOF
import serial
import time
import sys

device = "$DEVICE"
duration = $DURATION

try:
    ser = serial.Serial(device, 115200, timeout=1)
    print(f"Connected to {device}")

    # Trigger ESP32 reset via DTR/RTS
    print("Triggering reset...")
    ser.dtr = False
    ser.rts = True
    time.sleep(0.1)
    ser.dtr = True
    ser.rts = False
    time.sleep(0.1)
    ser.dtr = False

    print("Capturing boot logs...")
    print("-" * 50)

    start = time.time()
    while time.time() - start < duration:
        if ser.in_waiting:
            try:
                line = ser.readline().decode('utf-8', errors='replace').rstrip()
                if line:
                    print(line)
            except Exception as e:
                print(f"[decode error: {e}]")
        else:
            time.sleep(0.05)

    print("-" * 50)
    print(f"Done ({duration}s)")
    ser.close()

except serial.SerialException as e:
    print(f"Serial error: {e}")
    sys.exit(1)
except KeyboardInterrupt:
    print("\nInterrupted")
    sys.exit(0)
EOF
