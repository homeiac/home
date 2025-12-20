#!/bin/bash
# Clean up Windows node for fresh RKE2 registration
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    source "${SCRIPT_DIR}/.env"
fi

WINDOWS_VM_IP="${WINDOWS_VM_IP:-192.168.4.201}"
WINDOWS_USER="${WINDOWS_USER:-Administrator}"
WINDOWS_PASSWORD="${WINDOWS_PASSWORD}"

if [[ -z "$WINDOWS_PASSWORD" ]]; then
    echo "ERROR: WINDOWS_PASSWORD not set. Create .env file from .env.example"
    exit 1
fi

win_ssh() {
    sshpass -p "${WINDOWS_PASSWORD}" ssh -o StrictHostKeyChecking=no ${WINDOWS_USER}@${WINDOWS_VM_IP} "$@"
}

echo "=== Cleaning Up Windows Node for Fresh Registration ==="
echo ""

echo "Stopping services..."
win_ssh "sc stop rke2 2>nul & sc stop rancher-wins 2>nul & sc stop rancher-system-agent 2>nul & echo done" || true
sleep 5

echo ""
echo "Deleting services..."
win_ssh "sc delete rke2 2>nul & sc delete rancher-wins 2>nul & sc delete rancher-system-agent 2>nul & echo done" || true

echo ""
echo "Removing Rancher/RKE2 directories..."
win_ssh "rmdir /s /q C:\\var\\lib\\rancher 2>nul & echo done" || true
win_ssh "rmdir /s /q C:\\etc\\rancher 2>nul & echo done" || true
win_ssh "rmdir /s /q C:\\usr\\local 2>nul & echo done" || true

echo ""
echo "=== Cleanup Complete ==="
echo "Now re-register from Rancher UI with a fresh token."
