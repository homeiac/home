# MA90 Crucible Deployment - Complete Working Guide

**Date**: September 1, 2025
**Status**: ON HOLD - proper-raptor offline, needs physical check
**Last Updated**: January 25, 2026
**Performance**: 4K blocks = 60+ MB/s (vs 512B blocks = 6 MB/s)

## ⚠️ PROJECT STATUS (January 2026)

**Current State**: Project on hold due to:
1. **proper-raptor.maas (192.168.4.189) is OFFLINE** - needs physical power-on/network check
2. **3-downstairs requirement** - single sled deployment was blocked by Crucible's quorum requirement
3. **Never fully operational** - downstairs deployed, but upstairs/NBD integration never completed

**Note**: The `crucible-storage` directory on fun-bedbug (`/mnt/crucible-storage`) is NOT connected to Crucible - it's just a local directory with a misleading name.

**To Resume**:
1. Physically check proper-raptor (may be labeled as grand-python)
2. Power on and verify network connectivity
3. Either deploy 2 more MA90 sleds OR run 3 downstairs on single sled
4. Complete upstairs/NBD integration

---

## 🚀 Quick Start Prerequisites

### **Required Before Starting:**
1. **SSH Key Setup**: Ensure `~/.ssh/id_ed25519_pve` key has access to MA90 sleds
2. **Crucible Binaries**: Available on still-fawn at `/tmp/crucible/target/release/`
3. **MAAS Access**: Upload commissioning script capability
4. **Network Access**: 2.5GbE connectivity to MA90 storage sleds

### **SSH Key Access Validation:**
```bash
# Test SSH access to MA90 sled
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas "whoami && hostname"
# Expected output: ubuntu + hostname

# Test SSH access to build host  
ssh root@still-fawn.maas "ls -la /tmp/crucible/target/release/crucible-downstairs"
# Expected: crucible-downstairs binary file
```

## 🚨 CRITICAL LIMITATIONS

### **Single-Sled Testing Not Supported**
**CRUCIBLE REQUIRES MINIMUM 3 DOWNSTAIRS FOR TESTING** - Cannot test with single MA90 sled!
- ❌ **1 downstairs**: Crucible upstairs/NBD fails to start
- ✅ **3 downstairs**: Required for any Crucible testing (can be on same sled)
- 📋 **Minimum deployment**: 3 MA90 sleds OR 3 downstairs processes on single sled

### **Performance Requirements**
**NEVER USE 512-BYTE BLOCKS** - Performance is 10x worse than 4K blocks!
- ❌ **512B blocks**: 6-11 MB/s  
- ✅ **4K blocks**: 60+ MB/s

## Architecture Overview

```
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   Compute Hosts     │    │    Storage Sleds    │    │   MAAS Controller   │
│   (still-fawn)      │    │   (proper-raptor)   │    │   (192.168.4.53)   │
│                     │    │                     │    │                     │
│  ┌───────────────┐  │    │  ┌───────────────┐  │    │  ┌───────────────┐  │
│  │ Crucible      │  │    │  │ Crucible      │  │    │  │ Custom Storage │  │
│  │ Upstairs      │◄─┼────┼─►│ Downstairs    │  │    │  │ Scripts        │  │
│  │ (clients)     │  │    │  │ Port: 3810    │  │    │  │               │  │
│  └───────────────┘  │    │  │ ZFS-backed    │  │    │  └───────────────┘  │
└─────────────────────┘    │  │ 4K blocks     │  │    └─────────────────────┘
                           │  └───────────────┘  │
                           │                     │
                           │  Disk Layout:       │
                           │  sda1: 512M EFI     │
                           │  sda2: 25G Root     │
                           │  sda3: 91.6G ZFS    │
                           └─────────────────────┘
```

## MAAS Custom Storage Script

### Working Script: `45-ma90-multi-zfs-layout-v2`

**Location**: Upload to MAAS via web interface  
**Critical**: Remove `"fs": "unformatted"` (causes commissioning failure)

```python
#!/usr/bin/env python3
# --- Start MAAS 1.0 script metadata ---
# name: 45-ma90-multi-zfs-layout-v2
# title: MA90 Multi-ZFS Storage Layout v2
# description: Create EFI + Root + ZFS partition layout for MA90 Crucible storage
# script_type: commissioning
# timeout: 300
# --- End MAAS 1.0 script metadata ---

import json
import os
import sys

def read_json_file(path):
    """Read and parse JSON file safely"""
    try:
        with open(path) as fd:
            return json.load(fd)
    except OSError as e:
        sys.exit(f"Failed to read {path}: {e}")
    except json.JSONDecodeError as e:
        sys.exit(f"Failed to parse {path}: {e}")

def write_json_file(path, data):
    """Write JSON data to file safely"""
    try:
        with open(path, 'w') as fd:
            json.dump(data, fd, indent=2)
    except OSError as e:
        sys.exit(f"Failed to write {path}: {e}")

# Load hardware resources from MAAS
print("MA90 Multi-ZFS Layout Commissioning Script v2 starting...")

if 'MAAS_RESOURCES_FILE' not in os.environ:
    sys.exit("ERROR: MAAS_RESOURCES_FILE environment variable not set")

resources_file = os.environ['MAAS_RESOURCES_FILE']
print(f"Reading MAAS resources from: {resources_file}")

# Load the hardware data
hardware = read_json_file(resources_file)

# Extract disk information
disks = hardware.get('resources', {}).get('storage', {}).get('disks', [])
if not disks:
    sys.exit("ERROR: No disks found in MAAS resources")

# Find the primary disk (MA90 has ~128GB M.2 SATA)
primary_disk = None
for disk in disks:
    # Skip virtual/removable drives  
    if 'Virtual' in disk.get("model", "") or disk.get('removable', False):
        continue
    
    # MA90 disk size range
    disk_size_gb = disk.get('size', 0) / (1024 * 1024 * 1024)
    if disk_size_gb > 100 and disk_size_gb < 200:
        primary_disk = disk
        break

# Fallback to first non-removable disk
if not primary_disk:
    for disk in disks:
        if not disk.get('removable', False):
            primary_disk = disk
            break

if not primary_disk:
    sys.exit("ERROR: No suitable disk found for MA90 storage layout")

disk_id = primary_disk['id']
disk_size = primary_disk['size']
disk_size_gb = disk_size / (1024 * 1024 * 1024)

print(f"Selected disk: {disk_id}")
print(f"Disk size: {disk_size_gb:.1f}GB ({disk_size} bytes)")
print(f"Disk model: {primary_disk.get('model', 'Unknown')}")

# Calculate partition sizes (MAAS uses 1000-based)
efi_size_bytes = 512 * 1000 * 1000
root_size_bytes = 25 * 1000 * 1000 * 1000
zfs_size_bytes = disk_size - efi_size_bytes - root_size_bytes

# Convert to MAAS size format
efi_size = "512M"
root_size = "25G" 
zfs_size_gb = int(zfs_size_bytes / (1000 * 1000 * 1000))
zfs_size = f"{zfs_size_gb}G"

print(f"Partition plan: EFI({efi_size}) + Root({root_size}) + ZFS({zfs_size})")

# Create storage layout configuration
storage_layout = {
    "layout": {
        disk_id: {
            "type": "disk",
            "ptable": "gpt",
            "boot": True,
            "partitions": [
                {
                    "name": f"{disk_id}1",
                    "fs": "fat32",
                    "size": efi_size,
                    "bootable": True
                },
                {
                    "name": f"{disk_id}2", 
                    "fs": "ext4",
                    "size": root_size
                },
                {
                    "name": f"{disk_id}3",
                    "size": zfs_size
                    # 🚨 CRITICAL: No "fs" field = unformatted partition
                    # NEVER add "fs": "unformatted" - causes failure!
                }
            ]
        }
    },
    "mounts": {
        "/": {
            "device": f"{disk_id}2",
            "options": "noatime,errors=remount-ro"
        },
        "/boot/efi": {
            "device": f"{disk_id}1"
        }
    }
}

# Add storage-extra to hardware resources
hardware["storage-extra"] = storage_layout

# Write back to MAAS_RESOURCES_FILE
print(f"Adding custom storage layout to {resources_file}")
write_json_file(resources_file, hardware)

print("SUCCESS: MA90 Multi-ZFS storage layout configuration added successfully")
print(f"Layout: EFI({efi_size}) + Root({root_size}) + ZFS({zfs_size} for Crucible)")

sys.exit(0)
```

## Deployment Process

### Step 1: Upload Script to MAAS
1. **MAAS Web Interface**: http://192.168.4.53:5240/MAAS/
2. **Settings → Commissioning scripts → Upload**
3. **Script name**: `45-ma90-multi-zfs-layout-v2`
4. **Script type**: `commissioning`
5. **Timeout**: `300`

### Step 2: Commission MA90 with Custom Script
```bash
# Get system ID
maas admin machines read | grep -A 5 -B 5 "proper-raptor"

# Commission with custom script
maas admin machine commission xx4ebf commissioning_scripts=45-ma90-multi-zfs-layout-v2

# Wait for "Ready" status
```

### Step 3: Deploy Ubuntu with Custom Storage
1. **Actions → Deploy**
2. **OS**: Ubuntu 24.04 LTS
3. **Storage Layout**: Custom (should work without error now)
4. **Deploy**

**Expected Result**:
```
sda1  vfat   512MB  /boot/efi  (EFI boot)
sda2  ext4    25GB  /          (Root filesystem)
sda3          91GB              (Unformatted for ZFS)
```

## Post-Deployment ZFS & Crucible Setup

### SSH Access
```bash
# Add SSH key to authorized_keys first
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG1SBlNlBbwmKwGfncXLCjOR4eUpqPZZEbelk6TQU7c2 claude-code@windows

# SSH to deployed MA90
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas
```

### Install ZFS
```bash
sudo apt update && sudo apt install -y zfsutils-linux
```

### Create ZFS Pool
```bash
# Fix permissions first
sudo chown ubuntu:ubuntu /crucible
sudo chmod 755 /crucible

# Create ZFS pool on dedicated partition
sudo zpool create -o ashift=12 crucible /dev/sda3

# Verify
sudo zpool status
sudo zfs list
# Expected: ~91GB available on /crucible
```

### Deploy Crucible Binaries
```bash
# CRITICAL: Binaries are compiled on still-fawn at /tmp/crucible/target/release/
# First, create tarball on still-fawn (if not already done)
ssh root@still-fawn.maas "cd /tmp/crucible/target/release && tar czf /tmp/crucible-bins.tar.gz crucible-downstairs crucible-agent dsc crucible-nbd-server"

# Transfer from still-fawn to MA90 sled
scp -i ~/.ssh/id_ed25519_pve root@still-fawn.maas:/tmp/crucible-bins.tar.gz ~/

# Extract and prepare binaries
tar xzf crucible-bins.tar.gz
chmod +x crucible-downstairs crucible-agent dsc crucible-nbd-server

# Verify binaries are executable
ls -la crucible-*
```

### Create Optimized Crucible Region
```bash
# 🚨 CRITICAL: Use 4K blocks for 10x better performance!
UUID=$(python3 -c "import uuid; print(uuid.uuid4())")
echo "Creating region with UUID: $UUID"

# Create with 4K block size (NOT 512!)
./crucible-downstairs create \
    --data /crucible/regions \
    --uuid $UUID \
    --block-size 4096 \
    --extent-size 32768 \
    --extent-count 100

# Verify configuration
cat /crucible/regions/region.json | grep -A 5 block_size
# Must show: "block_size": 4096
```

### Start Downstairs Service
```bash
# Create log directory
sudo mkdir -p /var/log/crucible
sudo chown ubuntu:ubuntu /var/log/crucible

# Start service
nohup ./crucible-downstairs run \
    --data /crucible/regions \
    --address 0.0.0.0 \
    --port 3810 \
    > /var/log/crucible/downstairs.log 2>&1 &

# Verify running
ps aux | grep crucible
ss -tln | grep 3810
```

## Performance Validation

### Test I/O Performance
```bash
# Test 4K block performance (should show 60+ MB/s)
sudo fio --name=crucible-test \
    --rw=randwrite \
    --bs=4k \
    --size=1G \
    --filename=/crucible/test-performance \
    --direct=1

# Clean up test file
sudo rm -f /crucible/test-performance
```

## Working File Locations & Access Patterns

### Development Machine (Windows)
- **Working commissioning script**: `C:\Users\gshiv\code\home\proxmox\homelab\scripts\45-ma90-multi-zfs-layout-fixed.sh`
- **SSH private key**: `~/.ssh/id_ed25519_pve` (**CRITICAL** for MA90 access)
- **Documentation**: `docs/ma90-crucible-deployment-complete-guide.md` (this file)

### MAAS Server (192.168.4.53)
- **Commissioning script**: Upload `45-ma90-multi-zfs-layout-fixed.sh` via web interface
- **System ID**: `xx4ebf` (proper-raptor example)
- **Access**: Web interface + `maas admin` CLI

### Still-fawn.maas (Build Host) - **CRITICAL: Source of Binaries**
- **Crucible source code**: `/tmp/crucible/` (cloned from GitHub)
- **Compiled binaries**: `/tmp/crucible/target/release/` (crucible-downstairs, crucible-agent, etc.)
- **Binary archive**: `/tmp/crucible-bins.tar.gz` (for transfer to MA90 sleds)
- **SSH access**: `ssh root@still-fawn.maas`

### MA90 Storage Sleds (e.g., proper-raptor.maas)
- **ZFS pool**: `/crucible/` (91.6GB dedicated storage)
- **Transferred binaries**: `/home/ubuntu/crucible-*` (executable)
- **Region data**: `/crucible/regions/` (ZFS-backed storage)
- **Logs**: `/var/log/crucible/downstairs.log`
- **Service port**: `3810` (single sled) or `3810,3811,3812` (testing setup)
- **SSH access**: `ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas`

### Key Command Patterns for New Sessions
```bash
# 1. Verify SSH access to MA90
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas "whoami && hostname"

# 2. Transfer binaries from still-fawn
scp -i ~/.ssh/id_ed25519_pve root@still-fawn.maas:/tmp/crucible-bins.tar.gz ~/

# 3. Check current Crucible status
ssh -i ~/.ssh/id_ed25519_pve ubuntu@proper-raptor.maas "ps aux | grep crucible"
```

## Common Errors & Solutions

### Error: "Unknown filesystem type 'unformatted'"
**Cause**: Adding `"fs": "unformatted"` to partition definition  
**Fix**: Remove the `"fs"` field entirely for unformatted partitions

### Error: "No custom storage layout configuration found"
**Cause**: Trying to use "Custom" layout before commissioning script runs  
**Fix**: Commission with custom script first, then deploy

### Error: "Permission denied (os error 13)"
**Cause**: ZFS mount point owned by root  
**Fix**: `sudo chown ubuntu:ubuntu /crucible`

### Poor Performance (6 MB/s)
**Cause**: Using 512-byte block size  
**Fix**: Use `--block-size 4096` for 10x better performance

## System Information

### Hardware
- **Model**: ATOPNUC MA90
- **CPU**: AMD A9-9400 (2 cores, 4 threads)
- **RAM**: 8GB DDR4
- **Storage**: 128GB M.2 SATA SSD
- **Network**: 1Gbps (2.5GbE capable)

### Software
- **OS**: Ubuntu 24.04 LTS
- **ZFS**: 2.2.2
- **Crucible**: Built from source (latest)

## Next Steps

### 💡 **BUDGET-FRIENDLY TESTING STRATEGY**
With only 1 downstairs process, Crucible requires 3 total downstairs for functionality:
- Crucible upstairs uses 3-way quorum for consensus-based operations
- NBD server needs minimum 3 downstairs targets to start
- **Solution**: Add 2 more downstairs processes (same sled = $30 testing vs 3 sleds = $90)

### **Required Next Steps for Testing:**

**Option A: Deploy 2 Additional MA90 Sleds (Production Fault Tolerance)**
1. **Deploy 2 more MA90 sleds** using this exact process
2. **Configure each with 1 downstairs** on port 3810
3. **Test true 3-way distributed replication** across 3 separate sleds
4. **Benefits**: Hardware fault tolerance, geographic distribution, 3x performance scaling

**Option B: Add 2 More Downstairs to Current Sled (Cost-Effective Testing)**  

**💡 SMART BUDGET APPROACH - Test full Crucible functionality for $30**
- **Perfect for Learning**: Understand all Crucible features without expensive hardware
- **Complete Testing**: NBD integration, replication, upstairs/downstairs communication
- **Development Platform**: Ideal for experimentation and proof-of-concept work
- **Upgrade Ready**: Easy migration to 3-sled production setup when needed

1. **Create 2 additional regions** on proper-raptor (see NBD guide)
2. **Start downstairs on ports 3811, 3812**
3. **Test complete 3-downstairs functionality** on single sled

### **After 3 Downstairs Available:**
4. **Test NBD integration** with Proxmox VMs (see `docs/crucible-proxmox-nbd-integration-guide.md`)
5. **Set up systemd services** for persistent operation
6. **Monitor performance** and storage health

---

**⚠️ REMEMBER**: Always use 4K blocks, never reinvent the MAAS script, and document everything!