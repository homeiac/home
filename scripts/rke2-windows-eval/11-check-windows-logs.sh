#!/bin/bash
# Check Windows node RKE2/rancher-wins logs for troubleshooting
set -e

WINDOWS_VM_IP="192.168.4.201"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true
WINDOWS_PASSWORD="${WINDOWS_PASSWORD:-}"

win_ssh() {
    sshpass -p "${WINDOWS_PASSWORD}" ssh -o StrictHostKeyChecking=no Administrator@${WINDOWS_VM_IP} "$@"
}

echo "=== Windows Node RKE2 Troubleshooting ==="
echo ""

echo "=== Services Status ==="
win_ssh "powershell -Command \"Get-Service rancher-wins, rke2 | Format-Table Name, Status, StartType\""
echo ""

echo "=== RKE2 Agent Log (last 50 lines) ==="
win_ssh "powershell -Command \"if (Test-Path 'C:\\var\\log\\rancher\\rke2\\rke2.log') { Get-Content 'C:\\var\\log\\rancher\\rke2\\rke2.log' -Tail 50 } else { Write-Host 'rke2.log not found' }\""
echo ""

echo "=== rancher-wins Log (last 30 lines) ==="
win_ssh "powershell -Command \"if (Test-Path 'C:\\var\\log\\rancher\\wins\\wins.log') { Get-Content 'C:\\var\\log\\rancher\\wins\\wins.log' -Tail 30 } else { Write-Host 'wins.log not found' }\""
echo ""

echo "=== Check if RKE2 binary exists ==="
win_ssh "powershell -Command \"Test-Path 'C:\\usr\\local\\bin\\rke2.exe'\""
echo ""

echo "=== Check rancher-system-agent status ==="
win_ssh "powershell -Command \"Get-Service rancher-system-agent -ErrorAction SilentlyContinue | Format-Table Name, Status, StartType\""
echo ""

echo "=== Windows Event Log (rancher-wins last 10) ==="
win_ssh "powershell -Command \"Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='rancher-wins'} -MaxEvents 10 -ErrorAction SilentlyContinue | Format-List TimeCreated, Message\""
echo ""

echo "=== Network connectivity to control plane ==="
win_ssh "powershell -Command \"Test-NetConnection -ComputerName 192.168.4.202 -Port 9345\""
