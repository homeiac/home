#!/bin/bash
set -euo pipefail

echo "Waiting for k3s-vm-still-fawn to come back online..."
for i in {1..30}; do
    if ssh -o ConnectTimeout=5 ubuntu@k3s-vm-still-fawn "uptime" 2>/dev/null; then
        echo "VM is online."
        exit 0
    fi
    echo "Attempt $i/30 - waiting 5s..."
    sleep 5
done
echo "ERROR: VM did not come back online in time."
exit 1
