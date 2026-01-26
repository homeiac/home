#!/bin/bash
# Sync sensitive configs to Crucible storage as backup
#
# Usage: ./sync-secrets-to-crucible.sh [--dry-run]
#
# Backs up sensitive files that can't be checked into git:
# - SOPS age keys
# - SSH private keys
# - .env files with credentials
# - Certificate private keys
#
# Files are synced to /mnt/crucible-storage/secrets/ on each Proxmox host.
# Crucible provides redundancy when multiple sleds are configured.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DRY_RUN=false

# Parse arguments
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "=== DRY RUN MODE ==="
fi

# Local paths to backup (dest:src pairs)
# These are files on the local Mac that get synced to Crucible
LOCAL_SECRETS=(
    "sops/age.key:$HOME/.config/sops/age/keys.txt"
    "ssh/id_ed25519_pve:$HOME/.ssh/id_ed25519_pve"
    "ssh/id_ed25519_pve.pub:$HOME/.ssh/id_ed25519_pve.pub"
    "env/homelab.env:$REPO_ROOT/proxmox/homelab/.env"
)

# Target host (use pve as primary backup location)
BACKUP_HOST="pve"
BACKUP_BASE="/mnt/crucible-storage/secrets"

log() {
    echo "[$(date '+%H:%M:%S')] $*"
}

# Check Crucible mount is available
check_mount() {
    log "Checking Crucible mount on $BACKUP_HOST..."
    if ! ssh "root@$BACKUP_HOST" "mountpoint -q /mnt/crucible-storage"; then
        echo "ERROR: /mnt/crucible-storage not mounted on $BACKUP_HOST" >&2
        echo "Run: ./scripts/crucible/attach-volumes-to-proxmox.sh" >&2
        exit 1
    fi
    log "Mount verified"
}

# Create directory structure
setup_dirs() {
    log "Setting up directory structure..."
    local dirs="sops ssh env certs backups"

    if $DRY_RUN; then
        echo "Would create: $BACKUP_BASE/{$dirs}"
        return
    fi

    ssh "root@$BACKUP_HOST" "
        mkdir -p $BACKUP_BASE/{sops,ssh,env,certs,backups}
        chmod 700 $BACKUP_BASE
        chmod 700 $BACKUP_BASE/*
    "
}

# Sync a single file
sync_file() {
    local dest_path="$1"
    local src_path="$2"

    if [[ ! -f "$src_path" ]]; then
        log "SKIP: $src_path (not found)"
        return
    fi

    local dest_full="$BACKUP_BASE/$dest_path"

    if $DRY_RUN; then
        echo "Would sync: $src_path -> $BACKUP_HOST:$dest_full"
        return
    fi

    log "Syncing: $dest_path"
    scp -q "$src_path" "root@$BACKUP_HOST:$dest_full"
    ssh "root@$BACKUP_HOST" "chmod 600 '$dest_full'"
}

# List current backups
list_backups() {
    log "Current backups on $BACKUP_HOST:"
    ssh "root@$BACKUP_HOST" "
        if [[ -d '$BACKUP_BASE' ]]; then
            find '$BACKUP_BASE' -type f -exec ls -lh {} \; 2>/dev/null | awk '{print \$5, \$9}'
        else
            echo '(none)'
        fi
    "
}

# Main
log "Starting secrets backup to Crucible storage"

check_mount
setup_dirs

echo ""
log "Syncing local secrets..."
for pair in "${LOCAL_SECRETS[@]}"; do
    dest_path="${pair%%:*}"
    src_path="${pair#*:}"
    sync_file "$dest_path" "$src_path"
done

echo ""
list_backups

echo ""
log "Done. Secrets backed up to $BACKUP_HOST:$BACKUP_BASE"
