#!/bin/bash
# Backup config files from Proxmox hosts to Crucible storage
#
# Usage: ./backup-configs-to-crucible.sh [HOST]
#
# Backs up configs that may not be in git or are host-specific:
# - /etc/pve/* (Proxmox cluster config)
# - /etc/network/interfaces
# - /etc/hosts
# - /etc/systemd/system/crucible-* (Crucible services)
# - LXC configs
# - VM configs
#
# Each host backs up to its own /mnt/crucible-storage/configs/
set -e

# Hosts to backup (or pass specific host as argument)
if [[ -n "$1" ]]; then
    HOSTS=("$1")
else
    HOSTS=(pve still-fawn.maas pumped-piglet.maas chief-horse.maas fun-bedbug.maas)
fi

BACKUP_BASE="/mnt/crucible-storage/configs"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

log() {
    echo "[$(date '+%H:%M:%S')] $*"
}

backup_host() {
    local host="$1"
    local ssh_host="root@$host"

    echo ""
    echo "=== $host ==="

    # Check mount
    if ! ssh "$ssh_host" "mountpoint -q /mnt/crucible-storage" 2>/dev/null; then
        log "SKIP: Crucible not mounted on $host"
        return
    fi

    ssh "$ssh_host" "
        set -e
        BACKUP_DIR='$BACKUP_BASE/$TIMESTAMP'
        mkdir -p \"\$BACKUP_DIR\"

        echo 'Backing up Proxmox configs...'
        # /etc/pve (cluster config, VM/LXC configs, storage.cfg, etc.)
        if [[ -d /etc/pve ]]; then
            cp -a /etc/pve \"\$BACKUP_DIR/\" 2>/dev/null || true
        fi

        echo 'Backing up network config...'
        cp /etc/network/interfaces \"\$BACKUP_DIR/\" 2>/dev/null || true
        cp /etc/hosts \"\$BACKUP_DIR/\" 2>/dev/null || true
        cp /etc/hostname \"\$BACKUP_DIR/\" 2>/dev/null || true

        echo 'Backing up Crucible services...'
        mkdir -p \"\$BACKUP_DIR/systemd\"
        cp /etc/systemd/system/crucible-*.service \"\$BACKUP_DIR/systemd/\" 2>/dev/null || true
        cp /etc/systemd/system/mnt-crucible*.mount \"\$BACKUP_DIR/systemd/\" 2>/dev/null || true

        echo 'Backing up module configs...'
        cp /etc/modules-load.d/nbd.conf \"\$BACKUP_DIR/\" 2>/dev/null || true

        echo 'Backing up fstab...'
        cp /etc/fstab \"\$BACKUP_DIR/\" 2>/dev/null || true

        echo 'Backing up ZFS pools (if any)...'
        zpool list -H 2>/dev/null > \"\$BACKUP_DIR/zpool-list.txt\" || true
        zfs list -H 2>/dev/null > \"\$BACKUP_DIR/zfs-list.txt\" || true

        # Create manifest
        echo \"Backup created: \$(date)\" > \"\$BACKUP_DIR/MANIFEST.txt\"
        echo \"Host: \$(hostname)\" >> \"\$BACKUP_DIR/MANIFEST.txt\"
        echo '' >> \"\$BACKUP_DIR/MANIFEST.txt\"
        echo 'Files:' >> \"\$BACKUP_DIR/MANIFEST.txt\"
        find \"\$BACKUP_DIR\" -type f | sort >> \"\$BACKUP_DIR/MANIFEST.txt\"

        # Show result
        echo ''
        echo \"Backup saved to: \$BACKUP_DIR\"
        du -sh \"\$BACKUP_DIR\" | cut -f1 | xargs -I{} echo \"Size: {}\"

        # Keep only last 5 backups
        echo ''
        echo 'Cleaning old backups (keeping last 5)...'
        ls -dt $BACKUP_BASE/*/ 2>/dev/null | tail -n +6 | xargs rm -rf 2>/dev/null || true
        echo \"Backups on disk: \$(ls -1 $BACKUP_BASE 2>/dev/null | wc -l)\"
    "
}

log "Starting config backup to Crucible storage"

for host in "${HOSTS[@]}"; do
    backup_host "$host"
done

echo ""
log "Done"
