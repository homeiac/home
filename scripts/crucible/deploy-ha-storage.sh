#!/bin/bash
# Deploy HA-ready Crucible storage to all Proxmox hosts
#
# This script deploys:
#   1. crucible-nbd-server binary
#   2. crucible-nbd-wrapper.sh (timestamp generation)
#   3. crucible-vm@.service template
#   4. crucible-vm-connect@.service template
#   5. HA hook script
#
# After deployment, any host can start any VM using Crucible storage.
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CRUCIBLE_IP="192.168.4.189"
CRUCIBLE_HOST="ubuntu@${CRUCIBLE_IP}"

# Proxmox hosts to deploy to
HOSTS=(
    "pve"
    "still-fawn.maas"
    "pumped-piglet.maas"
    "chief-horse.maas"
)

echo "=== Deploying HA-Ready Crucible Storage ==="
echo ""

# Step 1: Get the crucible-nbd-server binary from proper-raptor
echo "=== Step 1: Fetching crucible-nbd-server binary ==="
if [ ! -f /tmp/crucible-nbd-server ] || [ "$1" == "--force" ]; then
    scp "${CRUCIBLE_HOST}:/home/ubuntu/crucible-nbd-server" /tmp/crucible-nbd-server
    echo "Downloaded crucible-nbd-server"
else
    echo "Using cached /tmp/crucible-nbd-server (use --force to re-download)"
fi

# Step 2: Deploy to each host
for host in "${HOSTS[@]}"; do
    echo ""
    echo "=== Deploying to $host ==="

    # Test connectivity
    if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "root@${host}" "echo 'OK'" 2>/dev/null; then
        echo "  SKIP: Cannot connect to $host"
        continue
    fi

    # Copy binary
    echo "  Copying crucible-nbd-server..."
    ssh "root@${host}" "rm -f /usr/local/bin/crucible-nbd-server"
    scp /tmp/crucible-nbd-server "root@${host}:/usr/local/bin/"
    ssh "root@${host}" "chmod +x /usr/local/bin/crucible-nbd-server"

    # Create wrapper script (generates timestamp-based gen at runtime)
    echo "  Creating wrapper script..."
    ssh "root@${host}" "cat > /usr/local/bin/crucible-nbd-wrapper.sh" << 'WRAPPER'
#!/bin/bash
# Wrapper to start crucible-nbd-server with timestamp-based generation
# Generation MUST be >= stored value. Using timestamp ensures this after reboots/failovers.
# This is critical for HA: the new host always gets a higher gen than the old one.
exec /usr/local/bin/crucible-nbd-server "$@" --gen $(date +%s)
WRAPPER
    ssh "root@${host}" "chmod +x /usr/local/bin/crucible-nbd-wrapper.sh"

    # Copy systemd templates
    echo "  Installing systemd templates..."
    scp "${SCRIPT_DIR}/templates/crucible-vm@.service" "root@${host}:/etc/systemd/system/"
    scp "${SCRIPT_DIR}/templates/crucible-vm-connect@.service" "root@${host}:/etc/systemd/system/"

    # Install NBD client if needed
    echo "  Ensuring nbd-client is installed..."
    ssh "root@${host}" "apt-get update -qq && apt-get install -y -qq nbd-client" 2>/dev/null || true

    # Load NBD module
    echo "  Loading NBD kernel module..."
    ssh "root@${host}" "modprobe nbd max_part=8; echo 'nbd' > /etc/modules-load.d/nbd.conf"

    # Reload systemd
    echo "  Reloading systemd..."
    ssh "root@${host}" "systemctl daemon-reload"

    # Create HA hooks directory if it doesn't exist
    echo "  Installing HA hook..."
    ssh "root@${host}" "mkdir -p /var/lib/pve-cluster/hooks"
    scp "${SCRIPT_DIR}/ha-hook.sh" "root@${host}:/var/lib/pve-cluster/hooks/crucible-storage.sh"
    ssh "root@${host}" "chmod +x /var/lib/pve-cluster/hooks/crucible-storage.sh"

    echo "  Done: $host"
done

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Per-VM services are now available on all hosts:"
echo "  systemctl start crucible-vm@<VMID>.service      # Start NBD server"
echo "  systemctl start crucible-vm-connect@<VMID>.service  # Connect device"
echo ""
echo "To create a new VM volume on proper-raptor:"
echo "  ./scripts/crucible/create-vm-volume.sh <VMID> [SIZE_GB]"
echo ""
echo "VMID range: 200-299 (ports 3900-4892)"
echo ""
echo "Example workflow:"
echo "  1. Create volume:  ./scripts/crucible/create-vm-volume.sh 200"
echo "  2. Connect on pve: ssh root@pve 'systemctl start crucible-vm@200 crucible-vm-connect@200'"
echo "  3. Format disk:    ssh root@pve 'mkfs.ext4 /dev/nbd0'"
echo "  4. Use in VM:      Proxmox can use /dev/nbd0 as VM disk"
