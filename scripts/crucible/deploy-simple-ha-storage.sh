#!/opt/homebrew/bin/bash
# Deploy simple HA-ready Crucible storage to all Proxmox hosts
#
# Architecture:
#   - Each host gets ONE NBD device (/dev/nbd0) backed by Crucible
#   - ZFS pool on NBD for caching, compression, snapshots
#   - Proxmox uses it as directory storage at /mnt/crucible-storage
#
# HA comes from Crucible's 3-way replication, not filesystem-level
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRUCIBLE_IP="192.168.4.189"

# Binary location (built with --address flag support)
BINARY_PATH="${1:-/tmp/crucible-nbd-server}"

if [ ! -f "$BINARY_PATH" ]; then
    echo "ERROR: Binary not found at $BINARY_PATH"
    echo "Usage: $0 [path-to-crucible-nbd-server]"
    exit 1
fi

# Host:ports mapping (each host has its own 3 downstairs regions)
declare -A HOSTS=(
    ["pve"]="3820 3821 3822"
    ["still-fawn.maas"]="3830 3831 3832"
    ["pumped-piglet.maas"]="3840 3841 3842"
    ["chief-horse.maas"]="3850 3851 3852"
)

echo "=== Deploying Crucible Storage (Simple HA Model) ==="
echo "Binary: $BINARY_PATH"
echo ""

for host in "${!HOSTS[@]}"; do
    ports=(${HOSTS[$host]})
    echo ""
    echo "=== $host (ports ${ports[*]}) ==="

    # Test connectivity
    if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "root@${host}" "echo 'OK'" 2>/dev/null; then
        echo "  SKIP: Cannot connect to $host"
        continue
    fi

    # Stop existing services
    echo "  Stopping existing services..."
    ssh "root@${host}" "
        systemctl stop crucible-nbd-connect.service 2>/dev/null || true
        systemctl stop crucible-nbd.service 2>/dev/null || true
        pkill -f crucible-nbd-server 2>/dev/null || true
        nbd-client -d /dev/nbd0 2>/dev/null || true
        sleep 1
    "

    # Copy binary
    echo "  Copying binary..."
    ssh "root@${host}" "rm -f /usr/local/bin/crucible-nbd-server"
    scp "$BINARY_PATH" "root@${host}:/usr/local/bin/"
    ssh "root@${host}" "chmod +x /usr/local/bin/crucible-nbd-server"

    # Create wrapper script (timestamp-based gen for HA)
    echo "  Creating wrapper script..."
    ssh "root@${host}" "cat > /usr/local/bin/crucible-nbd-wrapper.sh" << 'WRAPPER'
#!/bin/bash
# Timestamp-based generation for split-brain prevention
# Higher gen wins - enables HA failover
exec /usr/local/bin/crucible-nbd-server "$@" --gen $(date +%s)
WRAPPER
    ssh "root@${host}" "chmod +x /usr/local/bin/crucible-nbd-wrapper.sh"

    # Install nbd-client and zfs
    echo "  Installing dependencies..."
    ssh "root@${host}" "
        apt-get update -qq
        apt-get install -y -qq nbd-client zfsutils-linux 2>/dev/null || apt-get install -y -qq nbd-client
        modprobe nbd max_part=8
        echo 'nbd' > /etc/modules-load.d/nbd.conf
    " 2>/dev/null

    # Create systemd services
    echo "  Creating systemd services..."
    ssh "root@${host}" "cat > /etc/systemd/system/crucible-nbd.service" << EOF
[Unit]
Description=Crucible NBD Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/crucible-nbd-wrapper.sh --target ${CRUCIBLE_IP}:${ports[0]} --target ${CRUCIBLE_IP}:${ports[1]} --target ${CRUCIBLE_IP}:${ports[2]}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    ssh "root@${host}" "cat > /etc/systemd/system/crucible-nbd-connect.service" << 'EOF'
[Unit]
Description=Connect NBD client to Crucible
After=crucible-nbd.service
Requires=crucible-nbd.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/sleep 3
ExecStart=/usr/sbin/nbd-client 127.0.0.1 10809 /dev/nbd0
ExecStop=/usr/sbin/nbd-client -d /dev/nbd0

[Install]
WantedBy=multi-user.target
EOF

    # Create ZFS mount service (only if ZFS is available)
    ssh "root@${host}" "cat > /etc/systemd/system/crucible-zfs-mount.service" << 'EOF'
[Unit]
Description=Mount Crucible ZFS Pool
After=crucible-nbd-connect.service
Requires=crucible-nbd-connect.service

[Service]
Type=oneshot
RemainAfterExit=yes
# Import pool if it exists, or create it
ExecStart=/bin/bash -c 'zpool import crucible-pool 2>/dev/null || (zpool list crucible-pool 2>/dev/null || zpool create -o ashift=12 -O compression=lz4 -O atime=off crucible-pool /dev/nbd0)'
ExecStart=/bin/mkdir -p /mnt/crucible-storage
ExecStart=/bin/bash -c 'mountpoint -q /mnt/crucible-storage || zfs set mountpoint=/mnt/crucible-storage crucible-pool'
ExecStop=/bin/bash -c 'zpool export crucible-pool 2>/dev/null || true'

[Install]
WantedBy=multi-user.target
EOF

    # Reload and enable
    echo "  Starting services..."
    ssh "root@${host}" "
        systemctl daemon-reload
        systemctl enable crucible-nbd.service crucible-nbd-connect.service
        systemctl start crucible-nbd.service
        sleep 3
        systemctl start crucible-nbd-connect.service
        sleep 2
    "

    # Verify
    echo "  Verifying..."
    if ssh "root@${host}" "test -b /dev/nbd0 && lsblk /dev/nbd0 2>/dev/null | head -2"; then
        echo "  SUCCESS: /dev/nbd0 ready"
    else
        echo "  WARNING: /dev/nbd0 not ready - check logs"
    fi
done

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Next steps for each host:"
echo "1. Initialize ZFS (first time only):"
echo "   zpool create -o ashift=12 -O compression=lz4 -O atime=off crucible-pool /dev/nbd0"
echo "   zfs set mountpoint=/mnt/crucible-storage crucible-pool"
echo ""
echo "2. Add to Proxmox storage:"
echo "   pvesm add dir crucible-storage --path /mnt/crucible-storage --content images,vztmpl,iso"
echo ""
echo "3. Enable auto-mount:"
echo "   systemctl enable --now crucible-zfs-mount.service"
