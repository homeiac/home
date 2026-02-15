# PBS Migration: pumped-piglet → still-fawn

**Date:** 2026-02-14
**Status:** Planning Phase (Phase 2)
**Objective:** Move PBS to still-fawn to reduce pumped-piglet failure blast radius

---

## Overview

This runbook migrates Proxmox Backup Server from pumped-piglet (LXC 103) to still-fawn. The goal is to decentralize critical infrastructure - currently, pumped-piglet hosts all GPU workloads AND PBS, creating a single point of failure.

**Why migrate?**
- pumped-piglet failure = catastrophic (GPU workloads + PBS + storage all down)
- PBS doesn't need GPU (wasted resources on pumped-piglet)
- Physically moving the 3TB HDD means NO data migration needed
- Reduces blast radius: PBS failure only affects backups, not GPU workloads

---

## Current State

### PBS on pumped-piglet (LXC 103)
```
Container ID: 103
Hostname: proxmox-backup-server
IP: DHCP (resolves as proxmox-backup-server.maas)

Resources:
- CPU: 2 cores
- RAM: 2048 MB
- Root FS: local-2TB-zfs:subvol-103-disk-0 (200GB allocated, 2.21GB used)
- Datastore: local-3TB-backup:subvol-103-homelab-backup (mounted at /mnt/homelab-backup)
```

### Storage on pumped-piglet
```
sda - 2.7TB WD HDD (WD30EZRX) → local-3TB-backup pool (PBS datastore, ~1.26TB used)
sdc - 2.3TB WD HDD (WD25EZRS) → appears underutilized
nvme1n1 - 1.9TB Intel NVMe → K3s VM storage
nvme0n1 - 238GB boot drive
```

### still-fawn Storage
```
Pool: rpool (2TB SSD mirror - 2x T-FORCE SSDs)
Total: 1.86TB
Used: 40.2GB (K3s VM disk, etc.)
Available: 1.76TB
```

---

## Migration Strategy: Physically Move the 3TB HDD

**Key insight:** The 3TB WD HDD (`sda` on pumped-piglet) contains the entire PBS datastore as a ZFS pool. By physically moving this drive to still-fawn:
- **Zero data migration** - ZFS pool imports directly
- **Full 2.7TB capacity** retained
- **All backup history preserved**
- **Minimal downtime** (just the physical move)

### Target Architecture

```
still-fawn.maas
├── Root System: rpool/ROOT (~2.5GB) [SSD mirror]
├── K3s VM (VMID 108): ~40GB [SSD mirror]
├── PBS LXC Root FS: 20GB [SSD mirror]
└── PBS Datastore: 2.7TB [WD 3TB HDD - moved from pumped-piglet]
    └── local-3TB-backup pool (imported)

pumped-piglet.maas (after migration)
├── sdc - 2.3TB WD HDD (available for other use)
├── nvme1n1 - 1.9TB Intel NVMe (K3s VM)
└── nvme0n1 - 238GB boot drive
```

---

## Prerequisites

- [ ] still-fawn has been stable for 1-2 weeks (Phase 1 verification)
- [ ] Physical access to both machines
- [ ] SATA port available on still-fawn
- [ ] Backup current PBS config from pumped-piglet
- [ ] Plan maintenance window (~30 minutes downtime)

---

## Procedure

### Phase 1: Preparation (Before Physical Work)

#### 1.1 Backup PBS Configuration

```bash
ssh root@pumped-piglet.maas

# Enter PBS container
pct enter 103

# Export current config
proxmox-backup-manager config show > /tmp/pbs-config-backup.txt
proxmox-backup-manager datastore list > /tmp/pbs-datastore-backup.txt
proxmox-backup-manager user list > /tmp/pbs-users-backup.txt

# Copy backups out
exit
pct pull 103 /tmp/pbs-config-backup.txt /root/pbs-config-backup.txt
pct pull 103 /tmp/pbs-datastore-backup.txt /root/pbs-datastore-backup.txt
pct pull 103 /tmp/pbs-users-backup.txt /root/pbs-users-backup.txt

# Also copy to your local machine
scp root@pumped-piglet.maas:/root/pbs-*.txt /tmp/
```

#### 1.2 Document ZFS Pool Details

```bash
ssh root@pumped-piglet.maas

# Record pool name and status
zpool status local-3TB-backup
zpool list local-3TB-backup

# Record the disk identifier
zpool status local-3TB-backup | grep -E "sda|wwn"
```

Save this output - you'll need the pool name for import.

#### 1.3 Verify still-fawn Has SATA Port

```bash
ssh root@still-fawn.maas

# Check available SATA ports
ls /sys/class/ata_port/

# Check current SATA devices
lsblk | grep -E "^sd"
```

still-fawn currently shows only the SSD mirror (sda, sdb). A third SATA port should be available for the HDD.

#### 1.4 Stop PBS Container and Export Pool

```bash
ssh root@pumped-piglet.maas

# Stop PBS
pct stop 103

# Export the ZFS pool cleanly
zpool export local-3TB-backup

# Verify export
zpool list
# Should NOT show local-3TB-backup
```

#### 1.5 Shutdown Both Hosts

```bash
# Shutdown still-fawn first (will receive the drive)
ssh root@still-fawn.maas 'shutdown -h now'

# Then shutdown pumped-piglet
ssh root@pumped-piglet.maas 'shutdown -h now'
```

### Phase 2: Physical Drive Move

#### 2.1 Move the HDD

1. Power off both machines (verify LEDs off)
2. Open pumped-piglet chassis
3. Disconnect 3TB WD HDD (sda - WD30EZRX)
   - Note: This is the larger WD drive (2.7TB), not the 2.3TB one
4. Open still-fawn chassis
5. Connect HDD to available SATA port + power
6. Close both chassis

#### 2.2 Power On Hosts

1. Power on still-fawn first
2. Power on pumped-piglet
3. Wait for both to boot (~2-3 minutes)

### Phase 3: Import ZFS Pool on still-fawn

#### 3.1 Verify Drive Detection

```bash
ssh root@still-fawn.maas

# Check drive appeared
lsblk
# Should now show sdc or similar as 2.7T disk

# Check ZFS can see the pool
zpool import
# Should list "local-3TB-backup" as available for import
```

#### 3.2 Import the Pool

```bash
ssh root@still-fawn.maas

# Import the pool
zpool import local-3TB-backup

# Verify import
zpool status local-3TB-backup
zpool list local-3TB-backup

# Check the datastore subvolume
zfs list | grep homelab-backup
```

#### 3.3 Register Pool in Proxmox Storage

```bash
ssh root@still-fawn.maas

# Add to Proxmox storage config (if not auto-detected)
pvesm add zfspool local-3TB-backup -pool local-3TB-backup -content rootdir,images
```

### Phase 4: Create PBS Container on still-fawn

#### 4.1 Install PBS Using Community Scripts

```bash
ssh root@still-fawn.maas

# Download and run PBS installation script
bash -c "$(wget -qLO - https://github.com/community-scripts/ProxmoxVE/raw/main/ct/proxmox-backup-server.sh)"

# Follow prompts:
# - Container ID: 103 (reuse same ID)
# - Cores: 2
# - RAM: 2048 MB
# - Disk Size: 20 GB (root only)
# - Network: Bridge vmbr0
# - IP: DHCP (will get same IP via MAC if possible)
# - Storage: local-zfs (still-fawn's rpool/data for root FS)
```

#### 4.2 Mount Existing Datastore

```bash
ssh root@still-fawn.maas

# Stop container
pct stop 103

# Add mount point for existing datastore
# The subvolume already exists from the imported pool!
cat >> /etc/pve/lxc/103.conf <<'EOF'
mp0: local-3TB-backup:subvol-103-homelab-backup,mp=/mnt/homelab-backup,backup=1,size=0T
EOF

# Start container
pct start 103
```

#### 4.3 Configure PBS to Use Existing Datastore

```bash
pct enter 103

# The datastore data already exists, just register it
proxmox-backup-manager datastore create homelab-backup /mnt/homelab-backup

# Verify all backups are visible
proxmox-backup-client backup-group list homelab-backup

# Configure retention (match original)
proxmox-backup-manager datastore update homelab-backup \
  --gc-schedule "daily" \
  --prune-schedule "daily" \
  --keep-daily 3 \
  --keep-weekly 2

exit
```

### Phase 5: Update Cluster Configuration

#### 5.1 Get PBS IP/Fingerprint

```bash
ssh root@still-fawn.maas

# Get container IP
pct exec 103 -- hostname -I

# Get fingerprint
pct exec 103 -- proxmox-backup-manager cert info | grep Fingerprint
```

#### 5.2 Update DNS (Recommended)

Update OPNsense DNS to point `proxmox-backup-server.maas` to new IP:
- OPNsense → Services → Unbound DNS → Host Overrides
- Update `proxmox-backup-server` to new IP

Or if using DHCP with MAC reservation, the IP may stay the same.

#### 5.3 Update Storage Config on All Nodes (if IP changed)

If the PBS IP changed, update `/etc/pve/storage.cfg` on each node:

```bash
# On each Proxmox node
# Edit the homelab-backup storage entry:
# - Update 'server' line to new IP
# - Update 'fingerprint' if regenerated
```

Or via Proxmox Web UI: Datacenter → Storage → homelab-backup → Edit

#### 5.4 Test Connectivity from All Nodes

```bash
# From each Proxmox host
for node in pve still-fawn pumped-piglet chief-horse fun-bedbug; do
  echo "=== $node ==="
  ssh root@${node}.maas "pvesm status --storage homelab-backup"
done
```

### Phase 6: Verification

#### 6.1 Verify All Backups Accessible

```bash
# Access PBS web UI
open https://proxmox-backup-server.maas:8007

# Or via CLI
pct exec 103 -- proxmox-backup-client backup-group list homelab-backup
```

Verify:
- All VM backup groups present
- All CT backup groups present
- Recent backups show correct dates

#### 6.2 Test Backup

```bash
# From any Proxmox node, backup a small CT
vzdump 100 --storage homelab-backup --mode snapshot
```

#### 6.3 Test Restore

```bash
# Dry-run restore
qmrestore homelab-backup:backup/vm/100/latest 999 --storage local-zfs
```

### Phase 7: Cleanup

#### 7.1 Delete Old PBS Container on pumped-piglet

```bash
ssh root@pumped-piglet.maas

# The container root was on local-2TB-zfs, datastore was on the moved HDD
# Container is now orphaned - safe to remove
pct destroy 103 --purge
```

#### 7.2 Remove Old Storage Reference (if needed)

```bash
ssh root@pumped-piglet.maas

# Remove the now-missing pool from storage config
pvesm remove local-3TB-backup
```

---

## Verification Checklist

- [ ] 3TB HDD physically installed in still-fawn
- [ ] `local-3TB-backup` ZFS pool imported successfully
- [ ] PBS container 103 running on still-fawn
- [ ] Web UI accessible at https://proxmox-backup-server.maas:8007
- [ ] All backup groups visible (VMs and CTs)
- [ ] Each Proxmox node can connect to storage
- [ ] Test backup from at least 2 nodes succeeds
- [ ] Test restore works
- [ ] Old PBS container removed from pumped-piglet
- [ ] pumped-piglet boots cleanly without the HDD

---

## Rollback Plan

**If migration fails after physical move:**

1. Shutdown still-fawn
2. Move HDD back to pumped-piglet
3. Power on pumped-piglet
4. Import pool: `zpool import local-3TB-backup`
5. Start PBS: `pct start 103`

**Data safety:** The ZFS pool contains all data. As long as the HDD is intact, data is safe.

---

## Post-Migration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  still-fawn (NVR + Backup Node)                             │
├─────────────────────────────────────────────────────────────┤
│  Storage:                                                   │
│  ├── rpool (2TB SSD mirror) - OS, K3s VM, PBS root         │
│  └── local-3TB-backup (2.7TB HDD) - PBS datastore          │
│                                                             │
│  Workloads:                                                 │
│  ├── PBS LXC 103 - Proxmox Backup Server                   │
│  ├── K3s VM 108 - Future: Frigate + Coral TPU              │
│  └── (Future: Frigate recordings on SSD)                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  pumped-piglet (GPU Powerhouse)                             │
├─────────────────────────────────────────────────────────────┤
│  Storage:                                                   │
│  ├── sdc (2.3TB HDD) - Available for other use             │
│  ├── nvme1n1 (1.9TB NVMe) - K3s VM storage                 │
│  └── nvme0n1 (238GB NVMe) - Boot                           │
│                                                             │
│  Workloads:                                                 │
│  ├── K3s VM 105 - Ollama, Stable Diffusion, Webtop         │
│  └── RTX 3070 GPU - AI/ML workloads                        │
└─────────────────────────────────────────────────────────────┘
```

**Benefits:**
| Metric | Before | After |
|--------|--------|-------|
| pumped-piglet failure impact | Catastrophic (GPU + PBS) | GPU only |
| Data migration required | N/A | **None** (physical move) |
| Backup capacity | 2.7TB | 2.7TB (unchanged) |
| PBS storage speed | HDD | HDD (same drive) |
| Downtime | N/A | ~30 minutes |

---

## Related Documentation

- `docs/runbooks/pbs-migration-to-pumped-piglet.md` - Previous migration (reverse reference)
- `docs/runbooks/proxmox-backup-server-storage-connectivity.md` - PBS troubleshooting
- `proxmox/inventory.txt` - Cluster inventory

---

## Tags

pbs, proxmox-backup-server, migration, still-fawn, pumped-piglet, storage, backup, zfs, infrastructure, resilience, blast-radius, physical-move, hdd
