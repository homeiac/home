#!/bin/bash
# Setup 3 Crucible downstairs processes on proper-raptor
# Required for Crucible replication/consensus to work
#
# Usage: ./setup-3-downstairs.sh
#
set -e

HOST="ubuntu@192.168.4.189"
CRUCIBLE_BIN="/home/ubuntu/crucible-downstairs"

echo "=== Setting up 3 Crucible downstairs on proper-raptor ==="

# Check SSH access
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" "echo 'SSH OK'" 2>/dev/null; then
    echo "ERROR: Cannot SSH to $HOST"
    exit 1
fi

# Generate a shared UUID for all 3 regions
UUID=$(uuidgen)
echo "Using UUID: $UUID"

# Copy the setup script to the remote host and execute it there
ssh "$HOST" "cat > /tmp/setup-crucible.sh" << 'REMOTE_SCRIPT'
#!/bin/bash
set -e

CRUCIBLE_BIN="/home/ubuntu/crucible-downstairs"
UUID="$1"

echo "=== Stopping existing downstairs processes ==="
sudo pkill -f crucible-downstairs || true
sleep 2

echo "=== Creating and initializing 3 regions ==="
for i in 0 1 2; do
    DIR="/crucible/downstairs-${i}"
    echo "Setting up region $i at $DIR..."

    sudo mkdir -p "$DIR"
    sudo chown ubuntu:ubuntu "$DIR"

    if [ -f "$DIR/region.json" ]; then
        echo "Region $i already exists, skipping creation"
    else
        echo "Creating region $i with UUID $UUID..."
        "$CRUCIBLE_BIN" create \
            -d "$DIR" \
            --block-size 4096 \
            --extent-size 32768 \
            --extent-count 100 \
            --uuid "$UUID"
    fi
done

echo "=== Creating systemd services ==="
for i in 0 1 2; do
    PORT=$((3810 + i))

    sudo tee /etc/systemd/system/crucible-downstairs-${i}.service > /dev/null << EOF
[Unit]
Description=Crucible Downstairs Instance ${i}
After=network.target zfs-mount.service
Wants=zfs-mount.service

[Service]
Type=simple
User=ubuntu
ExecStart=${CRUCIBLE_BIN} run -p ${PORT} -d /crucible/downstairs-${i}
Restart=always
RestartSec=5
StandardOutput=append:/var/log/crucible/downstairs-${i}.log
StandardError=append:/var/log/crucible/downstairs-${i}.log

[Install]
WantedBy=multi-user.target
EOF
done

echo "=== Creating log directory ==="
sudo mkdir -p /var/log/crucible
sudo chown ubuntu:ubuntu /var/log/crucible

echo "=== Starting services ==="
sudo systemctl daemon-reload
sudo systemctl enable --now crucible-downstairs-0 crucible-downstairs-1 crucible-downstairs-2

sleep 3

echo "=== Verifying services ==="
systemctl status crucible-downstairs-0 crucible-downstairs-1 crucible-downstairs-2 --no-pager | grep -E '(Active:|●)' || true

echo "=== Checking ports ==="
ss -tlnp | grep -E '(3810|3811|3812)' || echo "Ports not yet listening, check logs"

echo "=== Setup complete ==="
REMOTE_SCRIPT

# Make it executable and run it
ssh "$HOST" "chmod +x /tmp/setup-crucible.sh && /tmp/setup-crucible.sh '$UUID'"

echo ""
echo "=== Done ==="
echo "3 Crucible downstairs should be running on ports 3810, 3811, 3812"
echo "UUID: $UUID"
echo ""
echo "Test with: nc -zv 192.168.4.189 3810 3811 3812"
