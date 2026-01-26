#!/bin/bash
# Check status of HA-ready Crucible storage across all hosts
#
# Usage: status-ha-storage.sh [VMID]
#
# Without VMID: Shows all VM volumes and their status
# With VMID:    Shows detailed status for specific VM
#
set -e

VMID="$1"
CRUCIBLE_IP="192.168.4.189"
CRUCIBLE_HOST="ubuntu@${CRUCIBLE_IP}"

# Proxmox hosts
HOSTS=(
    "pve"
    "still-fawn.maas"
    "pumped-piglet.maas"
    "chief-horse.maas"
)

MIN_VMID=200

echo "=== Crucible HA Storage Status ==="
echo ""

# Check proper-raptor (storage server)
echo "=== Storage Server (proper-raptor @ ${CRUCIBLE_IP}) ==="

if ! ssh -o ConnectTimeout=3 -o BatchMode=yes "$CRUCIBLE_HOST" "true" 2>/dev/null; then
    echo "  ERROR: Cannot connect to storage server"
else
    if [ -n "$VMID" ]; then
        # Show specific VM
        echo "  VM-${VMID} downstairs:"
        for i in 0 1 2; do
            PORT=$((3900 + (VMID - MIN_VMID) * 10 + i))
            STATUS=$(ssh "$CRUCIBLE_HOST" "systemctl is-active crucible-vm-${VMID}-${i}.service 2>/dev/null || echo 'not found'")
            LISTENING=$(ssh "$CRUCIBLE_HOST" "ss -tlnp | grep -q ':${PORT}' && echo 'listening' || echo 'not listening'")
            echo "    Region $i: port $PORT - $STATUS ($LISTENING)"
        done
    else
        # Show all VM volumes
        echo "  Active downstairs services:"
        SERVICES=$(ssh "$CRUCIBLE_HOST" "systemctl list-units 'crucible-vm-*' --no-pager --plain | grep -E '\.service' | awk '{print \$1}'" 2>/dev/null || echo "")
        if [ -z "$SERVICES" ]; then
            echo "    (none)"
        else
            # Group by VMID
            VMIDS=$(echo "$SERVICES" | sed -n 's/crucible-vm-\([0-9]*\)-.*/\1/p' | sort -u)
            for vid in $VMIDS; do
                COUNT=$(echo "$SERVICES" | grep "crucible-vm-${vid}-" | wc -l | tr -d ' ')
                echo "    VM-${vid}: $COUNT/3 regions"
            done
        fi
        echo ""
        echo "  Listening ports:"
        ssh "$CRUCIBLE_HOST" "ss -tlnp | grep crucible | awk '{print \$4}' | sort -t: -k2 -n | head -20" 2>/dev/null || echo "    (none)"
    fi
fi

echo ""
echo "=== Proxmox Hosts ==="

for host in "${HOSTS[@]}"; do
    # Determine SSH target
    if [ "$host" == "pve" ]; then
        SSH_TARGET="root@pve"
    else
        SSH_TARGET="root@${host}"
    fi

    echo ""
    echo "--- $host ---"

    if ! ssh -o ConnectTimeout=3 -o BatchMode=yes "$SSH_TARGET" "true" 2>/dev/null; then
        echo "  ERROR: Cannot connect"
        continue
    fi

    if [ -n "$VMID" ]; then
        # Show specific VM
        NBD_DEV=$((VMID - MIN_VMID))
        NBD_SVC="crucible-vm@${VMID}.service"
        NBD_CONN="crucible-vm-connect@${VMID}.service"

        NBD_STATUS=$(ssh "$SSH_TARGET" "systemctl is-active $NBD_SVC 2>/dev/null || echo 'inactive'")
        CONN_STATUS=$(ssh "$SSH_TARGET" "systemctl is-active $NBD_CONN 2>/dev/null || echo 'inactive'")
        DEV_EXISTS=$(ssh "$SSH_TARGET" "test -b /dev/nbd${NBD_DEV} && echo 'yes' || echo 'no'")

        echo "  VM-${VMID}:"
        echo "    NBD server:  $NBD_STATUS"
        echo "    NBD connect: $CONN_STATUS"
        echo "    /dev/nbd${NBD_DEV}: $DEV_EXISTS"
    else
        # Show all active VM services
        ACTIVE=$(ssh "$SSH_TARGET" "systemctl list-units 'crucible-vm@*' --no-pager --plain 2>/dev/null | grep -E 'active' | awk '{print \$1}'" || echo "")
        if [ -z "$ACTIVE" ]; then
            echo "  No active VM connections"
        else
            for svc in $ACTIVE; do
                VID=$(echo "$svc" | sed 's/crucible-vm@\([0-9]*\)\.service/\1/')
                NBD_DEV=$((VID - MIN_VMID))
                DEV_EXISTS=$(ssh "$SSH_TARGET" "test -b /dev/nbd${NBD_DEV} && echo 'OK' || echo 'NO'")
                echo "  VM-${VID}: /dev/nbd${NBD_DEV} ($DEV_EXISTS)"
            done
        fi
    fi
done

echo ""
echo "=== Commands ==="
echo "Create volume:  ./scripts/crucible/create-vm-volume.sh <VMID> [SIZE_GB]"
echo "Connect:        systemctl start crucible-vm@<VMID> crucible-vm-connect@<VMID>"
echo "Disconnect:     systemctl stop crucible-vm-connect@<VMID> crucible-vm@<VMID>"
echo "Test failover:  ./scripts/crucible/test-ha-failover.sh <VMID> <HOST1> <HOST2>"
