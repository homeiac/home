#!/bin/bash
# Setup NBD client on a Proxmox host - runs ON the host
# Usage: setup-nbd-client.sh CRUCIBLE_IP PORT1 PORT2 PORT3
#
# GENERATION NUMBER:
# Uses $(date +%s) (Unix timestamp) per Oxide's pattern (crucible README line 68).
# This ensures gen is always >= stored value, even after writes/reboots.
# See: https://github.com/oxidecomputer/crucible/blob/main/README.md
set -e

CRUCIBLE_IP=$1
PORT1=$2
PORT2=$3
PORT3=$4

echo "Setting up Crucible NBD: ${CRUCIBLE_IP}:${PORT1},${PORT2},${PORT3}"

# Install nbd-client
apt-get update -qq
apt-get install -y -qq nbd-client

# Load nbd module
modprobe nbd max_part=8
echo "nbd" > /etc/modules-load.d/nbd.conf

# Stop existing
systemctl stop crucible-nbd.service 2>/dev/null || true
systemctl stop crucible-nbd-connect.service 2>/dev/null || true
pkill -f crucible-nbd-server 2>/dev/null || true
nbd-client -d /dev/nbd0 2>/dev/null || true
sleep 1

# Create wrapper script that generates gen at runtime
cat > /usr/local/bin/crucible-nbd-wrapper.sh << 'WRAPPER'
#!/bin/bash
# Wrapper to start crucible-nbd-server with timestamp-based generation
# Generation MUST be >= stored value. Using timestamp ensures this.
exec /usr/local/bin/crucible-nbd-server "$@" --gen $(date +%s)
WRAPPER
chmod +x /usr/local/bin/crucible-nbd-wrapper.sh

# Create crucible-nbd service (uses wrapper for dynamic gen)
cat > /etc/systemd/system/crucible-nbd.service << EOF
[Unit]
Description=Crucible NBD Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/crucible-nbd-wrapper.sh --target ${CRUCIBLE_IP}:${PORT1} --target ${CRUCIBLE_IP}:${PORT2} --target ${CRUCIBLE_IP}:${PORT3}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create nbd-connect service
cat > /etc/systemd/system/crucible-nbd-connect.service << EOF
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

# Start
systemctl daemon-reload
systemctl enable crucible-nbd.service crucible-nbd-connect.service
systemctl start crucible-nbd.service
sleep 3
systemctl start crucible-nbd-connect.service
sleep 2

# Verify
echo "=== Result ==="
lsblk /dev/nbd0
