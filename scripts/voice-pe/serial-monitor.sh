#!/bin/bash
# Serial monitor for ESP32 using pyserial
# Usage: ./serial-monitor.sh [device] [duration_seconds]
#
# Unlike 'cat /dev/cu.usbmodem*' which hangs, this properly handles
# the serial connection with timeout and clean exit.

set -e

DEVICE="${1:-/dev/cu.usbmodem12201}"
DURATION="${2:-10}"

if [[ ! -e "$DEVICE" ]]; then
    echo "ERROR: Device $DEVICE not found"
    echo "Available devices:"
    ls /dev/cu.usb* 2>/dev/null || echo "  (none)"
    exit 1
fi

echo "=== ESP32 Serial Monitor ==="
echo "Device: $DEVICE"
echo "Duration: ${DURATION}s"
echo "==========================="
echo ""

# Use platformio's python environment which has pyserial
~/.platformio/penv/bin/python << EOF
import serial
import time
import sys

device = "$DEVICE"
duration = $DURATION

try:
    ser = serial.Serial(device, 115200, timeout=1)
    print(f"Connected to {device} at 115200 baud")
    print("-" * 40)

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
            time.sleep(0.1)

    print("-" * 40)
    print(f"Monitoring complete ({duration}s)")
    ser.close()

except serial.SerialException as e:
    print(f"Serial error: {e}")
    sys.exit(1)
except KeyboardInterrupt:
    print("\nInterrupted")
    sys.exit(0)
EOF
