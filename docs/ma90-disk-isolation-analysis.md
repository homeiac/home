# MA90 Disk Isolation Analysis - Live Repartitioning vs MAAS Custom Storage

**Date**: August 31, 2025  
**System**: proper-raptor.maas (MA90 with 128GB M.2 SATA SSD)  
**Goal**: Create 3 separate ZFS pools for Crucible storage isolation

## Current System State

### Disk Layout (proper-raptor.maas)
```bash
# Current partition table
Disk /dev/sda: 119.24 GiB, 128035676160 bytes, 250069680 sectors
Device       Start       End   Sectors   Size Type
/dev/sda1     2048   1050623   1048576   512M EFI System
/dev/sda2  1050624 250069646 249019023 118.7G Linux filesystem

# Current filesystem usage
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda2       117G  7.9G  103G   8% /

# Available tools
/usr/sbin/parted
/usr/sbin/gdisk
/usr/bin/growpart
/usr/sbin/resize2fs
```

## Approach 1: Live Root Filesystem Repartitioning

### Feasibility Assessment
**MAJOR LIMITATION**: Cannot resize mounted ext4 filesystem directly
- `e2fsck -f /dev/sda2` fails: "e2fsck: Cannot continue, aborting. /dev/sda2 is mounted."
- Would require unmounting root filesystem (impossible on live system)

### Potential Solutions

#### Option 1A: Boot from Rescue/Live Media
```bash
# Boot from Ubuntu live USB/PXE rescue
# Then run from rescue environment:
sudo e2fsck -f /dev/sda2
sudo resize2fs /dev/sda2 40G  # Shrink to 40GB
sudo parted /dev/sda resizepart 2 40G
sudo parted /dev/sda mkpart primary 40G 80G  # New partition 3
sudo parted /dev/sda mkpart primary 80G 118G # New partition 4
# Create ZFS pools on new partitions
```

#### Option 1B: SystemRescue Approach
```bash
# Download SystemRescue ISO to still-fawn
# Copy to proper-raptor via MAAS or manual boot
# Perform offline resize operations
```

**Complexity**: HIGH - Requires downtime, rescue media, risk of data loss

## Approach 2: MAAS Custom Storage Layout

### Research Findings
Based on MAAS documentation and Discourse examples:

#### MAAS ZFS Limitations
- **Critical**: "MAAS does not support deploying ZFS beyond the root device"
- ZFS root is "Experimental" and limited to single partition
- Custom storage layouts have limited ZFS support

#### JSON Configuration Structure
MAAS custom storage requires commissioning script outputting to `$MAAS_STORAGE_CONFIG_FILE`:

```json
{
  "layout": {
    "sda": {
      "type": "disk",
      "ptable": "gpt", 
      "boot": true,
      "partitions": [
        {
          "name": "sda1",
          "fs": "vfat",
          "size": "512M",
          "bootable": true
        },
        {
          "name": "sda2", 
          "fs": "ext4",
          "size": "40G"
        },
        {
          "name": "sda3",
          "size": "39G",
          "fs": "unformatted"  # For ZFS pool 1
        },
        {
          "name": "sda4", 
          "size": "39G",
          "fs": "unformatted"  # For ZFS pool 2
        }
      ]
    }
  },
  "mounts": {
    "/": {"device": "sda2", "options": "noatime"},
    "/boot/efi": {"device": "sda1"}
  }
}
```

#### Implementation Steps
```bash
# 1. Create commissioning script: 45-ma90-multi-zfs-layout.sh
#!/bin/bash
# Script must run after 40-maas-01-machine-resources
# Script outputs JSON to $MAAS_STORAGE_CONFIG_FILE

# 2. Upload to MAAS via Web UI
# 3. Re-commission proper-raptor with custom layout
# 4. Deploy Ubuntu with new partition scheme
# 5. Post-deployment: Create ZFS pools on sda3, sda4, sda5
```

**Complexity**: MEDIUM - Requires re-deployment, custom scripting

## Approach 3: Loop Device Solution (Current Fallback)

### Implementation (What we started)
```bash
# Create 3 loop device-backed files with separate ZFS pools
sudo truncate -s 15G /var/lib/crucible-pool-1.img
sudo truncate -s 15G /var/lib/crucible-pool-2.img  
sudo truncate -s 15G /var/lib/crucible-pool-3.img

sudo zpool create -o ashift=12 crucible1 /var/lib/crucible-pool-1.img
sudo zpool create -o ashift=12 crucible2 /var/lib/crucible-pool-2.img
sudo zpool create -o ashift=12 crucible3 /var/lib/crucible-pool-3.img
```

**Complexity**: LOW - No downtime, immediate implementation
**Performance**: Still shares underlying disk, but provides filesystem isolation

## Recommendation: Hybrid Approach

### Phase 1: Immediate Testing (Loop Devices)
Implement loop device solution for immediate testing to validate:
- ZFS pool isolation benefits
- Crucible region performance improvements  
- Configuration and management complexity

### Phase 2: MAAS Custom Storage (Production)
If Phase 1 shows benefits:
1. Create comprehensive MAAS custom storage script
2. Test on spare MA90 or in lab environment
3. Implement on production MA90s during planned maintenance

### Phase 3: Additional MA90 Deployment  
Deploy additional MA90 sleds with proper partitioning from start
- Each sled: 3 partitions × 3 sleds = 9 separate regions
- True distributed storage with proper disk isolation

## Next Actions

### Immediate (Continue Current Session)
```bash
# Complete loop device setup for testing
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas
sudo truncate -s 15G /var/lib/crucible-pool-{1,2,3}.img
sudo zpool create -o ashift=12 crucible{1,2,3} /var/lib/crucible-pool-{1,2,3}.img
```

### Future Implementation
1. **Document complete MAAS custom storage script**
2. **Test performance comparison**: loop devices vs real partitions
3. **Validate Crucible performance** with isolated storage
4. **Create production deployment guide** for additional MA90s

## File Locations & Commands Reference

### Critical File Locations (proper-raptor.maas)
- **Current Crucible binaries**: `/home/ubuntu/crucible-downstairs`, etc.
- **Current regions**: `/crucible/regions-optimized-{1,2,3}/`  
- **Log files**: `/var/log/crucible/downstairs.log`
- **ZFS pools**: `/crucible1/`, `/crucible2/`, `/crucible3/` (planned)

### Essential Commands
```bash
# Check current disk layout
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas "lsblk -f"
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas "sudo fdisk -l /dev/sda"

# Check ZFS status
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas "sudo zpool status"
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas "sudo zfs list"

# Monitor Crucible processes  
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas "ps aux | grep crucible"
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas "ss -tln | grep 381"

# Performance testing
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas "sudo fio --name=test --rw=randwrite --bs=4k --size=100M --filename=/crucible1/test1"
```

### SSH Access Pattern
- **MA90 Storage**: `ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas`
- **Build Host**: `ssh root@still-fawn.maas` 
- **Crucible binaries location**: `/tmp/crucible/target/release/` (still-fawn)

## Conclusion

The loop device approach provides immediate disk isolation testing capabilities while maintaining system stability. MAAS custom storage offers production-quality partitioning but requires re-deployment. A hybrid approach allows validation of benefits before committing to more complex production deployment.

**Current Priority**: Complete loop device setup to test performance improvements and validate the disk isolation hypothesis before considering more invasive approaches.