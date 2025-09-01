# MA90 Crucible Storage Scripts

## Working Scripts for MA90 Deployment

### MAAS Commissioning Script
- **File**: `45-ma90-multi-zfs-layout-fixed.sh`
- **Purpose**: Creates custom 3-partition layout for MA90 via MAAS
- **Status**: ✅ TESTED AND WORKING
- **Upload to**: MAAS web interface as `45-ma90-multi-zfs-layout-v2`

### Key Features
- **Partition Layout**: EFI (512M) + Root (25G) + ZFS (remaining ~91G)
- **Fixed**: Removes `"fs": "unformatted"` that caused commissioning failures
- **Hardware Detection**: Automatically finds MA90's 128GB M.2 SATA disk

### Critical Notes
- ❌ **NEVER add** `"fs": "unformatted"` to JSON - causes MAAS failure
- ✅ **Omit fs field** entirely for unformatted partitions
- ✅ **Test with mock data** before uploading to MAAS

### Deployment Workflow
1. Upload script to MAAS
2. Commission MA90 with script enabled  
3. Deploy Ubuntu 24.04 with "Custom" storage layout
4. Create ZFS pool on `/dev/sda3`
5. Deploy Crucible with **4K blocks** (not 512B!)

## Performance Critical Settings

### Crucible Region Creation
```bash
# ✅ CORRECT - High Performance (60+ MB/s)
./crucible-downstairs create \
    --data /crucible/regions \
    --uuid <UUID> \
    --block-size 4096 \
    --extent-size 32768 \
    --extent-count 100

# ❌ WRONG - Poor Performance (6 MB/s)
./crucible-downstairs create \
    --data /crucible/regions \
    --uuid <UUID> \
    --extent-size 131072 \
    --extent-count 100
    # Missing --block-size 4096 = defaults to 512B
```

### File Locations
- **Working script**: `proxmox/homelab/scripts/45-ma90-multi-zfs-layout-fixed.sh`
- **Documentation**: `docs/ma90-crucible-deployment-complete-guide.md`
- **Test results**: All documented in guide above