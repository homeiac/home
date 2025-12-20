#!/bin/bash
# Fix IPv6 in RKE2 config with proper backup
# Copies config locally, makes backup, applies fix
set -e

WINDOWS_VM_IP="192.168.4.201"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true
WINDOWS_PASSWORD="${WINDOWS_PASSWORD:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/configs"
BACKUP_DIR="${SCRIPT_DIR}/backups"

mkdir -p "$CONFIG_DIR" "$BACKUP_DIR"

win_ssh() {
    sshpass -p "${WINDOWS_PASSWORD}" ssh -o StrictHostKeyChecking=no Administrator@${WINDOWS_VM_IP} "$@"
}

echo "=== Fixing IPv6 in RKE2 Config (with backup) ==="
echo ""

# Backup original config
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
echo "Backing up original config..."
win_ssh "type C:\\etc\\rancher\\rke2\\config.yaml.d\\50-rancher.yaml" > "${BACKUP_DIR}/50-rancher.yaml.${TIMESTAMP}.bak"
win_ssh "type C:\\var\\lib\\rancher\\rke2\\agent\\etc\\rke2-agent-load-balancer.json" > "${BACKUP_DIR}/rke2-agent-load-balancer.json.${TIMESTAMP}.bak" 2>/dev/null || true
echo "Backups saved to: ${BACKUP_DIR}/"

# Create fixed config locally
echo ""
echo "Creating fixed config..."
cat > "${CONFIG_DIR}/50-rancher.yaml" << 'EOF'
{
  "node-label": [
    "cattle.io/os=windows",
    "rke.cattle.io/machine=ccc0ac00-4143-446d-a3cc-44c6c02a84fc"
  ],
  "private-registry": "/etc/rancher/rke2/registries.yaml",
  "protect-kernel-defaults": false,
  "server": "https://192.168.4.202:9345",
  "token": "zvmd8cfv4dgp2ghg6skvx7d5vrczgzv7kt9tf42xtt596r28hrgkq2"
}
EOF

cat > "${CONFIG_DIR}/rke2-agent-load-balancer.json" << 'EOF'
{"ServerURL": "https://192.168.4.202:9345", "ServerAddresses": []}
EOF

echo "Fixed configs created in: ${CONFIG_DIR}/"
cat "${CONFIG_DIR}/50-rancher.yaml"

# Stop services
echo ""
echo "Stopping services..."
win_ssh "sc stop rke2" 2>/dev/null || true
win_ssh "sc stop rancher-wins" 2>/dev/null || true
sleep 5

# Copy fixed configs
echo ""
echo "Applying fixed config..."
sshpass -p "${WINDOWS_PASSWORD}" scp -o StrictHostKeyChecking=no "${CONFIG_DIR}/50-rancher.yaml" "Administrator@${WINDOWS_VM_IP}:C:/etc/rancher/rke2/config.yaml.d/50-rancher.yaml"
sshpass -p "${WINDOWS_PASSWORD}" scp -o StrictHostKeyChecking=no "${CONFIG_DIR}/rke2-agent-load-balancer.json" "Administrator@${WINDOWS_VM_IP}:C:/var/lib/rancher/rke2/agent/etc/rke2-agent-load-balancer.json"

# Verify
echo ""
echo "Verifying..."
win_ssh "type C:\\etc\\rancher\\rke2\\config.yaml.d\\50-rancher.yaml"

# Start services
echo ""
echo "Starting services..."
win_ssh "sc start rancher-wins"
sleep 3
win_ssh "sc start rke2"

echo ""
echo "=== Done ==="
echo "Backups: ${BACKUP_DIR}/"
echo "Monitor with: ./11-check-windows-logs.sh"
