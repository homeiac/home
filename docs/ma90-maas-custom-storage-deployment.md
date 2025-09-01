# MA90 MAAS Custom Storage Deployment Guide

**Date**: August 31, 2025  
**System**: proper-raptor.maas (MA90 with failed live repartitioning)  
**Goal**: Deploy MA90 with custom multi-partition layout via MAAS commissioning

## Current Situation

**proper-raptor.maas is currently unbootable** after failed live root filesystem shrinking attempt. This provides the perfect opportunity to redeploy it properly using MAAS custom storage layout.

## Commissioning Script Status

### Script: `45-ma90-multi-zfs-layout.sh`
- **Location**: `C:\Users\gshiv\code\home\proxmox\homelab\scripts\45-ma90-multi-zfs-layout.sh`
- **Function**: Creates 3-partition layout optimized for single ZFS pool
- **Testing**: ✅ Validated locally with mock MAAS environment
- **Ready**: ✅ Ready for upload to MAAS

### Partition Layout Created
```
/dev/sda1  512MB   vfat     /boot/efi    (EFI System)
/dev/sda2   25GB   ext4     /            (Root filesystem)
/dev/sda3   ~90GB  unformatted           (ZFS pool for Crucible)
```

### Script Features
- ✅ **Dynamic disk detection** from MAAS machine resources
- ✅ **Proper error handling** and validation
- ✅ **JSON configuration generation** for MAAS
- ✅ **Hardware-appropriate sizing** for MA90 128GB disk
- ✅ **Logging and debugging** output for troubleshooting

## Deployment Process

### Step 1: Upload Commissioning Script to MAAS

1. **Access MAAS Web Interface**
   - Navigate to MAAS dashboard
   - Go to Settings → Commissioning scripts

2. **Upload Script**
   - Click "Upload script"
   - Select: `45-ma90-multi-zfs-layout.sh`
   - **Script name**: `45-ma90-multi-zfs-layout`
   - **Tags**: `ma90`, `storage`, `crucible`
   - **Timeout**: 300 seconds (5 minutes)

3. **Verify Upload**
   - Confirm script appears in commissioning scripts list
   - Check script runs after `40-maas-01-machine-resources`

### Step 2: Prepare MA90 for Re-commissioning

1. **Mark Machine as Failed/Broken**
   - In MAAS: proper-raptor → Actions → Mark broken
   - Reason: "Failed live repartitioning - needs redeployment"

2. **Ensure Machine is Ready State**
   - Machine status should be "Ready" before commissioning
   - If not Ready: Actions → Release → Commission

### Step 3: Commission with Custom Storage Script

1. **Start Commissioning**
   - proper-raptor → Actions → Commission
   - **Enable custom storage script**: `45-ma90-multi-zfs-layout`
   - **Additional scripts**: Keep default commissioning scripts
   - Start commissioning process

2. **Monitor Progress**
   - Watch commissioning logs for custom storage script execution
   - Look for success messages:
     ```
     MA90 Multi-ZFS Layout Commissioning Script starting...
     MAAS detected primary disk: sda
     Disk size: 119GB
     ✓ JSON validation passed
     MA90 storage layout configuration created successfully
     Layout: EFI(512M) + Root(25G) + ZFS(remaining ~90GB)
     ```

### Step 4: Deploy with Custom Layout

1. **Deploy Machine**
   - proper-raptor → Actions → Deploy
   - **OS**: Ubuntu 24.04 LTS
   - **Storage**: Custom layout (should be automatically applied)
   - Start deployment

2. **Monitor Deployment**
   - Wait for successful Ubuntu installation
   - Verify SSH access restored

## Post-Deployment Configuration

### Step 5: Create ZFS Pool on Unformatted Partition

```bash
# SSH to deployed MA90
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas

# Verify partition layout
lsblk -f
# Expected:
# sda1  vfat   FAT32 efi   /boot/efi
# sda2  ext4   1.0   root  /
# sda3                     (unformatted, ~90GB)

# Install ZFS utilities
sudo apt update && sudo apt install -y zfsutils-linux

# Create ZFS pool on sda3
sudo zpool create -o ashift=12 crucible /dev/sda3

# Verify ZFS pool
sudo zpool status crucible
sudo zfs list

# Expected output:
# NAME        SIZE  ALLOC   FREE  CKPOINT  EXPANDSZ   FRAG    CAP  DEDUP    HEALTH  ALTROOT
# crucible   89.5G    96K  89.4G        -         -     0%     0%  1.00x    ONLINE  -
```

### Step 6: Deploy Crucible on ZFS Storage

```bash
# Transfer Crucible binaries (from still-fawn)
# Binaries are in: /tmp/crucible/target/release/
scp root@still-fawn.maas:/tmp/crucible-bins.tar.gz ~/
tar xzf crucible-bins.tar.gz

# Make binaries executable
chmod +x crucible-downstairs crucible-agent dsc crucible-nbd-server

# Create Crucible region on ZFS
UUID=$(python3 -c 'import uuid; print(uuid.uuid4())')
echo "Creating region with UUID: $UUID"

./crucible-downstairs create \
    --data /crucible/regions \
    --uuid $UUID \
    --extent-size 131072 \
    --extent-count 100

# Start downstairs service
nohup ./crucible-downstairs run \
    --data /crucible/regions \
    --address 0.0.0.0 \
    --port 3810 \
    > /var/log/crucible/downstairs.log 2>&1 &

# Verify service
ps aux | grep crucible-downstairs
ss -tln | grep 3810
```

## Expected Results

### Partition Layout Verification
```bash
# Disk layout
$ lsblk
NAME   MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
sda      8:0    0 119.2G  0 disk 
├─sda1   8:1    0   512M  0 part /boot/efi
├─sda2   8:2    0    25G  0 part /
└─sda3   8:3    0  93.7G  0 part 

# ZFS pool
$ sudo zpool status
  pool: crucible
 state: ONLINE
config:
        NAME        STATE     READ WRITE CKSUM
        crucible    ONLINE       0     0     0
          sda3      ONLINE       0     0     0
```

### Storage Capacity
- **Total Disk**: 119GB (MA90 M.2 SATA)
- **EFI Boot**: 512MB
- **Root System**: 25GB (adequate for OS + Crucible binaries)
- **ZFS Pool**: ~94GB (maximum storage for Crucible regions)

## Troubleshooting

### Script Upload Issues
```bash
# If script upload fails
1. Check script file permissions (must be executable)
2. Verify script name doesn't conflict with existing scripts
3. Check MAAS logs for upload errors
```

### Commissioning Failures
```bash
# Check commissioning logs
maas admin events query hostname=proper-raptor

# Script-specific logs
# Look for "45-ma90-multi-zfs-layout" in commissioning output
# Check for JSON validation errors or disk detection issues
```

### Deployment Issues
```bash
# If deployment fails to use custom storage
1. Verify commissioning completed successfully
2. Check that custom storage configuration was created
3. Try manual deployment with explicit storage configuration
```

### Post-Deployment Verification
```bash
# Verify partition sizes
df -h /
sudo fdisk -l /dev/sda

# Check ZFS pool health
sudo zpool status -v
sudo zfs get all crucible
```

## File Locations & Commands

### Critical Files
- **Commissioning script**: `C:\Users\gshiv\code\home\proxmox\homelab\scripts\45-ma90-multi-zfs-layout.sh`
- **Crucible binaries**: `/tmp/crucible/target/release/` (still-fawn)
- **ZFS mount point**: `/crucible/` (proper-raptor post-deployment)
- **Logs**: `/var/log/crucible/downstairs.log`

### SSH Access
- **MA90 (post-deployment)**: `ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas`
- **Build host**: `ssh root@still-fawn.maas`

### Key Commands
```bash
# MAAS machine status
maas admin machines read | jq '.[] | select(.hostname=="proper-raptor") | {hostname, status_name, storage}'

# ZFS operations
sudo zpool status crucible
sudo zfs list
sudo zpool list -v

# Crucible operations  
ps aux | grep crucible
ss -tln | grep 381
```

## Next Steps After Successful Deployment

1. **Deploy additional MA90 sleds** using same commissioning script
2. **Configure 3-way replication** across multiple MA90s
3. **Implement systemd services** for Crucible processes
4. **Set up monitoring** and alerting for storage health
5. **Test NBD integration** with Proxmox VMs

## Success Criteria

✅ **MAAS custom storage script successfully uploaded and executed**  
✅ **MA90 deployed with 3-partition layout (EFI + Root + ZFS)**  
✅ **ZFS pool created on dedicated 90GB partition**  
✅ **Crucible downstairs service running on dedicated storage**  
✅ **SSH access restored and system stable**  

This completes the transition from failed live repartitioning to proper MAAS-managed custom storage deployment, providing the foundation for distributed Crucible storage across multiple MA90 sleds.