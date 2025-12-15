#!/bin/bash
# Setup external HDD as a PBS datastore (PBS-native approach)
#
# This script:
# 1. Detects and mounts external USB HDD on Proxmox host
# 2. Formats as ext4 if needed (with confirmation)
# 3. Passes through mount to PBS LXC container (103)
# 4. Creates PBS datastore using proxmox-backup-manager
#
# Benefits over rsync approach:
# - Deduplication (saves 50-70% space)
# - Incremental sync (only changed chunks)
# - Native PBS restore commands work
# - Web UI visibility
# - Integrity verification
#
# Run on: pumped-piglet.maas (where PBS LXC 103 and external HDD are)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
PBS_LXC_ID=103
MOUNT_POINT="/mnt/external-backup"
PBS_MOUNT_POINT="/mnt/external-hdd"  # Inside PBS container
DATASTORE_NAME="external-hdd"

echo "========================================="
echo "PBS External HDD Datastore Setup"
echo "========================================="
echo ""
echo "This script configures an external HDD as a PBS datastore"
echo "using PBS native functionality (not rsync)."
echo ""

# Check we're on a Proxmox host
if ! command -v pct &>/dev/null; then
    echo "ERROR: This script must be run on a Proxmox host (pct not found)"
    exit 1
fi

# Check PBS container exists
if ! pct status $PBS_LXC_ID &>/dev/null; then
    echo "ERROR: PBS container (LXC $PBS_LXC_ID) not found"
    exit 1
fi

echo "PBS Container: LXC $PBS_LXC_ID"
echo ""

# Detect external drives
echo "Detecting external USB drives..."
echo ""
lsblk -d -o NAME,SIZE,TYPE,TRAN,MODEL | grep -E "usb|NAME"
echo ""

# List available block devices that might be external
AVAILABLE_DISKS=$(lsblk -d -n -o NAME,TRAN | grep usb | awk '{print $1}')

if [ -z "$AVAILABLE_DISKS" ]; then
    echo "No USB drives detected."
    echo ""
    echo "Please connect an external USB HDD and run this script again."
    echo ""
    echo "If the drive is connected but not detected, check:"
    echo "  dmesg | tail -20"
    echo "  lsusb"
    exit 1
fi

echo "Available USB disks:"
for disk in $AVAILABLE_DISKS; do
    size=$(lsblk -d -n -o SIZE /dev/$disk)
    model=$(lsblk -d -n -o MODEL /dev/$disk)
    echo "  /dev/$disk - $size - $model"
done
echo ""

read -p "Enter disk to use (e.g., sdb): " DISK
DISK_PATH="/dev/$DISK"

if [ ! -b "$DISK_PATH" ]; then
    echo "ERROR: $DISK_PATH is not a valid block device"
    exit 1
fi

# Check if disk has partitions
PARTITION="${DISK_PATH}1"
if [ ! -b "$PARTITION" ]; then
    echo ""
    echo "No partition found on $DISK_PATH"
    echo "WARNING: This will ERASE ALL DATA on $DISK_PATH"
    read -p "Create partition and format as ext4? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Creating partition..."
        parted -s "$DISK_PATH" mklabel gpt
        parted -s "$DISK_PATH" mkpart primary ext4 0% 100%
        sleep 2
        PARTITION="${DISK_PATH}1"
        echo "Formatting as ext4..."
        mkfs.ext4 -L "pbs-external" "$PARTITION"
    else
        echo "Aborted."
        exit 0
    fi
fi

# Check filesystem
FS_TYPE=$(blkid -o value -s TYPE "$PARTITION" 2>/dev/null || echo "unknown")
echo "Partition: $PARTITION (filesystem: $FS_TYPE)"

if [ "$FS_TYPE" != "ext4" ]; then
    echo "WARNING: Partition is not ext4 (found: $FS_TYPE)"
    echo "WARNING: This will ERASE ALL DATA on $PARTITION"
    read -p "Format as ext4? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mkfs.ext4 -L "pbs-external" "$PARTITION"
    else
        echo "Aborted. Please format the partition manually."
        exit 1
    fi
fi

# Get UUID for fstab
UUID=$(blkid -o value -s UUID "$PARTITION")
echo "Partition UUID: $UUID"

# Create mount point on host
echo ""
echo "Creating mount point at $MOUNT_POINT..."
mkdir -p "$MOUNT_POINT"

# Add to fstab if not already present
if ! grep -q "$UUID" /etc/fstab; then
    echo "Adding to /etc/fstab..."
    echo "UUID=$UUID $MOUNT_POINT ext4 defaults,nofail 0 2" >> /etc/fstab
else
    echo "Already in /etc/fstab"
fi

# Mount
echo "Mounting..."
mount "$MOUNT_POINT" 2>/dev/null || mount -a

# Verify mount
if mountpoint -q "$MOUNT_POINT"; then
    echo "Mounted successfully at $MOUNT_POINT"
    df -h "$MOUNT_POINT"
else
    echo "ERROR: Failed to mount"
    exit 1
fi

# Create directory for PBS datastore
DATASTORE_PATH="$MOUNT_POINT/pbs-datastore"
mkdir -p "$DATASTORE_PATH"
chown 100000:100000 "$DATASTORE_PATH"  # Map to root inside LXC
echo "Created datastore directory: $DATASTORE_PATH"

# Add bind mount to LXC config
echo ""
echo "Configuring LXC $PBS_LXC_ID bind mount..."

LXC_CONF="/etc/pve/lxc/${PBS_LXC_ID}.conf"

# Check if mount point already exists
if grep -q "mp[0-9]*:.*$MOUNT_POINT" "$LXC_CONF" 2>/dev/null; then
    echo "Bind mount already configured in LXC"
else
    # Find next available mp number
    NEXT_MP=$(grep -oP 'mp\K[0-9]+' "$LXC_CONF" 2>/dev/null | sort -n | tail -1)
    NEXT_MP=$((${NEXT_MP:-0} + 1))

    echo "Adding mp$NEXT_MP to $LXC_CONF..."
    echo "mp$NEXT_MP: $DATASTORE_PATH,mp=$PBS_MOUNT_POINT" >> "$LXC_CONF"
fi

# Restart LXC to apply mount
echo "Restarting PBS container to apply mount..."
pct stop $PBS_LXC_ID 2>/dev/null || true
sleep 2
pct start $PBS_LXC_ID
sleep 5

# Verify mount inside container
echo ""
echo "Verifying mount inside PBS container..."
if pct exec $PBS_LXC_ID -- mountpoint -q "$PBS_MOUNT_POINT" 2>/dev/null; then
    echo "Mount verified inside container at $PBS_MOUNT_POINT"
    pct exec $PBS_LXC_ID -- df -h "$PBS_MOUNT_POINT"
else
    # Check if directory exists and is accessible
    if pct exec $PBS_LXC_ID -- ls -la "$PBS_MOUNT_POINT" &>/dev/null; then
        echo "Directory accessible at $PBS_MOUNT_POINT"
        pct exec $PBS_LXC_ID -- df -h "$PBS_MOUNT_POINT"
    else
        echo "ERROR: Mount not visible inside container"
        echo "Check LXC config and restart manually"
        exit 1
    fi
fi

# Create PBS datastore
echo ""
echo "Creating PBS datastore '$DATASTORE_NAME'..."

# Check if datastore already exists
if pct exec $PBS_LXC_ID -- proxmox-backup-manager datastore list 2>/dev/null | grep -q "^$DATASTORE_NAME"; then
    echo "Datastore '$DATASTORE_NAME' already exists"
else
    pct exec $PBS_LXC_ID -- proxmox-backup-manager datastore create \
        "$DATASTORE_NAME" \
        "$PBS_MOUNT_POINT"
    echo "Datastore created successfully"
fi

# List datastores
echo ""
echo "Current PBS datastores:"
pct exec $PBS_LXC_ID -- proxmox-backup-manager datastore list

echo ""
echo "========================================="
echo "Setup Complete"
echo "========================================="
echo ""
echo "External HDD configured as PBS datastore:"
echo "  Host mount: $MOUNT_POINT"
echo "  Container mount: $PBS_MOUNT_POINT"
echo "  Datastore name: $DATASTORE_NAME"
echo ""
echo "Next steps:"
echo "  1. Run setup-pbs-sync-job.sh to create sync job"
echo "  2. Run setup-pbs-verify-job.sh to create verify job"
echo ""
echo "PBS Web UI: https://192.168.4.218:8007"
echo ""
echo "To take HDD offsite:"
echo "  1. pct exec $PBS_LXC_ID -- proxmox-backup-manager datastore remove $DATASTORE_NAME"
echo "  2. umount $MOUNT_POINT"
echo "  3. Disconnect HDD"
echo "  4. When reconnected: mount $MOUNT_POINT && run this script again"
