#!/bin/bash
# Replicate Crucible storage contents across all Proxmox hosts
#
# Usage: ./replicate-crucible-storage.sh [--dry-run]
#
# Syncs /mnt/crucible-storage/{secrets,services,configs} from pve to all other hosts.
# This provides redundancy - if one host loses its Crucible connection, others have copies.
set -e

DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "=== DRY RUN MODE ==="
fi

PRIMARY_HOST="pve"
REPLICA_HOSTS=(still-fawn.maas pumped-piglet.maas chief-horse.maas fun-bedbug.maas)
SYNC_DIRS=(secrets services configs)

log() {
    echo "[$(date '+%H:%M:%S')] $*"
}

# Check mount on a host
check_mount() {
    local host="$1"
    ssh "root@$host" "mountpoint -q /mnt/crucible-storage" 2>/dev/null
}

# Sync a directory from primary to replica
sync_dir() {
    local dir="$1"
    local replica="$2"
    local src="/mnt/crucible-storage/$dir"
    local dest="/mnt/crucible-storage/$dir"

    # Check if source exists on primary
    if ! ssh "root@$PRIMARY_HOST" "test -d '$src'" 2>/dev/null; then
        log "SKIP: $dir (not on primary)"
        return
    fi

    if $DRY_RUN; then
        echo "Would sync: $PRIMARY_HOST:$src -> $replica:$dest"
        return
    fi

    log "Syncing $dir to $replica..."

    # Create dest dir
    ssh "root@$replica" "mkdir -p '$dest'"

    # Use tar pipe through local machine (avoids host key issues between Proxmox hosts)
    ssh "root@$PRIMARY_HOST" "tar -C '$src' -cf - ." | ssh "root@$replica" "tar -C '$dest' -xf -"
}

# Main
log "Starting Crucible storage replication"
log "Primary: $PRIMARY_HOST"
log "Replicas: ${REPLICA_HOSTS[*]}"

# Check primary mount
if ! check_mount "$PRIMARY_HOST"; then
    echo "ERROR: Crucible not mounted on primary ($PRIMARY_HOST)" >&2
    exit 1
fi

# Sync to each replica
for replica in "${REPLICA_HOSTS[@]}"; do
    echo ""
    echo "=== $replica ==="

    if ! check_mount "$replica"; then
        log "SKIP: Crucible not mounted"
        continue
    fi

    for dir in "${SYNC_DIRS[@]}"; do
        sync_dir "$dir" "$replica"
    done
done

echo ""
log "Replication complete"

# Show summary
echo ""
log "Storage contents:"
for host in $PRIMARY_HOST "${REPLICA_HOSTS[@]}"; do
    echo "--- $host ---"
    ssh "root@$host" "du -sh /mnt/crucible-storage/*/ 2>/dev/null | grep -v lost+found || echo '(empty)'"
done
