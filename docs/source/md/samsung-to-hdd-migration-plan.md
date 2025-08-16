# Samsung T5 to HDD Migration Plan

## Current State Summary
- **Device**: Samsung Portable SSD T5 (931.5GB)
- **Location**: fun-bedbug.maas - USB 3.0
- **ZFS Pool**: local-1TB-backup
- **Total Used**: 160GB
  - Frigate (LXC 113): 160GB camera recordings in `/media`
  - Duplicati (LXC 114): 595MB rootfs
- **Available**: 739GB free

## Pre-Migration Checklist
- [ ] Backup confirmed (you mentioned you have this)
- [ ] New HDD ready to connect
- [ ] Maintenance window scheduled (Frigate will be down)

## Migration Steps

### Phase 1: Preparation (Before plugging in HDD)
```bash
# 1. Create ZFS snapshot for safety (we'll run this)
ssh root@fun-bedbug.maas "zfs snapshot -r local-1TB-backup@pre-migration-$(date +%Y%m%d)"

# 2. Stop Frigate to prevent new recordings during migration
ssh root@fun-bedbug.maas "pct stop 113"

# 3. Verify Duplicati is already stopped
ssh root@fun-bedbug.maas "pct status 114"
```

### Phase 2: HDD Connection & Verification
When you plug in the HDD:
```bash
# 1. Identify the new HDD
ssh root@fun-bedbug.maas "lsusb"  # Check new USB device
ssh root@fun-bedbug.maas "dmesg | tail -20"  # See device attachment
ssh root@fun-bedbug.maas "lsblk -o NAME,SIZE,TYPE,MODEL,SERIAL"  # Find device name

# 2. Peek at existing HDD data (as requested)
# We'll mount it read-only first to examine contents
```

### Phase 3: Data Migration Options

#### Option A: ZFS Send/Receive (Preserves everything)
```bash
# 1. Create ZFS pool on new HDD
zpool create -o ashift=12 -O compression=lz4 \
  -O mountpoint=/local-1TB-backup-new \
  local-1TB-backup-new /dev/sdX  # X = new drive letter

# 2. Migrate data using ZFS send/receive
zfs send -R local-1TB-backup@pre-migration | \
  zfs receive -F local-1TB-backup-new

# 3. Export old pool, rename new pool
zpool export local-1TB-backup
zpool export local-1TB-backup-new
zpool import local-1TB-backup-new local-1TB-backup
```

#### Option B: Fresh ZFS Pool with rsync (Clean start)
```bash
# 1. Create new ZFS pool
zpool create -o ashift=12 -O compression=lz4 \
  -O mountpoint=/local-1TB-backup \
  local-1TB-backup-new /dev/sdX

# 2. Create datasets
zfs create local-1TB-backup-new/subvol-113-disk-0
zfs create local-1TB-backup-new/subvol-114-disk-0

# 3. Copy data
rsync -avhP /local-1TB-backup/subvol-113-disk-0/ \
  /local-1TB-backup-new/subvol-113-disk-0/
rsync -avhP /local-1TB-backup/subvol-114-disk-0/ \
  /local-1TB-backup-new/subvol-114-disk-0/
```

### Phase 4: Switchover
```bash
# 1. Stop using old pool
zpool export local-1TB-backup

# 2. Rename new pool (if using option B)
zpool export local-1TB-backup-new
zpool import local-1TB-backup-new local-1TB-backup

# 3. Update Proxmox storage if mount point changed
pvesm set local-1TB-backup --disable 0

# 4. Start containers
pct start 113  # Frigate
pct start 114  # Duplicati (if needed)
```

### Phase 5: Verification
```bash
# 1. Verify pool status
zpool status local-1TB-backup

# 2. Check Frigate is recording
pct exec 113 -- df -h /media
pct exec 113 -- ls -la /media/frigate/recordings/

# 3. Verify container functionality
curl -I http://frigate.local:5000  # Or appropriate URL
```

## Rollback Plan
If issues occur:
```bash
# 1. Stop containers
pct stop 113 114

# 2. Reconnect Samsung T5
# 3. Import original pool
zpool import local-1TB-backup

# 4. Restart containers
pct start 113
```

## Key Considerations
1. **Frigate Downtime**: ~30-60 minutes expected
2. **HDD Performance**: HDDs are slower than SSD for random I/O
   - Frigate recordings are sequential writes (good for HDD)
   - May notice slower UI/timeline scrubbing
3. **USB Connection**: Ensure stable USB connection (avoid USB hubs)
4. **Space Planning**: 
   - Current: 160GB used, 739GB free
   - Ensure new HDD has adequate space for growth

## Ready to Proceed?
When you're ready:
1. Plug in the new HDD
2. We'll identify it and peek at the contents
3. Choose migration method based on HDD state
4. Execute the migration with verification at each step