#!/bin/bash
# Register Windows worker node to RKE2 cluster via Rancher
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

echo "=== Registering Windows Worker Node ==="
echo ""

# Check SSH connectivity
echo "Checking SSH connectivity to Windows VM..."
if ! win_ssh "hostname" 2>/dev/null; then
    echo "ERROR: Cannot SSH to Administrator@${WINDOWS_VM_IP}"
    exit 1
fi
echo "SSH OK"
echo ""

# Install Chocolatey first
echo "Installing Chocolatey..."
win_ssh "powershell -Command \"Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))\""

# Get registration tokens from .env
RANCHER_TOKEN="${RANCHER_TOKEN:-UPDATE_ME}"
RANCHER_CA_CHECKSUM="${RANCHER_CA_CHECKSUM:-UPDATE_ME}"

if [[ "$RANCHER_TOKEN" == "UPDATE_ME" ]]; then
    echo "ERROR: RANCHER_TOKEN not set in .env"
    echo "Get the token from Rancher UI Windows registration command"
    exit 1
fi

echo ""
echo "Running RKE2 Windows registration..."
echo "Token: ${RANCHER_TOKEN:0:10}..."
echo "Checksum: ${RANCHER_CA_CHECKSUM:0:10}..."
echo ""

win_ssh "powershell -Command \"curl.exe --insecure -fL https://rancher.homelab/wins-agent-install.ps1 -o install.ps1; Set-ExecutionPolicy Bypass -Scope Process -Force; ./install.ps1 -Server https://rancher.homelab -Label 'cattle.io/os=windows' -Token ${RANCHER_TOKEN} -Worker -CaChecksum ${RANCHER_CA_CHECKSUM}\""

echo ""
echo "=== Registration Complete ==="
echo "Check Rancher UI for Windows node status"
