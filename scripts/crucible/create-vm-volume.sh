#!/bin/bash
# Create a per-VM Crucible volume for HA-ready storage
#
# Usage: create-vm-volume.sh <VMID> [SIZE_GB]
#
# Creates 3 downstairs regions for a specific VM on proper-raptor.
# Any Proxmox host can connect to this volume, enabling HA failover.
#
# Port allocation scheme:
#   VM-200: 3900, 3901, 3902
#   VM-201: 3910, 3911, 3912
#   VM-2XX: 3900 + ((VMID - 200) * 10), +1, +2
#
# Capacity: VMIDs 200-299 = 100 VMs (ports 3900-4892)
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
CRUCIBLE_IP="192.168.4.189"
CRUCIBLE_HOST="ubuntu@${CRUCIBLE_IP}"
CRUCIBLE_BIN="/home/ubuntu/crucible-downstairs"
BASE_PORT=3900
MIN_VMID=200
MAX_VMID=299

# Volume parameters
BLOCK_SIZE=4096
EXTENT_SIZE=32768
DEFAULT_EXTENT_COUNT=100  # ~12.5 GB

usage() {
    echo "Usage: $0 <VMID> [SIZE_GB]"
    echo ""
    echo "Arguments:"
    echo "  VMID     VM ID (${MIN_VMID}-${MAX_VMID})"
    echo "  SIZE_GB  Optional volume size in GB (default: 12.5 GB)"
    echo ""
    echo "Examples:"
    echo "  $0 200           # Create 12.5GB volume for VM-200"
    echo "  $0 205 50        # Create 50GB volume for VM-205"
    exit 1
}

# Parse arguments
if [ $# -lt 1 ]; then
    usage
fi

VMID=$1
SIZE_GB=${2:-""}

# Validate VMID
if ! [[ "$VMID" =~ ^[0-9]+$ ]]; then
    echo "ERROR: VMID must be a number"
    exit 1
fi

if [ "$VMID" -lt "$MIN_VMID" ] || [ "$VMID" -gt "$MAX_VMID" ]; then
    echo "ERROR: VMID must be between ${MIN_VMID} and ${MAX_VMID}"
    echo "       This ensures unique port allocation (3900-4892)"
    exit 1
fi

# Calculate ports
PORT_OFFSET=$((VMID - MIN_VMID))
PORT1=$((BASE_PORT + PORT_OFFSET * 10))
PORT2=$((PORT1 + 1))
PORT3=$((PORT1 + 2))

# Calculate extent count from size if specified
if [ -n "$SIZE_GB" ]; then
    # extent_count * extent_size * block_size = total_bytes
    # extent_count = total_bytes / (extent_size * block_size)
    # 1 GB = 1073741824 bytes
    # block_size=4096, extent_size=32768 -> bytes per extent = 134217728 (~128MB)
    BYTES_PER_EXTENT=$((BLOCK_SIZE * EXTENT_SIZE))
    TOTAL_BYTES=$((SIZE_GB * 1073741824))
    EXTENT_COUNT=$((TOTAL_BYTES / BYTES_PER_EXTENT))
    if [ "$EXTENT_COUNT" -lt 1 ]; then
        EXTENT_COUNT=1
    fi
else
    EXTENT_COUNT=$DEFAULT_EXTENT_COUNT
fi

# Calculate actual size for display
ACTUAL_SIZE_BYTES=$((EXTENT_COUNT * EXTENT_SIZE * BLOCK_SIZE))
ACTUAL_SIZE_GB=$(echo "scale=2; $ACTUAL_SIZE_BYTES / 1073741824" | bc)

echo "=== Creating Crucible Volume for VM-${VMID} ==="
echo "Crucible host: ${CRUCIBLE_IP}"
echo "Ports: ${PORT1}, ${PORT2}, ${PORT3}"
echo "Size: ~${ACTUAL_SIZE_GB} GB (${EXTENT_COUNT} extents)"
echo ""

# Check SSH access
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$CRUCIBLE_HOST" "echo 'SSH OK'" 2>/dev/null; then
    echo "ERROR: Cannot SSH to $CRUCIBLE_HOST"
    echo "       Make sure proper-raptor is accessible"
    exit 1
fi

# Generate UUID for this volume
UUID=$(uuidgen)
echo "UUID: $UUID"
echo ""

# Create the volume on proper-raptor
ssh "$CRUCIBLE_HOST" "cat > /tmp/create-vm-volume.sh" << 'REMOTE_SCRIPT'
#!/bin/bash
set -e

CRUCIBLE_BIN="$1"
VMID="$2"
UUID="$3"
PORT1="$4"
PORT2="$5"
PORT3="$6"
BLOCK_SIZE="$7"
EXTENT_SIZE="$8"
EXTENT_COUNT="$9"

echo "Creating 3 regions for VM-${VMID}..."

# Create 3 regions with the SAME UUID (required for quorum)
for i in 0 1 2; do
    PORT=$((PORT1 + i))
    DIR="/crucible/vm-${VMID}-${i}"

    echo "  Region $i: $DIR (port $PORT)"

    sudo mkdir -p "$DIR"
    sudo chown ubuntu:ubuntu "$DIR"

    if [ -f "$DIR/region.json" ]; then
        echo "    Region already exists, skipping"
    else
        "$CRUCIBLE_BIN" create \
            -d "$DIR" \
            --block-size "$BLOCK_SIZE" \
            --extent-size "$EXTENT_SIZE" \
            --extent-count "$EXTENT_COUNT" \
            --uuid "$UUID"
    fi

    # Create systemd service for this region
    sudo tee /etc/systemd/system/crucible-vm-${VMID}-${i}.service > /dev/null << EOF
[Unit]
Description=Crucible VM-${VMID} Downstairs Region ${i}
After=network.target zfs-mount.service
Wants=zfs-mount.service

[Service]
Type=simple
User=ubuntu
ExecStart=${CRUCIBLE_BIN} run -p ${PORT} -d ${DIR}
Restart=always
RestartSec=5
StandardOutput=append:/var/log/crucible/vm-${VMID}-${i}.log
StandardError=append:/var/log/crucible/vm-${VMID}-${i}.log

[Install]
WantedBy=multi-user.target
EOF
done

# Ensure log directory exists
sudo mkdir -p /var/log/crucible
sudo chown ubuntu:ubuntu /var/log/crucible

# Save volume metadata
sudo mkdir -p /crucible/meta
echo "$UUID" | sudo tee /crucible/meta/vm-${VMID}.uuid > /dev/null
echo "${PORT1},${PORT2},${PORT3}" | sudo tee /crucible/meta/vm-${VMID}.ports > /dev/null

# Reload systemd and start services
echo ""
echo "Starting downstairs services..."
sudo systemctl daemon-reload
for i in 0 1 2; do
    sudo systemctl enable --now crucible-vm-${VMID}-${i}.service
done

sleep 2

# Verify services are running
echo ""
echo "Verifying..."
for i in 0 1 2; do
    PORT=$((PORT1 + i))
    if ss -tlnp | grep -q ":${PORT}"; then
        echo "  Port $PORT: OK"
    else
        echo "  Port $PORT: FAILED (check logs at /var/log/crucible/vm-${VMID}-${i}.log)"
    fi
done

echo ""
echo "Volume created successfully!"
REMOTE_SCRIPT

# Execute the remote script
ssh "$CRUCIBLE_HOST" "chmod +x /tmp/create-vm-volume.sh && /tmp/create-vm-volume.sh \
    '$CRUCIBLE_BIN' '$VMID' '$UUID' '$PORT1' '$PORT2' '$PORT3' \
    '$BLOCK_SIZE' '$EXTENT_SIZE' '$EXTENT_COUNT'"

echo ""
echo "=== Volume Summary ==="
echo "VM ID:     ${VMID}"
echo "UUID:      ${UUID}"
echo "Ports:     ${PORT1}, ${PORT2}, ${PORT3}"
echo "Size:      ~${ACTUAL_SIZE_GB} GB"
echo ""
echo "To connect from any Proxmox host:"
echo "  systemctl start crucible-vm@${VMID}.service"
echo "  systemctl start crucible-vm-connect@${VMID}.service"
echo "  lsblk /dev/nbd\$((${VMID} - ${MIN_VMID}))"
