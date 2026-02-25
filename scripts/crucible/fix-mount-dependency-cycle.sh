#!/bin/bash
# fix-mount-dependency-cycle.sh
#
# Detects and fixes the systemd dependency cycle caused by the Crucible NBD
# mount unit missing DefaultDependencies=no. Without this setting, systemd
# auto-adds the mount to local-fs.target, creating a cycle that can kill
# dbus.socket on boot.
#
# Usage:
#   ./fix-mount-dependency-cycle.sh                  # Fix all Proxmox hosts
#   ./fix-mount-dependency-cycle.sh pumped-piglet.maas  # Fix specific host
#   ./fix-mount-dependency-cycle.sh --check          # Dry run, check only
#
# See: docs/runbooks/crucible-mount-dbus-dependency-cycle-rca.md

set -euo pipefail

MOUNT_UNIT="mnt-crucible\\x2dstorage.mount"
MOUNT_PATH="/etc/systemd/system/mnt-crucible\\x2dstorage.mount"

# All Proxmox hosts with Crucible storage
ALL_HOSTS=(
    "pumped-piglet.maas"
    "still-fawn.maas"
    "pve.maas"
    "chief-horse.maas"
    "fun-bedbug.maas"
)

CHECK_ONLY=false
TARGETS=()

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --check|--dry-run)
            CHECK_ONLY=true
            ;;
        --help|-h)
            echo "Usage: $0 [--check] [host1.maas host2.maas ...]"
            echo ""
            echo "  --check     Dry run: detect issues without fixing"
            echo "  host.maas   Target specific host(s) instead of all"
            echo ""
            echo "Default: fix all Proxmox hosts (${ALL_HOSTS[*]})"
            exit 0
            ;;
        *)
            TARGETS+=("$arg")
            ;;
    esac
done

# Default to all hosts if none specified
if [[ ${#TARGETS[@]} -eq 0 ]]; then
    TARGETS=("${ALL_HOSTS[@]}")
fi

# Counters
TOTAL=0
FIXED=0
ALREADY_OK=0
MISSING=0
NEEDS_FIX=0
ERRORS=0

check_host() {
    local host="$1"
    local result

    # Check if mount unit exists
    if ! ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${host}" \
        "test -f '${MOUNT_PATH}'" 2>/dev/null; then
        echo "  SKIP: No Crucible mount unit found"
        ((MISSING++))
        return 1
    fi

    # Check if DefaultDependencies=no is already present
    if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${host}" \
        "grep -q 'DefaultDependencies=no' '${MOUNT_PATH}'" 2>/dev/null; then
        echo "  OK: DefaultDependencies=no already present"
        ((ALREADY_OK++))
        return 0
    fi

    # Check for dependency cycles
    result=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${host}" \
        "systemd-analyze verify '${MOUNT_UNIT}' 2>&1" 2>/dev/null || true)

    if echo "$result" | grep -qi "ordering cycle"; then
        echo "  CYCLE DETECTED: systemd-analyze verify reports ordering cycle"
    else
        echo "  MISSING: DefaultDependencies=no not set (cycle may appear on next boot)"
    fi

    return 2  # Needs fix
}

fix_host() {
    local host="$1"

    # Read the current unit file
    local current
    current=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${host}" \
        "cat '${MOUNT_PATH}'" 2>/dev/null)

    if [[ -z "$current" ]]; then
        echo "  ERROR: Could not read mount unit file"
        ((ERRORS++))
        return 1
    fi

    # Inject DefaultDependencies=no after the [Unit] Description line
    ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${host}" \
        "sed -i '/^Description=.*Crucible/a DefaultDependencies=no' '${MOUNT_PATH}'" 2>/dev/null

    # Verify it was added
    if ! ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${host}" \
        "grep -q 'DefaultDependencies=no' '${MOUNT_PATH}'" 2>/dev/null; then
        echo "  ERROR: sed injection failed, writing full unit file"
        # Fallback: write the complete corrected file
        ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${host}" "cat > '${MOUNT_PATH}' << 'UNITEOF'
[Unit]
Description=Crucible Storage Mount
DefaultDependencies=no
After=crucible-nbd-connect.service
Requires=crucible-nbd-connect.service

[Mount]
What=/dev/nbd0
Where=/mnt/crucible-storage
Type=ext4
Options=defaults,noatime

[Install]
WantedBy=multi-user.target
UNITEOF" 2>/dev/null
    fi

    # Reload systemd
    ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${host}" \
        "systemctl daemon-reload" 2>/dev/null

    # Verify fix
    local verify
    verify=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${host}" \
        "systemd-analyze verify '${MOUNT_UNIT}' 2>&1" 2>/dev/null || true)

    if echo "$verify" | grep -qi "ordering cycle"; then
        echo "  ERROR: Cycle still present after fix!"
        ((ERRORS++))
        return 1
    fi

    echo "  FIXED: DefaultDependencies=no added, daemon-reload done, no cycles"
    ((FIXED++))
    return 0
}

# Also check dbus status on each host
check_dbus() {
    local host="$1"
    local dbus_status

    dbus_status=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${host}" \
        "systemctl is-active dbus.socket 2>/dev/null" 2>/dev/null || echo "unknown")

    if [[ "$dbus_status" != "active" ]]; then
        echo "  WARNING: dbus.socket is ${dbus_status} (may need: systemctl start dbus.socket dbus.service)"
    fi
}

echo "=== Crucible Mount Dependency Cycle Fix ==="
echo ""
if $CHECK_ONLY; then
    echo "Mode: CHECK ONLY (no changes will be made)"
else
    echo "Mode: FIX (will modify unit files and reload systemd)"
fi
echo "Targets: ${TARGETS[*]}"
echo ""

for host in "${TARGETS[@]}"; do
    ((TOTAL++))
    echo "[$host]"

    # Test connectivity
    if ! ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@${host}" "true" 2>/dev/null; then
        echo "  ERROR: Cannot connect via SSH"
        ((ERRORS++))
        echo ""
        continue
    fi

    status=0
    check_host "$host" || status=$?

    if [[ $status -eq 2 ]]; then
        # Needs fix
        if $CHECK_ONLY; then
            echo "  ACTION NEEDED: Run without --check to fix"
            ((NEEDS_FIX++))
        else
            fix_host "$host"
        fi
    fi

    check_dbus "$host"
    echo ""
done

echo "=== Summary ==="
echo "Hosts checked:  $TOTAL"
echo "Already fixed:  $ALREADY_OK"
if $CHECK_ONLY; then
    echo "Needs fix:      $NEEDS_FIX"
else
    echo "Fixed now:      $FIXED"
fi
echo "No mount unit:  $MISSING"
echo "Errors:         $ERRORS"

if $CHECK_ONLY && [[ $NEEDS_FIX -gt 0 ]]; then
    echo ""
    echo "Run without --check to apply fixes."
    exit 1
fi

if [[ $ERRORS -gt 0 ]]; then
    exit 1
fi
exit 0
