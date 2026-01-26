#!/bin/bash
# Setup NBD client on a Proxmox host - runs ON the host
# Usage: setup-nbd-client.sh CRUCIBLE_IP PORT1 PORT2 PORT3
#
# GENERATION NUMBER:
# Uses $(date +%s) (Unix timestamp) per Oxide's pattern (crucible README line 68).
# This ensures gen is always >= stored value, even after writes/reboots.
# See: https://github.com/oxidecomputer/crucible/blob/main/README.md
set -e

# Configuration
NBD_PORT=10809
NBD_DEVICE="/dev/nbd0"
NBD_MAX_PARTITIONS=8

# Parse arguments
CRUCIBLE_IP="$1"
PORT1="$2"
PORT2="$3"
PORT3="$4"

# Validate arguments
if [[ -z "$CRUCIBLE_IP" || -z "$PORT1" || -z "$PORT2" || -z "$PORT3" ]]; then
    echo "Usage: $0 CRUCIBLE_IP PORT1 PORT2 PORT3" >&2
    echo "Example: $0 192.168.4.189 3820 3821 3822" >&2
    exit 1
fi

log() {
    echo "[$(date '+%H:%M:%S')] $*"
}

stop_existing_services() {
    log "Stopping existing services..."
    systemctl stop crucible-nbd.service 2>/dev/null || true
    systemctl stop crucible-nbd-connect.service 2>/dev/null || true
    pkill -f crucible-nbd-server 2>/dev/null || true
    nbd-client -d "$NBD_DEVICE" 2>/dev/null || true
    sleep 1
}

install_dependencies() {
    log "Installing nbd-client..."
    apt-get update -qq
    apt-get install -y -qq nbd-client
}

configure_nbd_module() {
    log "Loading NBD kernel module..."
    modprobe nbd max_part="$NBD_MAX_PARTITIONS"
    echo "nbd" > /etc/modules-load.d/nbd.conf
}

create_wrapper_script() {
    log "Creating generation wrapper script..."
    cat > /usr/local/bin/crucible-nbd-wrapper.sh << 'WRAPPER'
#!/bin/bash
# Wrapper to start crucible-nbd-server with timestamp-based generation
# Generation MUST be >= stored value. Using timestamp ensures this.
exec /usr/local/bin/crucible-nbd-server "$@" --gen $(date +%s)
WRAPPER
    chmod +x /usr/local/bin/crucible-nbd-wrapper.sh
}

create_systemd_services() {
    log "Creating systemd services..."

    # NBD server service
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

    # NBD client connection service
    cat > /etc/systemd/system/crucible-nbd-connect.service << EOF
[Unit]
Description=Connect NBD client to Crucible
After=crucible-nbd.service
Requires=crucible-nbd.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/sleep 3
ExecStart=/usr/sbin/nbd-client 127.0.0.1 ${NBD_PORT} ${NBD_DEVICE}
ExecStop=/usr/sbin/nbd-client -d ${NBD_DEVICE}

[Install]
WantedBy=multi-user.target
EOF
}

start_services() {
    log "Starting services..."
    systemctl daemon-reload
    systemctl enable crucible-nbd.service crucible-nbd-connect.service

    systemctl start crucible-nbd.service
    sleep 3

    systemctl start crucible-nbd-connect.service
    sleep 2

    # Restart mount unit if it exists (uses systemd-escaped path: - becomes \x2d)
    local mount_unit="mnt-crucible\\x2dstorage.mount"
    if systemctl cat "$mount_unit" &>/dev/null; then
        log "Restarting mount unit..."
        systemctl restart "$mount_unit" || true
    fi
}

verify_setup() {
    log "Verifying setup..."
    echo "=== Result ==="
    lsblk "$NBD_DEVICE"
}

# Main
log "Setting up Crucible NBD: ${CRUCIBLE_IP}:${PORT1},${PORT2},${PORT3}"

stop_existing_services
install_dependencies
configure_nbd_module
create_wrapper_script
create_systemd_services
start_services
verify_setup
