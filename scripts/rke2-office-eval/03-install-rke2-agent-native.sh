#!/bin/bash
# Install RKE2 agent directly on Proxmox host (native, no VM)
# Run this ON the Proxmox host
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
RANCHER_URL="${RANCHER_URL:-}"
CLUSTER_TOKEN="${CLUSTER_TOKEN:-}"
NODE_NAME="${NODE_NAME:-$(hostname)}"

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Install RKE2 agent natively on this Proxmox host.

Options:
  --rancher-url URL   Rancher server URL (e.g., https://rancher.office.local)
  --token TOKEN       Cluster registration token from Rancher
  --node-name NAME    Node name (default: hostname)
  --uninstall         Remove RKE2 from this host
  -h, --help          Show this help

Example:
  $0 --rancher-url https://rancher.office.local \\
     --token "xxxxxx::yyyyyy"

To get the token:
  1. Rancher UI → Cluster → Registration
  2. Copy the token from the curl command

EOF
    exit 0
}

UNINSTALL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --rancher-url) RANCHER_URL="$2"; shift 2 ;;
        --token) CLUSTER_TOKEN="$2"; shift 2 ;;
        --node-name) NODE_NAME="$2"; shift 2 ;;
        --uninstall) UNINSTALL=true; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

# Check we're running on Proxmox
if ! command -v pvesh &>/dev/null; then
    echo "ERROR: This script must run ON a Proxmox host"
    echo "pvesh command not found"
    exit 1
fi

if $UNINSTALL; then
    echo "=== Uninstalling RKE2 Agent ==="

    if [[ -f /usr/local/bin/rke2-uninstall.sh ]]; then
        /usr/local/bin/rke2-uninstall.sh
        echo "RKE2 uninstalled successfully"
    else
        echo "RKE2 uninstall script not found - may not be installed"
    fi

    # Clean up config
    rm -rf /etc/rancher/rke2
    rm -rf /var/lib/rancher/rke2

    echo "Cleanup complete"
    exit 0
fi

# Validate required parameters
if [[ -z "$RANCHER_URL" || -z "$CLUSTER_TOKEN" ]]; then
    echo "ERROR: Missing required parameters"
    echo ""
    echo "Required: --rancher-url, --token"
    echo ""
    usage
fi

echo "=== Installing RKE2 Agent on Proxmox Host ==="
echo ""
echo "Host:        $(hostname)"
echo "Rancher URL: ${RANCHER_URL}"
echo "Node Name:   ${NODE_NAME}"
echo ""

# Check system requirements
echo "=== Checking Prerequisites ==="

# Memory check
TOTAL_MEM_GB=$(free -g | awk '/^Mem:/{print $2}')
echo "Total RAM: ${TOTAL_MEM_GB}GB"
if [[ $TOTAL_MEM_GB -lt 8 ]]; then
    echo "WARNING: Less than 8GB RAM. RKE2 may struggle."
fi

# Disk check
ROOT_FREE_GB=$(df -BG / | awk 'NR==2{print $4}' | tr -d 'G')
echo "Root free: ${ROOT_FREE_GB}GB"
if [[ $ROOT_FREE_GB -lt 20 ]]; then
    echo "WARNING: Less than 20GB free. Consider expanding."
fi

# Check for container runtime conflicts
if systemctl is-active --quiet docker; then
    echo "WARNING: Docker is running. RKE2 uses containerd."
    echo "They can coexist but may cause confusion."
fi

echo ""
echo "=== Installing RKE2 ==="

# Create config directory
mkdir -p /etc/rancher/rke2

# Write config
cat > /etc/rancher/rke2/config.yaml <<EOF
server: ${RANCHER_URL}
token: ${CLUSTER_TOKEN}
node-name: ${NODE_NAME}
# Taint this node so normal workloads don't schedule here
# Remove if you want workloads on the Proxmox host
node-taint:
  - "node-role.kubernetes.io/proxmox=true:NoSchedule"
EOF

echo "Config written to /etc/rancher/rke2/config.yaml"

# Download and install RKE2
echo ""
echo "Downloading RKE2..."
curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" sh -

echo ""
echo "Enabling and starting RKE2 agent..."
systemctl enable rke2-agent.service
systemctl start rke2-agent.service

echo ""
echo "=== Waiting for Agent to Join ==="
echo "This may take 1-2 minutes..."

for i in {1..60}; do
    if systemctl is-active --quiet rke2-agent.service; then
        echo "RKE2 agent service is running"
        break
    fi
    echo -n "."
    sleep 2
done

echo ""
echo "=== Agent Status ==="
systemctl status rke2-agent.service --no-pager || true

echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Check Rancher UI - node should appear in cluster"
echo "2. Verify with: journalctl -u rke2-agent -f"
echo "3. To untaint for workloads:"
echo "   kubectl taint nodes ${NODE_NAME} node-role.kubernetes.io/proxmox:NoSchedule-"
echo ""
echo "To uninstall: $0 --uninstall"
