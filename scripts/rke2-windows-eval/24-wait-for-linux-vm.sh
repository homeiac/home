#!/bin/bash
# Wait for Linux control plane VM to be SSH-accessible
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
LINUX_VM_IP="${LINUX_VM_IP:-192.168.4.202}"
MAX_ATTEMPTS="${1:-60}"

echo "=== Waiting for Linux VM (${LINUX_VM_IP}) ==="
echo ""
echo "Max attempts: ${MAX_ATTEMPTS} (5s intervals)"
echo ""

for i in $(seq 1 $MAX_ATTEMPTS); do
    if ssh root@${PROXMOX_HOST} "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=3 ubuntu@${LINUX_VM_IP} 'uptime'" 2>/dev/null; then
        echo ""
        echo "✓ Linux VM is accessible!"
        exit 0
    fi

    echo "  Attempt $i/$MAX_ATTEMPTS: Waiting..."
    sleep 5
done

echo ""
echo "ERROR: Linux VM did not become accessible after ${MAX_ATTEMPTS} attempts"
exit 1
