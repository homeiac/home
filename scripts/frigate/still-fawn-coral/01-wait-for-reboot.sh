#!/bin/bash
# 01-wait-for-reboot.sh - Wait for still-fawn to reboot
#
# Checks uptime to confirm the host actually rebooted (uptime < 3 min)

set -e

HOST="${1:-still-fawn.maas}"
MAX_WAIT=120  # seconds

echo "Waiting for $HOST to reboot (uptime < 3 min)..."
echo ""

start_time=$(date +%s)

while true; do
  current_time=$(date +%s)
  elapsed=$((current_time - start_time))

  if [ $elapsed -gt $MAX_WAIT ]; then
    echo "Timeout waiting for reboot after ${MAX_WAIT}s"
    exit 1
  fi

  uptime_output=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@$HOST "uptime" 2>/dev/null || echo "")

  if [ -n "$uptime_output" ]; then
    # Check if uptime indicates recent boot (< 3 minutes)
    if echo "$uptime_output" | grep -qE "up [0-2] min"; then
      echo "Host rebooted successfully!"
      echo "  $uptime_output"
      exit 0
    else
      echo "Host up but hasn't rebooted yet..."
      echo "  $uptime_output"
      sleep 5
    fi
  else
    echo "[$elapsed/$MAX_WAIT s] Host not responding..."
    sleep 10
  fi
done
