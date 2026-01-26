#!/opt/homebrew/bin/bash
# Create Crucible VM disk volumes for each Proxmox host
#
# This creates separate Crucible volumes (each with 3 regions) that can be
# attached to VMs on each Proxmox host via NBD.
#
# Architecture:
#   - Each Proxmox host gets its own volume
#   - Each volume has 3 regions on proper-raptor (ports 3820-3822, 3830-3832, etc.)
#   - NBD server on Proxmox host connects to the 3 regions
#
set -e

CRUCIBLE_HOST="ubuntu@192.168.4.189"
CRUCIBLE_BIN="/home/ubuntu/crucible-downstairs"

# Volume definitions: name, base_port
# Each volume uses 3 consecutive ports for its 3 regions
declare -A VOLUMES=(
    ["pve"]=3820
    ["still-fawn"]=3830
    ["pumped-piglet"]=3840
    ["chief-horse"]=3850
    ["fun-bedbug"]=3860
)

# Volume size: 100 extents * 32768 blocks * 4096 bytes = ~12.5 GB per volume
EXTENT_COUNT=100
BLOCK_SIZE=4096
EXTENT_SIZE=32768

echo "=== Creating Crucible VM disk volumes ==="

# Generate the remote script
ssh "$CRUCIBLE_HOST" "cat > /tmp/create-volumes.sh" << 'REMOTE_SCRIPT'
#!/bin/bash
set -e

CRUCIBLE_BIN="/home/ubuntu/crucible-downstairs"
EXTENT_COUNT=$1
BLOCK_SIZE=$2
EXTENT_SIZE=$3
shift 3

# Process each volume
while [ $# -gt 0 ]; do
    NAME="$1"
    BASE_PORT="$2"
    shift 2

    echo ""
    echo "=== Creating volume: $NAME (ports ${BASE_PORT}-$((BASE_PORT+2))) ==="

    # Generate UUID for this volume
    UUID=$(uuidgen)
    echo "UUID: $UUID"

    # Create 3 regions for this volume
    for i in 0 1 2; do
        PORT=$((BASE_PORT + i))
        DIR="/crucible/vm-${NAME}-${i}"

        echo "Creating region $i at $DIR (port $PORT)..."

        sudo mkdir -p "$DIR"
        sudo chown ubuntu:ubuntu "$DIR"

        if [ -f "$DIR/region.json" ]; then
            echo "  Region already exists, skipping"
        else
            "$CRUCIBLE_BIN" create \
                -d "$DIR" \
                --block-size "$BLOCK_SIZE" \
                --extent-size "$EXTENT_SIZE" \
                --extent-count "$EXTENT_COUNT" \
                --uuid "$UUID"
        fi

        # Create systemd service
        sudo tee /etc/systemd/system/crucible-vm-${NAME}-${i}.service > /dev/null << EOF
[Unit]
Description=Crucible VM Disk - ${NAME} Region ${i}
After=network.target zfs-mount.service
Wants=zfs-mount.service

[Service]
Type=simple
User=ubuntu
ExecStart=${CRUCIBLE_BIN} run -p ${PORT} -d ${DIR}
Restart=always
RestartSec=5
StandardOutput=append:/var/log/crucible/vm-${NAME}-${i}.log
StandardError=append:/var/log/crucible/vm-${NAME}-${i}.log

[Install]
WantedBy=multi-user.target
EOF
    done

    # Save volume info
    echo "$UUID" > "/crucible/vm-${NAME}.uuid"
    echo "${BASE_PORT},${BASE_PORT+1},${BASE_PORT+2}" > "/crucible/vm-${NAME}.ports"

    echo "Volume $NAME created with UUID $UUID"
done

# Reload and start all new services
echo ""
echo "=== Starting services ==="
sudo systemctl daemon-reload

# Find and start all vm-* services
for svc in /etc/systemd/system/crucible-vm-*.service; do
    name=$(basename "$svc")
    sudo systemctl enable --now "$name" 2>/dev/null || true
done

sleep 2

echo ""
echo "=== Verifying ==="
ss -tlnp | grep crucible | sort
REMOTE_SCRIPT

chmod +x /tmp/create-volumes.sh 2>/dev/null || true

# Build arguments for the remote script
ARGS="$EXTENT_COUNT $BLOCK_SIZE $EXTENT_SIZE"
for name in "${!VOLUMES[@]}"; do
    ARGS="$ARGS $name ${VOLUMES[$name]}"
done

# Execute
ssh "$CRUCIBLE_HOST" "chmod +x /tmp/create-volumes.sh && /tmp/create-volumes.sh $ARGS"

echo ""
echo "=== Summary ==="
echo ""
echo "Created volumes:"
for name in "${!VOLUMES[@]}"; do
    port=${VOLUMES[$name]}
    echo "  $name: ports ${port}-$((port+2)) -> /crucible/vm-${name}-{0,1,2}"
done
echo ""
echo "To attach a volume to a Proxmox host:"
echo "  1. Copy crucible-nbd-server to the host"
echo "  2. Run: crucible-nbd-server -t 192.168.4.189:PORT1,192.168.4.189:PORT2,192.168.4.189:PORT3"
echo "  3. NBD device appears at /dev/nbd0"
echo "  4. Format (first time): mkfs.ext4 /dev/nbd0"
echo "  5. Mount or attach to VM"
