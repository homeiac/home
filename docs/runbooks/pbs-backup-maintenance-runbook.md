# Runbook: PBS Backup Maintenance

## Overview

Proxmox Backup Server (PBS) requires three scheduled maintenance tasks to prevent disk exhaustion: **prune**, **garbage collection (GC)**, and **verify**. Without these, the backup datastore grows unbounded and can crash VMs during backup (see RCA: `pbs-disk-full-vm-crash-rca.md`).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  PBS Maintenance Pipeline (Daily)                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  22:30  vzdump backup runs (PVE cluster job)                        │
│    │    └─ Backs up all VMs/CTs except 103,108                      │
│    ▼                                                                │
│  04:00  Prune job (PBS)                                             │
│    │    └─ Marks old snapshots for removal (keep-daily=3, weekly=2) │
│    ▼                                                                │
│  05:00  Garbage collection (PBS)                                    │
│    │    └─ Deletes unreferenced chunks, reclaims disk space         │
│    ▼                                                                │
│  sat 03:00  Verify job (PBS, weekly)                                │
│         └─ Validates backup integrity, checks for bit rot           │
│                                                                     │
│  PBS Container: LXC 103 on pumped-piglet.maas                       │
│  Datastore: homelab-backup at /mnt/homelab-backup                   │
│  Storage: ZFS pool local-3TB-backup                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Configuration Reference

| Setting | Value | Location |
|---------|-------|----------|
| PBS container | LXC 103 on pumped-piglet | `qm list` |
| PBS IP | 192.168.4.211 | `/etc/pve/storage.cfg` |
| PBS Web UI | `https://proxmox-backup-server.maas:8007` | Browser |
| Datastore | `homelab-backup` at `/mnt/homelab-backup` | PBS config |
| ZFS pool | `local-3TB-backup` | pumped-piglet host |
| Backup schedule | 2nd and 22nd of month at 22:30 | PVE cluster job |
| Backup exclusions | VM 103 (PBS itself), VM 108 (still-fawn K3s) | PVE cluster job |
| Retention (vzdump) | keep-daily=3, keep-weekly=2 | PVE cluster job |
| Retention (PBS prune) | keep-daily=3, keep-weekly=2 | PBS prune job |
| GC schedule | Daily at 05:00 | PBS datastore config |
| Verify schedule | Saturday at 03:00 | PBS verify job |
| Age key (SOPS) | `~/.config/sops/age/keys.txt` | Local Mac |

## Common Operations

### Check Datastore Health

```bash
# Pool free space (should be >500 GB)
ssh root@pumped-piglet.maas "zfs list -o name,used,avail local-3TB-backup"

# GC status (last run, bytes removed)
ssh root@pumped-piglet.maas "pct exec 103 -- proxmox-backup-manager garbage-collection status homelab-backup"

# List scheduled jobs
ssh root@pumped-piglet.maas "pct exec 103 -- proxmox-backup-manager prune list"
ssh root@pumped-piglet.maas "pct exec 103 -- proxmox-backup-manager verify-job list"
ssh root@pumped-piglet.maas "pct exec 103 -- proxmox-backup-manager datastore show homelab-backup"

# Backup inventory (all snapshots)
ssh root@pumped-piglet.maas "pvesm list homelab-backup"

# Dedup stats
ssh root@pumped-piglet.maas "pct exec 103 -- proxmox-backup-manager garbage-collection status homelab-backup"
# Look for: Deduplication factor, On-Disk usage
```

### Manual Prune

```bash
# Run prune job immediately
ssh root@pumped-piglet.maas "pct exec 103 -- proxmox-backup-manager prune run homelab-prune"
```

### Manual Garbage Collection

```bash
# Run GC immediately (can take 10-30 min on large datastores)
ssh root@pumped-piglet.maas "pct exec 103 -- proxmox-backup-manager garbage-collection start homelab-backup"

# NOTE: GC will fail with ENOSPC if the pool is 100% full
# In that case, free space at the ZFS level first (see Emergency section)
```

### Manual Verify

```bash
# Run verify immediately
ssh root@pumped-piglet.maas "pct exec 103 -- proxmox-backup-manager verify-job run homelab-verify"
```

### Check Backup Job Status

```bash
# PVE cluster backup job config
ssh root@pumped-piglet.maas "pvesh get /cluster/backup --output-format json | jq '.[0]'"

# Recent backup task logs
ssh root@pumped-piglet.maas "journalctl | grep -iE 'vzdump|backup' | tail -20"
```

## Emergency: Pool Full

If `local-3TB-backup` hits 100%, follow this order:

### 1. Free ZFS-Level Space First

GC cannot run on a full pool (needs space to update atimes). Free space at the ZFS level:

```bash
# Check for stale vzdump temp directories
ssh root@pumped-piglet.maas "du -sh /local-3TB-backup/backup-tmpdir/*"
# Delete if stale (no active backup running):
ssh root@pumped-piglet.maas "rm -rf /local-3TB-backup/backup-tmpdir/vzdumptmp*"

# Check for old ZFS snapshots
ssh root@pumped-piglet.maas "zfs list -t snapshot -o name,used,creation -r local-3TB-backup"
# Destroy old snapshots:
ssh root@pumped-piglet.maas "zfs destroy local-3TB-backup/DATASET@SNAPSHOT_NAME"

# Verify space freed
ssh root@pumped-piglet.maas "zfs list -o name,avail local-3TB-backup"
```

### 2. Run Prune Then GC

```bash
# Prune first (marks snapshots for removal)
ssh root@pumped-piglet.maas "pct exec 103 -- proxmox-backup-manager prune run homelab-prune"

# Then GC (actually deletes chunks and reclaims space)
ssh root@pumped-piglet.maas "pct exec 103 -- proxmox-backup-manager garbage-collection start homelab-backup"
```

### 3. If a VM Crashed

If a VM is stopped due to a frozen filesystem from a failed backup:

```bash
# Check VM status
ssh root@pumped-piglet.maas "qm status <VMID>"

# Start the VM (only after freeing disk space)
ssh root@pumped-piglet.maas "qm start <VMID>"

# If start fails, check for lock files
ssh root@pumped-piglet.maas "ls -la /var/lock/qemu-server/lock-<VMID>.conf"
ssh root@pumped-piglet.maas "rm /var/lock/qemu-server/lock-<VMID>.conf"
```

## Modifying Retention Policy

### PBS Prune Job

```bash
# Update retention (e.g., keep more daily backups)
ssh root@pumped-piglet.maas "pct exec 103 -- proxmox-backup-manager prune update homelab-prune \
  --keep-daily 7 --keep-weekly 4 --keep-monthly 3"
```

### PVE Cluster Backup Job

```bash
# Update via pvesh (match PBS prune retention)
ssh root@pumped-piglet.maas "pvesh set /cluster/backup/backup-ff3d789f-f52b \
  --prune-backups keep-daily=7,keep-weekly=4,keep-monthly=3"
```

### GitOps (pbs-storage.yaml)

The desired state is in `proxmox/homelab/config/pbs-storage.yaml`. Update `prune_backups` there and run `pbs apply` to reconcile.

**Note**: As of 2026-02-28, the YAML config (`keep-daily=7, weekly=4, monthly=3`) is out of sync with the live cluster job (`keep-daily=3, weekly=2`). Reconcile when appropriate.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| GC fails with ENOSPC | Pool 100% full | Free ZFS-level space first (see Emergency section) |
| VM stopped after backup | Freeze/thaw timeout on full disk | Free space, start VM |
| Backup fails with "storage inactive" | PBS LXC 103 down or DNS issue | `pct start 103`, check DNS |
| Prune removes nothing | All snapshots within retention window | Expected behavior — check with `pvesm list` |
| GC removes 0 bytes | No dead chunks (nothing pruned recently) | Run prune first, then GC |
| High dedup ratio (>15x) | Many similar VMs being backed up | Normal for homelab |
| Verify shows errors | Bit rot or corrupt chunks | Restore affected backups to verify, re-backup if needed |

## Monitoring (TODO)

**Not yet implemented** — see RCA `pbs-disk-full-vm-crash-rca.md` for context.

Needed:
- ZFS pool space alerting (warn 80%, critical 90%)
- Backup failure notifications to HA
- VM status monitoring (detect crashed VMs)

## Related Documents

- RCA: `docs/runbooks/pbs-disk-full-vm-crash-rca.md`
- PBS migration: `docs/runbooks/pbs-migration-to-pumped-piglet.md`
- PBS connectivity: `docs/runbooks/proxmox-backup-server-storage-connectivity.md`
- Secret management: `docs/secret-management.md`
- PBS CLI tool: `proxmox/homelab/src/homelab/pbs_cli.py`
- PBS config: `proxmox/homelab/config/pbs-storage.yaml`

## Tags

pbs, proxmox-backup-server, backup, vzdump, prune, garbage-collection, gc, verify, retention, zfs, disk-full, enospc, maintenance, schedule, datastore, homelab-backup, pumped-piglet, lxc-103, runbook, disaster-recovery, proxmox, pve, proxmocks

**Owner**: Homelab
**Last Updated**: 2026-02-28
