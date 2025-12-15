# Backup and Restore Runbook

## Overview

This runbook documents recovery procedures for the homelab infrastructure using **PBS-native** (Proxmox Backup Server) functionality.

### Backup Tiers

| Tier | Method | RPO | Purpose |
|------|--------|-----|---------|
| 1 | ZFS Snapshots | 1 hour | Quick recovery from deletion/corruption |
| 2 | PBS + External HDD | 24 hours | Survive host failure (PBS sync job) |
| 3 | PostgreSQL dumps | 24 hours | Fast database recovery |
| 4 | Google Drive | 24 hours | Survive site disaster |

### What's Backed Up

| Data | Size | ZFS Snap | PBS (homelab-backup) | PBS (external-hdd) | Google Drive |
|------|------|----------|---------------------|-------------------|--------------|
| PostgreSQL | 10Gi | ✓ | ✓ | ✓ (sync job) | ✓ |
| K3s VMs | ~2TB | ✓ | ✓ | ✓ (sync job) | ✗ |
| Frigate config | 1Gi | ✓ | ✓ | ✓ (sync job) | ✗ |
| Frigate media | 200Gi | ✓ | ✗ | ✗ | ✗ |
| SOPS age key | <1Mi | Manual | Manual | Manual | Manual |

### PBS Infrastructure

| Component | Details |
|-----------|---------|
| PBS Host | LXC 103 on pumped-piglet (192.168.4.218:8007) |
| Main Datastore | `homelab-backup` (20TB, includes all VMs/LXCs) |
| External Datastore | `external-hdd` (sync target for offsite rotation) |
| Retention | 7 daily, 4 weekly, 3 monthly |
| Sync Job | `external-sync` - daily sync to external HDD |
| Verify Job | `weekly-verify` - weekly integrity check |

---

## Recovery Procedures

### Scenario 1: Accidental File/Database Deletion

**Symptoms**: User accidentally deleted data, need quick recovery

**Option A: ZFS Snapshot Rollback (fastest)**

```bash
# SSH to the Proxmox host
ssh root@pumped-piglet.maas

# List available snapshots
zfs list -t snapshot | grep <pool-name>

# Find the snapshot before deletion
zfs list -t snapshot -o name,creation -s creation | tail -20

# Rollback to snapshot (WARNING: loses all changes after snapshot)
zfs rollback <pool>@<snapshot>

# Or clone snapshot to recover specific files
zfs clone <pool>@<snapshot> <pool>/recovery
# Mount and copy files, then destroy clone
zfs destroy <pool>/recovery
```

**Option B: PostgreSQL Dump Restore**

```bash
# List available backups
kubectl exec -n database postgres-postgresql-0 -- ls -la /backup/

# Restore from dump
kubectl exec -it -n database postgres-postgresql-0 -- bash
gunzip -k /backup/pg_dumpall_YYYYMMDD_HHMMSS.sql.gz
psql -U postgres -f /backup/pg_dumpall_YYYYMMDD_HHMMSS.sql
```

---

### Scenario 2: Single VM/LXC Failure

**Symptoms**: VM won't start, filesystem corruption, need full VM restore

**Recovery from PBS (Web UI - Recommended)**

1. Open PBS Web UI: https://192.168.4.218:8007
2. Navigate to Datastore > homelab-backup > Content
3. Find the VM/LXC backup, click Restore
4. Select target Proxmox node and storage

**Recovery from PBS (CLI)**

```bash
# SSH to any Proxmox host
ssh root@pumped-piglet.maas

# List available backups in PBS
pvesm list homelab-backup

# Or list via PBS directly
pct exec 103 -- proxmox-backup-client list --repository localhost:homelab-backup

# Restore VM (example: VM 105)
qmrestore homelab-backup:backup/vzdump-qemu-105-YYYY_MM_DD-HH_MM_SS.vma 105

# For LXC container
pct restore 113 homelab-backup:backup/vzdump-lxc-113-YYYY_MM_DD-HH_MM_SS.tar.zst
```

**Recovery from External HDD (if main PBS unavailable)**

```bash
# If external-hdd datastore is available in PBS
pvesm list external-hdd

# Or if HDD moved to another host, import as PBS datastore first
# See Scenario 3 for details
```

---

### Scenario 3: Single Host Failure

**Symptoms**: Entire Proxmox host is down (e.g., pumped-piglet dies)

**If PBS is on the failed host (pumped-piglet):**

1. Connect external HDD to surviving host
2. Create PBS datastore from external HDD

```bash
# On surviving host (e.g., fun-bedbug or chief-horse)

# Option A: Install PBS on surviving host and import datastore
apt update && apt install proxmox-backup-server -y

# Mount external HDD
mkdir -p /mnt/external-backup
mount /dev/sdX1 /mnt/external-backup

# Create PBS datastore pointing to existing data
# The external-hdd was synced from PBS, so it's already in PBS format
proxmox-backup-manager datastore create recovery-store /mnt/external-backup/pbs-datastore

# Now restore VMs using PBS native commands
proxmox-backup-client restore <backup-id> /tmp/restore/
```

```bash
# Option B: Restore directly without PBS (emergency)
# PBS stores VMs in chunk format, need to use proxmox-backup-client

# Install PBS client tools
apt install proxmox-backup-client -y

# Mount and list backups
proxmox-backup-client list --repository /mnt/external-backup/pbs-datastore

# Restore specific VM
proxmox-backup-client restore host/vm-105/YYYY-MM-DDTHH:MM:SS \
  --repository /mnt/external-backup/pbs-datastore \
  --target /tmp/restore
```

3. Restore critical VMs to surviving host

```bash
# After extracting from PBS, restore to Proxmox
qmrestore /tmp/restore/vzdump-qemu-105-*.vma 105 --storage local-zfs
```

**If PBS survives (e.g., fun-bedbug dies):**

Simply restore from PBS to another host with available resources:

```bash
# From any Proxmox host with PBS storage configured
pvesm list homelab-backup | grep "vzdump-qemu-113"
qmrestore homelab-backup:backup/vzdump-qemu-113-*.vma 113 --storage local-zfs
```

---

### Scenario 4: Two+ Hosts Fail / Site Disaster

**Symptoms**: Multiple hosts down, or total site loss (fire, theft)

**Step 1: Recover PostgreSQL from Google Drive**

```bash
# On new infrastructure
rclone copy gdrive-backup:homelab-backup/postgres/ /tmp/pg-restore/

# Restore to new PostgreSQL instance
gunzip /tmp/pg-restore/pg_dumpall_*.sql.gz
psql -h <new-host> -U postgres -f /tmp/pg-restore/pg_dumpall_*.sql
```

**Step 2: Restore GitOps Configuration**

```bash
# Clone repository (already on GitHub)
git clone https://github.com/homeiac/home.git

# Install Flux on new K3s cluster
flux bootstrap github \
  --owner=homeiac \
  --repository=home \
  --path=gitops/clusters/homelab
```

**Step 3: Restore SOPS Key**

```bash
# Retrieve SOPS age key from:
# - Google Drive (manual backup)
# - Password manager
# - Offsite backup

# Restore to ~/.config/sops/age/keys.txt
mkdir -p ~/.config/sops/age
# Copy key file
chmod 600 ~/.config/sops/age/keys.txt

# Recreate K8s secret
kubectl create secret generic sops-age \
  --namespace=flux-system \
  --from-file=age.agekey=~/.config/sops/age/keys.txt
```

**Step 4: Restore VMs from External HDD (if available)**

If external HDD was taken offsite before disaster:

```bash
# Mount external HDD on new Proxmox host
mount /dev/sdX1 /mnt/external-backup

# Restore VMs
qmrestore /mnt/external-backup/pbs-backup/.../vzdump-qemu-*.vma <new-vmid>
```

---

## Backup Verification

### Daily Checks (Automated)

The backup CronJobs should create these artifacts:

```bash
# PostgreSQL backup
kubectl exec -n database postgres-postgresql-0 -- ls -la /backup/

# Check CronJob status
kubectl get cronjob -n database
kubectl get jobs -n database --sort-by=.metadata.creationTimestamp | tail -5
```

### Weekly Checks (Manual)

```bash
# 1. Verify ZFS snapshots exist
ssh root@pumped-piglet.maas "zfs list -t snapshot | wc -l"
ssh root@fun-bedbug.maas "zfs list -t snapshot | wc -l"

# 2. Verify PBS backups are recent
ssh root@pumped-piglet.maas "proxmox-backup-client list --repository localhost:homelab-backup"

# 3. Verify external HDD sync
ssh root@pumped-piglet.maas "ls -la /mnt/external-backup/pbs-backup/"

# 4. Verify Google Drive backups
rclone ls gdrive-backup:homelab-backup/postgres/
```

### Monthly Checks (Manual)

1. **Test restore**: Restore a PostgreSQL dump to a test database
2. **External HDD rotation**: Consider taking HDD offsite and swapping with another

---

## Critical Files Backup

### SOPS Age Key (CRITICAL)

The SOPS age key is required to decrypt all secrets. **Back this up manually!**

Location: `~/.config/sops/age/keys.txt`

**Backup locations:**
- [ ] Google Drive (encrypted or in secure folder)
- [ ] Password manager (e.g., 1Password, Bitwarden)
- [ ] Printed copy in secure location

```bash
# View public key (safe to share)
grep "public key" ~/.config/sops/age/keys.txt

# Backup key content (KEEP PRIVATE)
cat ~/.config/sops/age/keys.txt
```

### Git Repository

Already on GitHub: https://github.com/homeiac/home

Contains all GitOps manifests - K8s will be fully reconstructed by Flux.

---

## Troubleshooting

### PBS Connection Issues

```bash
# Test PBS connectivity
ping proxmox-backup-server.maas
curl -k https://192.168.4.218:8007

# Check PBS storage status
pvesm status | grep homelab-backup

# See docs/proxmox-backup-server-storage-connectivity.md
```

---

## PBS Commands Reference

### Datastore Management

```bash
# List datastores
pct exec 103 -- proxmox-backup-manager datastore list

# Create datastore
pct exec 103 -- proxmox-backup-manager datastore create <name> <path>

# Remove datastore (does NOT delete data)
pct exec 103 -- proxmox-backup-manager datastore remove <name>

# Show datastore status
pct exec 103 -- proxmox-backup-manager datastore status <name>
```

### Sync Jobs (Replication)

```bash
# List sync jobs
pct exec 103 -- proxmox-backup-manager sync-job list

# Create sync job
pct exec 103 -- proxmox-backup-manager sync-job create <id> \
  --remote <remote-name> \
  --remote-store <source-datastore> \
  --store <target-datastore> \
  --schedule "daily"

# Run sync job manually
pct exec 103 -- proxmox-backup-manager sync-job run <id>

# Remove sync job
pct exec 103 -- proxmox-backup-manager sync-job remove <id>
```

### Verify Jobs (Integrity)

```bash
# List verify jobs
pct exec 103 -- proxmox-backup-manager verify-job list

# Create verify job
pct exec 103 -- proxmox-backup-manager verify-job create <id> \
  --store <datastore> \
  --schedule "sat 03:00"

# Run verification manually
pct exec 103 -- proxmox-backup-manager verify <datastore>

# Check task status
pct exec 103 -- proxmox-backup-manager task list
```

### Backup Listing and Restore

```bash
# List backups in datastore
pct exec 103 -- proxmox-backup-client list --repository localhost:homelab-backup

# List specific backup contents
pct exec 103 -- proxmox-backup-client catalog dump <backup-id> \
  --repository localhost:homelab-backup

# Restore from backup
pct exec 103 -- proxmox-backup-client restore <backup-id> <target> \
  --repository localhost:homelab-backup
```

### Garbage Collection

```bash
# Run garbage collection (cleans unused chunks)
pct exec 103 -- proxmox-backup-manager garbage-collection start homelab-backup

# Check GC status
pct exec 103 -- proxmox-backup-manager garbage-collection status homelab-backup
```

### ZFS Snapshot Issues

```bash
# Check sanoid status
ssh root@<host> "systemctl status sanoid.timer"

# Run sanoid manually
ssh root@<host> "sanoid --take-snapshots --verbose"

# Check disk space (snapshots consume space)
ssh root@<host> "zfs list -o name,used,avail,refer"
```

### Google Drive Sync Issues

```bash
# Test rclone connection
rclone about gdrive-backup:

# Re-authorize if token expired
rclone config reconnect gdrive-backup:

# Debug sync
rclone sync /path/to/backups gdrive-backup:homelab-backup/ -vv
```

---

## Setup Scripts

Scripts to configure the backup infrastructure:

| Script | Purpose |
|--------|---------|
| `scripts/backup/setup-pbs-external-datastore.sh` | Add external HDD as PBS datastore |
| `scripts/backup/setup-pbs-sync-job.sh` | Create PBS sync job for replication |
| `scripts/backup/setup-pbs-verify-job.sh` | Create PBS verify job for integrity |
| `scripts/backup/setup-zfs-snapshots.sh` | Configure sanoid for ZFS snapshots |
| `scripts/backup/setup-rclone-gdrive.sh` | Configure rclone for Google Drive |
| `scripts/backup/sync-postgres-to-gdrive.sh` | Sync PostgreSQL backups to GDrive |

**Initial Setup Order:**

1. `setup-pbs-external-datastore.sh` - Run on pumped-piglet with HDD connected
2. `setup-pbs-sync-job.sh` - Create sync job after datastore exists
3. `setup-pbs-verify-job.sh` - Create verify jobs for integrity
4. `setup-zfs-snapshots.sh` - Configure sanoid on each host
5. `setup-rclone-gdrive.sh` - Configure Google Drive (needs OAuth)

---

## Contact

- Repository: https://github.com/homeiac/home
- Documentation: /docs/
