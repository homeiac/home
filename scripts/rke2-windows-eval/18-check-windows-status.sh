#!/bin/bash
# Check Windows node registration status
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

echo "=== Windows Node Status ==="
echo ""

echo "=== Services Status ==="
win_ssh "sc query rke2 2>nul | findstr STATE" || echo "rke2 service not installed"
win_ssh "sc query rancher-wins 2>nul | findstr STATE" || echo "rancher-wins not installed"
echo ""

echo "=== RKE2 Config (server address) ==="
win_ssh "type C:\\etc\\rancher\\rke2\\config.yaml.d\\50-rancher.yaml 2>nul | findstr server" || echo "No config yet"
echo ""

echo "=== Load Balancer Config ==="
win_ssh "type C:\\var\\lib\\rancher\\rke2\\agent\\etc\\rke2-agent-load-balancer.json 2>nul" || echo "No LB config yet"
echo ""

echo "=== Recent RKE2 Events ==="
win_ssh "powershell -Command \"Get-EventLog -LogName Application -Source 'rke2' -Newest 5 2>\\$null | ForEach-Object { Write-Host \\$_.TimeGenerated \\$_.EntryType; Write-Host \\$_.ReplacementStrings[0]; Write-Host '' }\""
echo ""

echo "=== Running Processes ==="
win_ssh "tasklist | findstr /i \"rke2 kubelet containerd\""
