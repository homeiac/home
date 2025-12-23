#!/bin/bash
# Register Windows worker node to RKE2 cluster via Rancher
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment if exists
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    source "${SCRIPT_DIR}/.env"
fi

# Configuration
WINDOWS_IP="${WINDOWS_IP:-}"
WINDOWS_USER="${WINDOWS_USER:-Administrator}"
WINDOWS_PASSWORD="${WINDOWS_PASSWORD:-}"
RANCHER_URL="${RANCHER_URL:-}"
RANCHER_TOKEN="${RANCHER_TOKEN:-}"
RANCHER_CA_CHECKSUM="${RANCHER_CA_CHECKSUM:-}"

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Register Windows VM as RKE2 worker node via Rancher.

Options:
  --windows-ip IP       Windows VM IP address
  --user USER           Windows user (default: Administrator)
  --password PASS       Windows password
  --rancher-url URL     Rancher server URL
  --token TOKEN         Registration token from Rancher
  --checksum HASH       CA checksum from Rancher
  -h, --help            Show this help

Environment file (.env):
  Create .env from .env.example with credentials

To get token and checksum:
  1. Rancher UI → Cluster → Registration
  2. Select "Windows" tab
  3. Copy values from the PowerShell command

Example:
  $0 --windows-ip 192.168.1.201 \\
     --password "YourPassword" \\
     --rancher-url https://rancher.office.local \\
     --token "xxxxxx::yyyyyy" \\
     --checksum "abc123..."

EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --windows-ip) WINDOWS_IP="$2"; shift 2 ;;
        --user) WINDOWS_USER="$2"; shift 2 ;;
        --password) WINDOWS_PASSWORD="$2"; shift 2 ;;
        --rancher-url) RANCHER_URL="$2"; shift 2 ;;
        --token) RANCHER_TOKEN="$2"; shift 2 ;;
        --checksum) RANCHER_CA_CHECKSUM="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

# Validate required parameters
missing=()
[[ -z "$WINDOWS_IP" ]] && missing+=("--windows-ip")
[[ -z "$WINDOWS_PASSWORD" ]] && missing+=("--password")
[[ -z "$RANCHER_URL" ]] && missing+=("--rancher-url")
[[ -z "$RANCHER_TOKEN" ]] && missing+=("--token")
[[ -z "$RANCHER_CA_CHECKSUM" ]] && missing+=("--checksum")

if [[ ${#missing[@]} -gt 0 ]]; then
    echo "ERROR: Missing required parameters: ${missing[*]}"
    echo ""
    usage
fi

# Check for sshpass
if ! command -v sshpass &>/dev/null; then
    echo "ERROR: sshpass not installed"
    echo "Install with: brew install hudochenkov/sshpass/sshpass"
    exit 1
fi

win_ssh() {
    sshpass -p "${WINDOWS_PASSWORD}" ssh -o StrictHostKeyChecking=no "${WINDOWS_USER}@${WINDOWS_IP}" "$@"
}

echo "=== Registering Windows Worker Node ==="
echo ""
echo "Windows VM: ${WINDOWS_IP}"
echo "Rancher:    ${RANCHER_URL}"
echo ""

# Check SSH connectivity
echo "Checking SSH connectivity..."
if ! win_ssh "hostname" 2>/dev/null; then
    echo "ERROR: Cannot SSH to ${WINDOWS_USER}@${WINDOWS_IP}"
    echo ""
    echo "Ensure:"
    echo "  1. OpenSSH Server is installed on Windows"
    echo "  2. Firewall allows port 22"
    echo "  3. Password is correct"
    exit 1
fi
echo "SSH OK: $(win_ssh 'hostname')"
echo ""

# Install Chocolatey (needed for some dependencies)
echo "Installing Chocolatey..."
win_ssh "powershell -Command \"Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))\"" 2>/dev/null || true

echo ""
echo "Running RKE2 Windows registration..."
echo "Token: ${RANCHER_TOKEN:0:15}..."
echo "Checksum: ${RANCHER_CA_CHECKSUM:0:15}..."
echo ""

# Run the Rancher Windows registration
win_ssh "powershell -Command \"curl.exe --insecure -fL ${RANCHER_URL}/wins-agent-install.ps1 -o C:\\install.ps1; Set-ExecutionPolicy Bypass -Scope Process -Force; C:\\install.ps1 -Server '${RANCHER_URL}' -Label 'cattle.io/os=windows' -Token '${RANCHER_TOKEN}' -Worker -CaChecksum '${RANCHER_CA_CHECKSUM}'\""

echo ""
echo "=== Registration Complete ==="
echo ""
echo "Check Rancher UI for Windows node status"
echo "Node should appear in cluster within 2-5 minutes"
echo ""
echo "To verify on Windows VM:"
echo "  Get-Service rancher-wins"
echo "  Get-Service rke2"
