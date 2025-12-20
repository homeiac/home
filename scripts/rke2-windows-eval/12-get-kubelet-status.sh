#!/bin/bash
# Get kubelet and RKE2 status from Windows node
set -e

WINDOWS_VM_IP="192.168.4.201"
WINDOWS_PASSWORD="REDACTED"

win_ssh() {
    sshpass -p "${WINDOWS_PASSWORD}" ssh -o StrictHostKeyChecking=no Administrator@${WINDOWS_VM_IP} "$@"
}

echo "=== Kubelet Status ==="
win_ssh "powershell -Command \"Get-Process kubelet -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, StartTime\""
echo ""

echo "=== RKE2 Service Details ==="
win_ssh "sc query rke2"
echo ""

echo "=== All RKE2-related processes ==="
win_ssh "tasklist | findstr /i \"rke2 kubelet containerd\""
echo ""

echo "=== C:\\usr\\local\\bin contents ==="
win_ssh "dir C:\\usr\\local\\bin"
echo ""

echo "=== Network connectivity to control plane 9345 ==="
win_ssh "powershell -Command \"Test-NetConnection -ComputerName 192.168.4.202 -Port 9345 | Select-Object ComputerName, RemotePort, TcpTestSucceeded\""
echo ""

echo "=== Network connectivity to control plane 6443 ==="
win_ssh "powershell -Command \"Test-NetConnection -ComputerName 192.168.4.202 -Port 6443 | Select-Object ComputerName, RemotePort, TcpTestSucceeded\""
