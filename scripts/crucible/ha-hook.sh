#!/bin/bash
# Proxmox HA Hook for Crucible Storage
#
# This hook is called by the Proxmox HA manager when VMs start/stop/migrate.
# It manages the Crucible NBD connection for per-VM volumes.
#
# Install location: /etc/pve/ha/resources.d/ (cluster-wide)
#                   or /var/lib/pve-cluster/hooks/ (node-specific)
#
# Called with: $0 <action> <vmid> [target_node]
#   action: start, stop, migrate
#   vmid: VM ID (e.g., 200)
#   target_node: (migrate only) destination node
#
# For Crucible HA storage, VMs must use VMID 200-299.
#
set -e

ACTION="$1"
VMID="$2"
TARGET_NODE="$3"

# Only handle VMs in our range
MIN_VMID=200
MAX_VMID=299

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [crucible-ha] $*" | tee -a /var/log/crucible-ha.log
}

# Check if this VM uses Crucible storage (VMID in range)
if [ "$VMID" -lt "$MIN_VMID" ] || [ "$VMID" -gt "$MAX_VMID" ]; then
    # VM doesn't use Crucible storage, exit silently
    exit 0
fi

log "Handling $ACTION for VM-$VMID"

case "$ACTION" in
    start)
        # Start NBD server and connect device
        log "Starting Crucible NBD for VM-$VMID"

        # Start the NBD server (connects to downstairs on proper-raptor)
        if ! systemctl is-active --quiet crucible-vm@${VMID}.service; then
            systemctl start crucible-vm@${VMID}.service
            sleep 2
        fi

        # Connect the NBD device
        if ! systemctl is-active --quiet crucible-vm-connect@${VMID}.service; then
            systemctl start crucible-vm-connect@${VMID}.service
        fi

        # Verify device exists
        NBD_DEV=$((VMID - MIN_VMID))
        if [ -b "/dev/nbd${NBD_DEV}" ]; then
            log "VM-$VMID: /dev/nbd${NBD_DEV} ready"
        else
            log "ERROR: /dev/nbd${NBD_DEV} not available!"
            exit 1
        fi
        ;;

    stop)
        # Disconnect device and stop NBD server
        log "Stopping Crucible NBD for VM-$VMID"

        # Stop NBD connection first
        systemctl stop crucible-vm-connect@${VMID}.service 2>/dev/null || true

        # Stop NBD server
        systemctl stop crucible-vm@${VMID}.service 2>/dev/null || true

        log "VM-$VMID: Crucible storage disconnected"
        ;;

    migrate)
        # Migration: stop on this node (target node's hook will start)
        log "Migration: stopping Crucible NBD for VM-$VMID (target: $TARGET_NODE)"

        # Ensure clean disconnect
        systemctl stop crucible-vm-connect@${VMID}.service 2>/dev/null || true
        systemctl stop crucible-vm@${VMID}.service 2>/dev/null || true

        log "VM-$VMID: Ready for migration to $TARGET_NODE"
        ;;

    *)
        log "Unknown action: $ACTION"
        exit 1
        ;;
esac

exit 0
