#!/bin/bash
# Start Crucible downstairs on proper-raptor
#
# Usage: ./start-downstairs.sh [--foreground]
#
set -e

HOST="ubuntu@192.168.4.189"
CRUCIBLE_BIN="/home/ubuntu/crucible-downstairs"
REGION_DIR="/crucible/regions"
PORT=3810

echo "=== Starting Crucible downstairs on proper-raptor ==="

# Check SSH access
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" "echo 'SSH OK'" 2>/dev/null; then
    echo "ERROR: Cannot SSH to $HOST"
    exit 1
fi

# Check if already running
if ssh "$HOST" "pgrep -f crucible-downstairs" 2>/dev/null; then
    echo "Crucible downstairs already running:"
    ssh "$HOST" "ps aux | grep crucible-downstairs | grep -v grep"
    exit 0
fi

# Check binary exists
if ! ssh "$HOST" "test -x $CRUCIBLE_BIN"; then
    echo "ERROR: $CRUCIBLE_BIN not found or not executable"
    exit 1
fi

# Check region directory
if ! ssh "$HOST" "test -d $REGION_DIR"; then
    echo "ERROR: $REGION_DIR not found"
    exit 1
fi

if [[ "$1" == "--foreground" ]]; then
    echo "Starting in foreground (Ctrl+C to stop)..."
    ssh -t "$HOST" "$CRUCIBLE_BIN run -p $PORT -d $REGION_DIR"
else
    echo "Starting in background..."
    ssh "$HOST" "nohup $CRUCIBLE_BIN run -p $PORT -d $REGION_DIR > /var/log/crucible/downstairs.log 2>&1 &"
    sleep 2

    # Verify started
    if ssh "$HOST" "pgrep -f crucible-downstairs" 2>/dev/null; then
        echo "Crucible downstairs started successfully"
        echo "Listening on port $PORT"
        echo "Log: /var/log/crucible/downstairs.log"
    else
        echo "ERROR: Failed to start"
        ssh "$HOST" "tail -20 /var/log/crucible/downstairs.log"
        exit 1
    fi
fi
