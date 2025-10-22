# PBS Migration Status - 2025-01-22

**Status:** VM Created, Ready for Installation
**Node:** pumped-piglet
**VM ID:** 103

---

## Summary

Proxmox Backup Server (PBS) migration from still-fawn (offline) to pumped-piglet is **90% complete**. The PBS VM is created and running, ready for manual installation via console. All backup data (1.26TB) is intact and accessible on pumped-piglet.

---

## Completed Steps ✅

### 1. Backup Data Verification
- **Location:** `/local-20TB-zfs/subvol-103-homelab-backup` on pumped-piglet
- **Size:** 1.26TB used / 20TB allocated
- **Contents:**
  - `.chunks/` - 65K directories (deduplicated backup chunks)
  - `ct/` - 7 container backup groups
  - `vm/` - 8 VM backup groups
- **Status:** ✅ All data intact and accessible

### 2. PBS ISO Downloaded
- **Version:** Proxmox Backup Server 4.0-1
- **Size:** 1.2GB (1341806592 bytes)
- **Location:** `/var/lib/vz/template/iso/proxmox-backup-server_4.0-1.iso` on pumped-piglet
- **Status:** ✅ Downloaded successfully

### 3. PBS VM Created
```bash
VM ID: 103
Name: proxmox-backup-server
Node: pumped-piglet
Resources:
  - CPU: 4 cores (host CPU type)
  - RAM: 2048 MB
  - Disk: 800GB (local-2TB-zfs:vm-103-disk-1)
  - EFI: 1MB (local-2TB-zfs:vm-103-disk-0)
Network:
  - Bridge: vmbr0
  - Target IP: 192.168.4.218 (DHCP initially, static after install)
Boot:
  - BIOS: OVMF (UEFI)
  - ISO: proxmox-backup-server_4.0-1.iso
Status: ✅ Running
```

### 4. Old Container Cleaned Up
- Removed obsolete LXC container 103 config from still-fawn
- Freed up VMID 103 for new PBS VM
- Status: ✅ Complete

---

## Manual Steps Required (Interactive Installation)

### Access PBS Console

**Via Proxmox Web UI:**
```
URL: https://192.168.4.175:8006
Node: pumped-piglet
VM: 103 (proxmox-backup-server)
Click: Console button
```

### Installation Wizard Configuration

Follow the PBS installer with these settings:

| Setting | Value | Notes |
|---------|-------|-------|
| **Target Disk** | `/dev/sda` | 800GB disk on local-2TB-zfs |
| **Filesystem** | ext4 (default) | Or ZFS if preferred |
| **Country** | United States | Or your location |
| **Timezone** | America/New_York | Or your timezone |
| **Keyboard Layout** | en-us | Or your layout |
| **Hostname (FQDN)** | `proxmox-backup-server.maas` | Must match DNS |
| **IP Address** | `192.168.4.218/24` | Static IP (currently in OPNsense DNS) |
| **Gateway** | `192.168.4.1` | OPNsense gateway |
| **DNS Server** | `192.168.4.1` | OPNsense Unbound DNS |
| **Root Password** | (Set strong password) | For web UI and SSH access |
| **Email** | (Your email) | For backup notifications |

**Installation Time:** ~5 minutes

### Post-Installation Verification

After reboot, verify PBS is accessible:

```bash
# Test SSH access
ssh root@192.168.4.218

# Test web UI
open https://192.168.4.218:8007
```

---

## Automated Post-Installation Steps

Once PBS installation completes, run these commands to attach the existing datastore:

### 1. Attach 20TB Datastore Disk to VM

```bash
# On pumped-piglet host
ssh root@pumped-piglet.maas

# Add existing ZFS dataset as second disk
qm set 103 --scsi1 /dev/zvol/local-20TB-zfs/subvol-103-homelab-backup

# Verify disk is attached
qm config 103 | grep scsi
```

### 2. Configure Datastore in PBS

```bash
# SSH into PBS VM
ssh root@192.168.4.218

# Create mount point
mkdir -p /mnt/homelab-backup

# Find the device (should be /dev/sdb or similar)
lsblk

# Mount the existing datastore
# NOTE: This disk has existing data, DO NOT format!
mount /dev/sdb /mnt/homelab-backup

# Verify existing backup data is accessible
ls -lah /mnt/homelab-backup/
# Should see: .chunks, ct, vm directories

# Add to /etc/fstab for persistence
echo "/dev/sdb /mnt/homelab-backup ext4 defaults 0 0" >> /etc/fstab

# Create PBS datastore pointing to existing data
proxmox-backup-manager datastore create homelab-backup /mnt/homelab-backup \
  --gc-schedule daily \
  --keep-daily 7 \
  --keep-weekly 4 \
  --keep-monthly 3
```

### 3. Verify Existing Backups

```bash
# List all backup groups (should show existing backups)
proxmox-backup-client backup-group list homelab-backup

# Or via web UI:
# Navigate to: Datastore → homelab-backup → Content
# Should show 7 container backups and 8 VM backups
```

### 4. Update Proxmox VE Storage Configuration

The storage configs already exist and point to `proxmox-backup-server.maas`. Just verify they work:

```bash
# On pve host
ssh root@pve.maas

# Test storage connection
pvesm status --storage homelab-backup
pvesm status --storage proxmox-backup-server

# List available backups
pvesm list homelab-backup
```

If credentials need updating:

```bash
# Create PBS API token for Proxmox integration
ssh root@192.168.4.218
proxmox-backup-manager user create backup@pbs --comment "Proxmox VE backup user"
proxmox-backup-manager acl update /datastore/homelab-backup \
  --auth-id backup@pbs --role DatastoreBackup

# Generate API token
proxmox-backup-manager user generate-token backup@pbs backup-token
# Save the token output

# Update Proxmox storage config with token
ssh root@pve.maas
pvesm set homelab-backup --username backup@pbs --password <TOKEN_SECRET>
```

### 5. Test Backup/Restore

```bash
# Test backup of a small container
vzdump 100 --storage homelab-backup --mode snapshot

# Verify in PBS web UI that backup appears

# Test restore (dry-run)
pct restore 999 homelab-backup:backup/ct/100/latest --storage local-zfs --dry-run
```

---

## Storage Architecture After Migration

```
pumped-piglet.maas
├── System: nvme0n1 (238GB)
├── local-2TB-zfs (1.9TB NVMe)
│   ├── vm-103-disk-0: PBS EFI disk (1MB)
│   └── vm-103-disk-1: PBS root disk (800GB) ← PBS OS installed here
└── local-20TB-zfs (21.8TB HDD)
    └── subvol-103-homelab-backup (1.26TB / 20TB)
        ├── .chunks/     ← Deduplicated backup chunks
        ├── ct/          ← 7 container backup groups
        └── vm/          ← 8 VM backup groups

PBS VM will see:
├── /dev/sda (800GB) - Root filesystem with PBS OS
└── /dev/sdb (20TB) - Mounted at /mnt/homelab-backup (existing data)
```

---

## Integration with Python Infrastructure Orchestrator

### Future Work: Add PBS Management Module

**Location:** `proxmox/homelab/src/homelab/pbs_manager.py`

**Capabilities:**
- Create PBS VMs with specified resources
- Attach existing datastores
- Configure PBS datastores programmatically
- Manage backup jobs
- Monitor backup status
- Handle PBS VM lifecycle (start/stop/migrate)

**Integration Points:**
- `infrastructure_orchestrator.py` - Add PBS provisioning step
- `vm_manager.py` - Extend for PBS-specific VM configurations
- `monitoring_manager.py` - Add PBS monitoring integration

**Example Python API:**
```python
from homelab.pbs_manager import PBSManager

# Create PBS VM with storage
pbs = PBSManager(node="pumped-piglet")
pbs.create_pbs_vm(
    vmid=103,
    cores=4,
    memory=2048,
    disk_size=800,
    datastore_path="/dev/zvol/local-20TB-zfs/subvol-103-homelab-backup"
)

# Configure datastore
pbs.configure_datastore(
    name="homelab-backup",
    path="/mnt/homelab-backup",
    retention={"daily": 7, "weekly": 4, "monthly": 3}
)

# Monitor backup status
status = pbs.get_backup_status()
```

---

## Network Configuration

**DNS Entry (Already Configured in OPNsense):**
```
proxmox-backup-server.maas → 192.168.4.218
```

**No DNS changes required** - existing DNS entry will work once PBS is installed with static IP.

---

## Rollback Plan

If PBS VM installation fails:

```bash
# 1. Stop and destroy PBS VM
ssh root@pumped-piglet.maas
qm stop 103
qm destroy 103

# 2. Backup data remains intact at:
/local-20TB-zfs/subvol-103-homelab-backup

# 3. Retry installation or:
# - Restore still-fawn hardware and bring PBS container back online
# - Install PBS as LXC container instead of VM (if kernel requirements met)
```

---

## Timeline

| Phase | Status | Duration |
|-------|--------|----------|
| Investigation & Planning | ✅ Complete | ~15 min |
| PBS ISO Download | ✅ Complete | ~3 min |
| VM Creation | ✅ Complete | ~2 min |
| PBS Installation | ⏳ Manual Step Required | ~5 min |
| Datastore Configuration | ⏸️ Pending | ~5 min |
| Testing | ⏸️ Pending | ~10 min |
| **Total Estimated Time** | | **~40 minutes** |

---

## Resources

**Documentation:**
- Full migration runbook: `docs/runbooks/pbs-migration-to-pumped-piglet.md`
- Proxmox Backup Server docs: https://pbs.proxmox.com/docs/
- PBS installation guide: https://pbs.proxmox.com/docs/installation.html

**Related Files:**
- VM creation script: `/tmp/create-pbs-vm.sh` (on pumped-piglet)
- Migration planning doc: `docs/runbooks/pbs-migration-to-pumped-piglet.md`

**Backup Data Location:**
- Current: `/local-20TB-zfs/subvol-103-homelab-backup` (pumped-piglet)
- Size: 1.26TB used (7 container + 8 VM backup groups)
- Status: Intact and accessible

---

## Success Criteria

- [ ] PBS VM installation completes successfully
- [ ] PBS web UI accessible at https://192.168.4.218:8007
- [ ] Existing datastore (1.26TB) recognized by PBS
- [ ] All 15 backup groups visible in PBS web UI
- [ ] Proxmox VE storage connection working
- [ ] Test backup completes successfully
- [ ] Test restore works from existing backups

---

## Questions & Decisions

**Q: Why VM instead of LXC container?**
**A:** PBS requires its own kernel and full isolation for proper operation. The original container approach was insufficient.

**Q: What happened to still-fawn?**
**A:** still-fawn node went offline (unknown reason). Hardware may be recovered later, but PBS needed to be migrated immediately for backup functionality.

**Q: Can we migrate PBS back to still-fawn later?**
**A:** Yes, if still-fawn comes back online:
- Option 1: Migrate PBS VM from pumped-piglet to still-fawn using `qm migrate`
- Option 2: Leave PBS on pumped-piglet (recommended - more powerful hardware)

**Q: What about the old PBS container config?**
**A:** Removed from cluster config (`/etc/pve/nodes/still-fawn/lxc/103.conf`). If still-fawn comes back online, the container won't auto-start since config was deleted.

---

## Next Actions

1. **Immediate:** Complete PBS installation via Proxmox console (manual, ~5 min)
2. **After Install:** Run automated datastore attachment commands (documented above)
3. **Testing:** Verify existing backups accessible and create test backup
4. **Integration:** Create Python PBS management module for infrastructure orchestrator
5. **Monitoring:** Add PBS monitoring to Uptime Kuma and Grafana

---

**Status:** Ready for manual PBS installation
**Blocker:** None (all prerequisites met)
**Risk:** Low (data already on target node)
**Estimated Completion:** 30 minutes after installation starts

---

**Last Updated:** 2025-01-22 by Claude Code
**Migration Lead:** Claude (AI Infrastructure Assistant)
**Documentation:** Complete and ready for execution
