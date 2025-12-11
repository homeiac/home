#!/bin/bash
# Frigate Coral LXC - Add Storage Mount for Recordings
# GitHub Issue: #168
#
# Adds external storage passthrough to Frigate container for recordings.
# User must physically connect and mount the drive on host first.
#
# Usage: ./44-add-storage-mount.sh [HOST_MOUNT_PATH]
#   If HOST_MOUNT_PATH not provided, script will show available mounts and prompt.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

# Accept mount path as argument or prompt
HOST_MOUNT_PATH="${1:-}"
CONTAINER_MOUNT_PATH="/media/frigate"

echo "=== Frigate Coral LXC - Add Storage Mount ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo "Container: $VMID"
echo ""

# Check if storage is mounted on host
echo "1. Checking for mounted storage on host..."
echo ""
echo "   Block devices:"
ssh root@"$PVE_HOST" "lsblk -o NAME,SIZE,TYPE,MOUNTPOINT | grep -E 'disk|part'" 2>/dev/null || true

echo ""
echo "   ZFS pools:"
ssh root@"$PVE_HOST" "zfs list -o name,used,avail,mountpoint 2>/dev/null | head -10" || echo "   No ZFS pools"

echo ""
echo "   Large storage mounts:"
STORAGE_MOUNTS=$(ssh root@"$PVE_HOST" "df -h | grep -E '/local-|/mnt|/media' | grep -v '^tmpfs'" 2>/dev/null || echo "")
if [ -n "$STORAGE_MOUNTS" ]; then
    echo "$STORAGE_MOUNTS"
else
    echo "   No large storage mounts found"
fi

# If no path provided as argument, prompt
if [ -z "$HOST_MOUNT_PATH" ]; then
    echo ""
    echo "   Enter the host mount path for Frigate storage:"
    echo "   (e.g., /local-3TB-backup or /mnt/frigate-storage)"
    read -r USER_MOUNT_PATH
    if [ -z "$USER_MOUNT_PATH" ]; then
        echo "   Exiting - no path provided"
        exit 1
    fi
    HOST_MOUNT_PATH="$USER_MOUNT_PATH"
else
    echo ""
    echo "   Using provided path: $HOST_MOUNT_PATH"
fi

# Verify mount path exists
echo ""
echo "2. Verifying mount path: $HOST_MOUNT_PATH"
if ! ssh root@"$PVE_HOST" "test -d $HOST_MOUNT_PATH" 2>/dev/null; then
    echo "   ❌ Mount path does not exist: $HOST_MOUNT_PATH"
    exit 1
fi

MOUNT_SIZE=$(ssh root@"$PVE_HOST" "df -h $HOST_MOUNT_PATH | tail -1 | awk '{print \$2}'" 2>/dev/null)
MOUNT_AVAIL=$(ssh root@"$PVE_HOST" "df -h $HOST_MOUNT_PATH | tail -1 | awk '{print \$4}'" 2>/dev/null)
echo "   ✅ Mount exists - Size: $MOUNT_SIZE, Available: $MOUNT_AVAIL"

# Stop container
echo ""
echo "3. Stopping container for config change..."
ssh root@"$PVE_HOST" "pct stop $VMID 2>/dev/null || true"
sleep 2
echo "   ✅ Container stopped"

# Backup config
echo ""
echo "4. Backing up LXC config..."
BACKUP_DIR="/Users/10381054/code/home/proxmox/backups/$PVE_HOST_NAME"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
ssh root@"$PVE_HOST" "cat /etc/pve/lxc/$VMID.conf" > "$BACKUP_DIR/lxc-$VMID-before-storage-$TIMESTAMP.conf"
echo "   ✅ Backed up to: $BACKUP_DIR/lxc-$VMID-before-storage-$TIMESTAMP.conf"

# Check if mp already exists for this path
echo ""
echo "5. Adding storage mount to LXC config..."
EXISTING_MP=$(ssh root@"$PVE_HOST" "grep -E '^mp[0-9]:' /etc/pve/lxc/$VMID.conf" 2>/dev/null || echo "")

if echo "$EXISTING_MP" | grep -q "$CONTAINER_MOUNT_PATH"; then
    echo "   ⚠️  Storage mount already exists:"
    echo "   $EXISTING_MP"
    echo "   Skipping..."
else
    # Find next available mp number
    NEXT_MP=0
    while ssh root@"$PVE_HOST" "grep -q '^mp${NEXT_MP}:' /etc/pve/lxc/$VMID.conf" 2>/dev/null; do
        NEXT_MP=$((NEXT_MP + 1))
    done

    # Add mount point
    ssh root@"$PVE_HOST" "echo 'mp${NEXT_MP}: ${HOST_MOUNT_PATH},mp=${CONTAINER_MOUNT_PATH}' >> /etc/pve/lxc/$VMID.conf"
    echo "   ✅ Added: mp${NEXT_MP}: ${HOST_MOUNT_PATH},mp=${CONTAINER_MOUNT_PATH}"
fi

# Start container
echo ""
echo "6. Starting container..."
ssh root@"$PVE_HOST" "pct start $VMID"
sleep 5
echo "   ✅ Container started"

# Verify mount inside container
echo ""
echo "7. Verifying mount inside container..."
sleep 3
CONTAINER_DF=$(ssh root@"$PVE_HOST" "pct exec $VMID -- df -h $CONTAINER_MOUNT_PATH 2>/dev/null" || echo "FAILED")

if echo "$CONTAINER_DF" | grep -q "$CONTAINER_MOUNT_PATH"; then
    echo "   ✅ Storage mounted successfully in container:"
    echo "$CONTAINER_DF" | tail -1
else
    echo "   ❌ Mount verification failed"
    echo "   Check: pct exec $VMID -- df -h"
fi

echo ""
echo "=== Storage Mount Complete ==="
echo ""
echo "Host path: $HOST_MOUNT_PATH"
echo "Container path: $CONTAINER_MOUNT_PATH"
echo ""
echo "NEXT: Run ./42-configure-cameras.sh to add cameras"
