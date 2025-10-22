# Proxmox Backup Server Migration: still-fawn → pumped-piglet

**Date:** 2025-01-22
**Status:** Planning Phase
**Objective:** Restore PBS functionality on pumped-piglet after still-fawn went offline

---

## Current Situation Analysis

### PBS Container Configuration (LXC 103 on still-fawn)

```bash
# From /etc/pve/nodes/still-fawn/lxc/103.conf

Container ID: 103
Hostname: proxmox-backup-server
IP Address: 192.168.4.218 (DHCP)
MAC: BC:24:11:C2:D1:C8

Resources:
- CPU: 4 cores
- RAM: 2048 MB
- Swap: 512 MB

Storage:
- Root FS: local-2TB-zfs:subvol-103-disk-0 (800GB) → ON STILL-FAWN ❌
- Data Mount: local-20TB-zfs:subvol-103-homelab-backup (20TB) → ON PUMPED-PIGLET ✅

Network: vmbr0, DHCP
Type: Unprivileged container
Tags: backup, community-script
```

### Storage Analysis

**Pumped-Piglet ZFS Pools:**
```
NAME                SIZE   USED   FREE   HEALTH
local-20TB-zfs      21.8T  3.38T  18.4T  ONLINE  ← PBS data here!
local-2TB-zfs       1.86T  42.3G  1.82T  ONLINE  ← Can host PBS root
```

**PBS Datastore Status:**
```bash
# /local-20TB-zfs/subvol-103-homelab-backup
Total Size: 20TB
Used: 1.26TB (7%)
Available: 18.3TB

Contents:
- .chunks/     (65K directories - deduplicated backup chunks)
- .lock        (datastore lock file)
- ct/          (container backups - 7 directories)
- vm/          (VM backups - 8 directories)
```

**Data is INTACT!** ✅ All backup data accessible on pumped-piglet.

### Problem Summary

| Component | Location | Status |
|-----------|----------|--------|
| **PBS Root FS** | still-fawn (local-2TB-zfs) | ❌ Offline/Inaccessible |
| **PBS Data** | pumped-piglet (local-20TB-zfs) | ✅ Online & Intact |
| **still-fawn Node** | Cluster | ❌ Offline |
| **pumped-piglet Node** | Cluster | ✅ Online (12 cores, 62GB RAM) |

---

## Migration Options

### Option 1: Bring still-fawn Back Online (Simplest)

**Pros:**
- No configuration changes needed
- PBS will boot and reconnect automatically
- Zero data migration

**Cons:**
- Requires physical access to still-fawn hardware
- Unknown why still-fawn went offline
- Doesn't improve resilience

**Steps:**
```bash
# 1. Physical inspection
# - Check power, network cables
# - Check BIOS/boot issues
# - Review server logs

# 2. Once online, verify PBS
ssh root@still-fawn.maas
pct start 103
pct status 103

# 3. Test PBS access
curl -k https://192.168.4.218:8007
```

**Recommendation:** Try this first if still-fawn hardware is accessible.

---

### Option 2: Migrate PBS Container to pumped-piglet (Recommended)

**Pros:**
- Preserves PBS configuration and certificates
- Reuses existing datastore without reconfiguration
- Consolidates infrastructure on most powerful node

**Cons:**
- Requires root FS migration (800GB)
- Need to update container config
- Some downtime required

**Migration Steps:**

#### Phase 1: Preparation

```bash
# 1. Verify PBS data integrity on pumped-piglet
ssh root@pumped-piglet.maas
ls -lah /local-20TB-zfs/subvol-103-homelab-backup/
# Should see: .chunks/, ct/, vm/ directories

# 2. Check available space for root FS
zfs list local-2TB-zfs
# Need: 800GB free (currently 1.82TB available ✅)

# 3. Backup PBS configuration (if still-fawn accessible)
# If still-fawn comes up temporarily:
ssh root@still-fawn.maas
pct snapshot 103 pre-migration
pct snapshot 103 pre-migration-backup
```

#### Phase 2: Root Filesystem Migration

**Method A: If still-fawn is accessible**

```bash
# 1. Stop PBS container on still-fawn
ssh root@still-fawn.maas
pct stop 103

# 2. Send ZFS snapshot to pumped-piglet
zfs snapshot local-2TB-zfs/subvol-103-disk-0@migration
zfs send local-2TB-zfs/subvol-103-disk-0@migration | \
  ssh root@pumped-piglet.maas "zfs receive local-2TB-zfs/subvol-103-disk-0"

# 3. Verify received snapshot
ssh root@pumped-piglet.maas
zfs list | grep subvol-103
```

**Method B: If still-fawn is inaccessible (Create New)**

Since still-fawn is offline and root FS is inaccessible, we need Option 3 (fresh install).

---

### Option 3: Fresh PBS Install on pumped-piglet (Most Practical)

**Pros:**
- No dependency on still-fawn hardware
- Clean installation with latest PBS version
- Can reuse existing datastore with all backups

**Cons:**
- Need to reconfigure PBS users, certificates, backup jobs
- Brief interruption to backup schedule

**Implementation Steps:**

#### Step 1: Install PBS on pumped-piglet

```bash
# 1. Install PBS using Proxmox Helper Scripts
ssh root@pumped-piglet.maas

# Download and run PBS installation script
bash -c "$(wget -qLO - https://github.com/community-scripts/ProxmoxVE/raw/main/ct/proxmox-backup-server.sh)"

# Follow prompts:
# - Container ID: 103 (reuse same ID)
# - Cores: 4
# - RAM: 2048 MB
# - Disk Size: 800 GB (match original)
# - Network: Bridge vmbr0
# - IP: Static 192.168.4.218 (or keep DHCP and update DNS)
# - Storage: local-2TB-zfs (for root FS)

# IMPORTANT: DO NOT create new datastore during install
```

#### Step 2: Configure Network (Static IP)

```bash
# If installed with DHCP, set static IP to match DNS
pct enter 103

# Edit network config
cat > /etc/network/interfaces <<EOF
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.4.218
    netmask 255.255.255.0
    gateway 192.168.4.1
    dns-nameservers 192.168.4.1
EOF

# Restart networking
systemctl restart networking
exit

# Update MAAS DNS if needed (already points to 192.168.4.218)
```

#### Step 3: Mount Existing Datastore

```bash
# 1. Stop PBS container
pct stop 103

# 2. Add existing datastore mount point to container config
# Edit /etc/pve/lxc/103.conf
cat >> /etc/pve/lxc/103.conf <<EOF
mp1: local-20TB-zfs:subvol-103-homelab-backup,mp=/mnt/homelab-backup,backup=1,size=0T
EOF

# 3. Start container
pct start 103

# 4. Verify mount inside container
pct enter 103
df -h | grep homelab-backup
ls -la /mnt/homelab-backup/
# Should see: .chunks, ct, vm directories with existing backups
```

#### Step 4: Configure PBS Datastore

```bash
# 1. Access PBS web interface
open https://192.168.4.218:8007

# Login with root credentials (set during installation)

# 2. Add existing datastore
# GUI: Administration → Storage/Disks → Directory
# - Name: homelab-backup
# - Path: /mnt/homelab-backup
# - GC Schedule: daily
# - Prune Schedule: keep-daily=7, keep-weekly=4, keep-monthly=3

# OR via CLI:
pct enter 103
proxmox-backup-manager datastore create homelab-backup /mnt/homelab-backup
proxmox-backup-manager datastore update homelab-backup \
  --gc-schedule "daily" \
  --prune-schedule "daily" \
  --keep-daily 7 \
  --keep-weekly 4 \
  --keep-monthly 3
exit
```

#### Step 5: Verify Existing Backups

```bash
# 1. Check datastore from PBS CLI
pct enter 103
proxmox-backup-manager datastore list
proxmox-backup-client backup-group list homelab-backup

# 2. Web interface verification
# Navigate to: Datastore → homelab-backup → Content
# Should show all existing VM/CT backups with dates

# Expected backups:
# - 7 container backup groups (ct/)
# - 8 VM backup groups (vm/)
```

#### Step 6: Recreate Backup Jobs

```bash
# From Proxmox VE web interface:
# Datacenter → Backup → Add

# Example job configuration:
# - Storage: homelab-backup
# - Schedule: Daily 02:00
# - Selection mode: All
# - Retention: keep-daily=7, keep-weekly=4, keep-monthly=3
# - Notification: Email

# OR via CLI on PVE:
pvesh create /cluster/backup --storage homelab-backup \
  --schedule "0 2 * * *" \
  --mode snapshot \
  --all 1 \
  --compress zstd \
  --prune-backups "keep-daily=7,keep-weekly=4,keep-monthly=3"
```

#### Step 7: Update Proxmox Storage Config

```bash
# The storage configs already exist and point to the right server!
# From earlier investigation:

# homelab-backup storage:
# - Server: proxmox-backup-server.maas (192.168.4.218)
# - Datastore: homelab-backup
# - Retention: keep-daily=7, keep-weekly=4, keep-monthly=3

# proxmox-backup-server storage:
# - Server: proxmox-backup-server.maas (192.168.4.218)
# - Datastore: pve-backup
# - Retention: keep-all=1

# Verify storage is working:
ssh root@pve.maas
pvesh get /storage/homelab-backup
pvesm status --storage homelab-backup
```

#### Step 8: Configure PBS Users and Permissions

```bash
pct enter 103

# 1. Create backup user for Proxmox integration
proxmox-backup-manager user create backup@pbs --comment "Proxmox VE backup user"

# 2. Set password
proxmox-backup-manager user update backup@pbs --password <PASSWORD>

# 3. Grant permissions
proxmox-backup-manager acl update /datastore/homelab-backup \
  --auth-id backup@pbs --role DatastoreBackup

# 4. Create API token (recommended over password)
proxmox-backup-manager user generate-token backup@pbs backup-token

# Save the token output for Proxmox integration
```

#### Step 9: Update Proxmox VE Storage Credentials

```bash
# Update storage configuration with new credentials
# GUI: Datacenter → Storage → homelab-backup → Edit
# - Username: backup@pbs
# - Password: (API token or password from Step 8)

# OR via CLI:
pvesm set homelab-backup \
  --username backup@pbs \
  --password <TOKEN_SECRET>

# Test connection
pvesm status --storage homelab-backup
```

#### Step 10: Test Backup/Restore

```bash
# 1. Test backup of a small VM/CT
vzdump 100 --storage homelab-backup --mode snapshot

# 2. Verify backup appears in PBS
open https://192.168.4.218:8007
# Check: Datastore → homelab-backup → Content

# 3. Test restore (dry-run)
qmrestore homelab-backup:backup/vm/100/latest 999 --storage local-zfs --dryrun

# 4. Verify existing backups are accessible
# Try browsing old backups from the web interface
```

---

## Post-Migration Verification Checklist

- [ ] PBS web interface accessible at https://192.168.4.218:8007
- [ ] Datastore "homelab-backup" shows 1.26TB used
- [ ] All 7 container backups visible in web interface
- [ ] All 8 VM backups visible in web interface
- [ ] Proxmox VE can list backups from storage
- [ ] Test backup job completes successfully
- [ ] Test restore from old backup works
- [ ] Prune policy is configured correctly
- [ ] GC (garbage collection) runs successfully
- [ ] Email notifications configured (if needed)
- [ ] API tokens documented for automation

---

## DNS Configuration

**Current DNS Entry (OPNsense Unbound):**
```
proxmox-backup-server.maas → 192.168.4.218
```

**Action:** Verify DNS resolves correctly after migration:
```bash
nslookup proxmox-backup-server.maas
# Should return: 192.168.4.218

# Test from all nodes:
for node in pve chief-horse fun-bedbug pumped-piglet; do
  echo "=== $node ==="
  ssh root@${node}.maas "host proxmox-backup-server.maas"
done
```

**If DNS needs update:**
- OPNsense → Services → Unbound DNS → Host Overrides
- Update `proxmox-backup-server.maas` → `192.168.4.218`

---

## Storage Architecture After Migration

```
pumped-piglet.maas (12 cores, 62GB RAM)
├── Root System: nvme0n1 (238GB)
├── ZFS Pool: local-2TB-zfs (1.9TB NVMe)
│   └── PBS Root FS: subvol-103-disk-0 (800GB)
└── ZFS Pool: local-20TB-zfs (21.8TB HDD)
    ├── PBS Datastore: subvol-103-homelab-backup (1.26TB used / 20TB allocated)
    │   ├── .chunks/     (deduplicated backup chunks)
    │   ├── ct/          (7 container backup groups)
    │   └── vm/          (8 VM backup groups)
    └── K3s Storage: Available capacity for VM images
```

**Benefits:**
- All PBS infrastructure on single, most powerful node
- Fast root FS on NVMe (better PBS performance)
- Large datastore on 20TB HDD (cost-effective)
- pumped-piglet has resources to spare (9.8% CPU utilization)

---

## Rollback Plan

**If migration fails:**

1. **Revert container config:**
```bash
# Remove new container on pumped-piglet
pct stop 103
pct destroy 103

# Remove storage mount config
vim /etc/pve/lxc/103.conf  # Remove mp1 line
```

2. **Restore still-fawn access:**
```bash
# If still-fawn comes back online
ssh root@still-fawn.maas
pct start 103
pct status 103
```

3. **Data preservation:**
- Original PBS data remains intact at `/local-20TB-zfs/subvol-103-homelab-backup`
- No data deleted during migration process
- Can always create new PBS and reattach datastore

---

## Estimated Downtime

**Option 1 (Restore still-fawn):**
- 15-30 minutes (hardware troubleshooting)
- 5 minutes (PBS startup)

**Option 2 (Migrate container):**
- 2-4 hours (ZFS send/receive 800GB)
- 30 minutes (configuration)

**Option 3 (Fresh install - RECOMMENDED):**
- 15 minutes (PBS installation)
- 15 minutes (datastore configuration)
- 30 minutes (backup job recreation)
- 30 minutes (testing and verification)
- **Total: ~90 minutes**

---

## Recommended Approach

**Primary Plan: Option 3 (Fresh PBS Install)**

**Reasoning:**
1. still-fawn offline status unknown (could be hardware failure)
2. PBS data already on pumped-piglet (no data migration needed)
3. Fresh install ensures latest PBS version
4. pumped-piglet has abundant resources (12 cores at 9.8% utilization)
5. Faster than waiting for ZFS send/receive (Option 2)

**Execution Timeline:**
1. **Day 1 (Today):** Install PBS on pumped-piglet, configure datastore
2. **Day 2:** Test backups, verify old data accessible
3. **Day 3:** Recreate backup jobs, monitor first automated backup
4. **Day 4:** Document any issues, finalize configuration

---

## Next Steps

1. **Immediate:** Decide on migration approach
2. **Short-term:** Execute Option 3 (fresh PBS install)
3. **Medium-term:** Investigate still-fawn hardware failure
4. **Long-term:** Consider PBS HA setup or off-site backup replication

---

## Related Documentation

- Original PBS installation: Community Scripts helper script
- Backup retention policy: 7 daily, 4 weekly, 3 monthly
- Storage investigation: `docs/review-homelab-infrastructure-2025-01.md`

---

**Status:** Ready for execution
**Blocker:** None (all prerequisites met)
**Risk:** Low (data already on target node)

**Questions for User:**
1. What caused still-fawn to go offline?
2. Is still-fawn hardware recoverable?
3. Should we keep still-fawn in cluster or remove it?
4. Any specific PBS configuration requirements (users, certificates, etc.)?
