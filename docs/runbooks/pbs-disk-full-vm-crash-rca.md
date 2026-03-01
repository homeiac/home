# RCA: PBS Disk Full Causes VM 105 Crash via Frozen Filesystem

**Date**: 2026-02-28
**Severity**: Critical
**Impact**: K3s VM 105 (pumped-piglet) crashed and stayed down for ~28 hours. All K8s workloads on that node unavailable (Frigate, Ollama, Stable Diffusion, Prometheus, Flux image automation).
**Resolution**: Freed space on 3TB ZFS pool, configured PBS prune/GC schedules, started VM. Also discovered and fixed Crossplane provider-proxmox burning 200% CPU.

## Executive Summary

On 2026-02-27 at 22:30, the scheduled vzdump backup of VM 105 failed because the `local-3TB-backup` ZFS pool was 100% full (2.63 TB / 2.63 TB). The backup issued a `guest-fsfreeze-freeze` QMP command to quiesce the VM's filesystem before the backup write. When the backup write failed with `ENOSPC`, vzdump attempted to thaw the filesystem via `guest-fsfreeze-thaw`, but this also timed out. The VM was left with its filesystem frozen, became unresponsive, and eventually crashed.

The VM remained down for ~28 hours until manually discovered and investigated. No alerts were generated because PVE had no notification configuration — the default `mail-to-root` endpoint had no relay configured.

The root cause of the disk full condition was that PBS garbage collection had **never been run** on the `homelab-backup` datastore, and no prune job existed on the PBS side. Dead chunks accumulated over months, and stale data (160 GB ZFS snapshot from August 2025, 97 GB vzdump temp from December 2025) consumed remaining space.

## Investigation

### Discovery Flow

```
User reports VM 105 down
    │
    ▼
qm status 105 → "stopped"
    │
    ▼
journalctl grep VM 105 → backup failures with ENOSPC
    │
    ├─── Feb 27 22:30: Backup started
    ├─── Feb 27 23:30: guest-fsfreeze-freeze timeout
    ├─── Feb 27 23:30: ENOSPC on backup write
    ├─── Feb 27 23:33: guest-fsfreeze-thaw timeout
    ├─── Feb 27 23:33: Backup FAILED
    ├─── Feb 28 02:30: Retry backup, VM started (was stopped)
    └─── Feb 28 02:30: ENOSPC again, backup FAILED
    │
    ▼
zfs list local-3TB-backup → 0 bytes available
    │
    ▼
Investigate PBS state:
    ├─── GC status: all zeros (never run)
    ├─── Prune jobs: none configured
    ├─── Storage-level retention: keep-all=1 (no pruning)
    ├─── Stale ZFS snapshot: 160 GB (Aug 2025)
    └─── Stale vzdump tmp: 97 GB (Dec 2025)
```

### Key Diagnostic Commands

| Command | Revealed |
|---------|----------|
| `qm status 105` | VM stopped |
| `journalctl \| grep "vm 105"` | ENOSPC errors, freeze/thaw timeouts |
| `zfs list local-3TB-backup` | 0 bytes available |
| `pct exec 103 -- proxmox-backup-manager garbage-collection status homelab-backup` | All zeros — GC never run |
| `pct exec 103 -- proxmox-backup-manager prune-job list` | Empty — no prune jobs |
| `zfs list -t snapshot -r local-3TB-backup` | 160 GB pre-migration snapshot from Aug 2025 |
| `ls /local-3TB-backup/backup-tmpdir/` | 97 GB stale vzdump temp from Dec 2025 |

## Root Cause Analysis

### Problem Chain

```
┌─────────────────────────────────────────────────────────────────┐
│  Root Cause: No PBS garbage collection or prune schedule        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. PBS GC never configured → dead chunks accumulate            │
│  2. No PBS prune job → old snapshots never removed              │
│  3. Stale ZFS data (snapshot + vzdump tmp) → 257 GB wasted      │
│  4. Pool fills to 100%                                          │
│                                                                 │
│  Trigger: vzdump backup at 22:30                                │
│                                                                 │
│  5. vzdump issues guest-fsfreeze-freeze → succeeds              │
│  6. Backup write hits ENOSPC → fails                            │
│  7. vzdump issues guest-fsfreeze-thaw → TIMES OUT               │
│  8. VM filesystem remains frozen → VM hangs → crashes           │
│                                                                 │
│  Amplifier: No notification config                              │
│                                                                 │
│  9. PVE mail-to-root → no relay configured → mail goes nowhere  │
│  10. No one knows VM is down for 28 hours                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Why guest-fsfreeze-thaw Failed

The thaw timeout is the critical bug in this chain. Normally, a failed backup should be recoverable — vzdump should thaw the filesystem and the VM continues running. However, when the underlying storage is 100% full:

1. The QEMU guest agent communicates via a virtio-serial channel
2. The guest agent process inside the VM may need to write to disk (logging, state)
3. With the filesystem frozen AND storage full, the agent becomes unresponsive
4. The QMP thaw command times out after 3 minutes
5. The VM is left in an unrecoverable frozen state

This is arguably a Proxmox VE bug — vzdump should handle ENOSPC more gracefully by force-thawing before giving up.

## Timeline

| Time | Event |
|------|-------|
| Feb 27, 22:30 | Scheduled vzdump backup of VM 105 starts |
| Feb 27, 23:30 | `guest-fsfreeze-freeze` times out, backup write fails with ENOSPC |
| Feb 27, 23:33 | `guest-fsfreeze-thaw` times out, backup marked FAILED |
| Feb 27, ~23:33-02:30 | VM 105 hangs with frozen filesystem, eventually crashes |
| Feb 28, 02:30 | Scheduled backup retry starts VM (was already stopped), immediately fails with ENOSPC |
| Feb 28, ~18:00 | User discovers VM is down, investigation begins |
| Feb 28, ~18:15 | Root cause identified: 3TB pool at 100% |
| Feb 28, ~18:20 | Stale vzdump tmp deleted (97 GB freed) |
| Feb 28, ~18:20 | Pre-migration ZFS snapshot destroyed (160 GB freed) |
| Feb 28, ~18:25 | PBS GC started (first ever), reclaimed 828 GB |
| Feb 28, ~18:30 | PBS prune job created (daily 04:00) |
| Feb 28, ~18:30 | GC schedule set (daily 05:00) |
| Feb 28, ~18:30 | Verify job created (Saturday 03:00) |
| Feb 28, ~18:45 | VM 105 started |
| Feb 28, ~22:10 | Crossplane provider-proxmox terraform loop discovered (200% CPU) |
| Feb 28, ~22:45 | Crossplane suspended via gitops |

## Resolution

### Immediate (Space Recovery)

```bash
# 1. Delete stale vzdump temp (97 GB, from Dec 2025)
rm -rf /local-3TB-backup/backup-tmpdir/vzdumptmp1916562_113/

# 2. Destroy 6-month-old pre-migration ZFS snapshot (160 GB)
zfs destroy local-3TB-backup/subvol-113-disk-0@pre-migration-20250816-0825

# 3. Run first-ever PBS garbage collection
pct exec 103 -- proxmox-backup-manager garbage-collection start homelab-backup
# Result: Removed 828 GB, 391850 chunks
# Dedup factor: 9.98x, on-disk usage: 1.463 TiB
```

**Space recovered**: Pool went from 0 B free → 977 GB free.

### Preventive (Scheduled Maintenance)

```bash
# PBS prune job: daily at 04:00, keep-daily=3, keep-weekly=2
pct exec 103 -- proxmox-backup-manager prune create homelab-prune \
  --schedule '04:00' --store homelab-backup --keep-daily 3 --keep-weekly 2

# PBS garbage collection: daily at 05:00
pct exec 103 -- proxmox-backup-manager datastore update homelab-backup \
  --gc-schedule '05:00'

# PBS verify job: Saturday at 03:00
pct exec 103 -- proxmox-backup-manager verify-job create homelab-verify \
  --schedule 'sat 03:00' --store homelab-backup
```

### Bonus: Crossplane CPU Fix

Crossplane provider-proxmox had no persisted terraform state, causing continuous terraform plan+apply loops (~200% CPU) for only 2 managed VMs. Suspended via gitops:

```yaml
# gitops/clusters/homelab/infrastructure/crossplane/helmrelease.yaml
spec:
  suspend: true  # provider-proxmox terraform loop burning CPU
```

## Verification

```bash
# Check PBS schedules are configured
pct exec 103 -- proxmox-backup-manager prune list
pct exec 103 -- proxmox-backup-manager datastore show homelab-backup
pct exec 103 -- proxmox-backup-manager verify-job list

# Check pool free space (should be >500 GB)
zfs list -o name,used,avail local-3TB-backup

# Check GC has run (should show non-zero removed-bytes)
pct exec 103 -- proxmox-backup-manager garbage-collection status homelab-backup

# Check VM is running
qm status 105
```

## Lessons Learned

### What Went Wrong

1. **PBS was deployed without GC or prune schedules** — The initial PBS setup created the datastore but never configured maintenance jobs. Dead chunks accumulated for months.
2. **No notification pipeline** — PVE's default `mail-to-root` goes to a local mailbox with no relay. Backup failures and VM crashes were silent.
3. **Stale data left behind** — A 160 GB ZFS snapshot from a migration 6 months ago and a 97 GB vzdump temp from a failed backup 3 months ago were never cleaned up.
4. **vzdump freeze/thaw is not crash-safe** — When storage is full, the thaw command can time out, leaving the VM in an unrecoverable state. This is a Proxmox design issue.
5. **Crossplane provider-proxmox runs terraform on every reconciliation** — Without state persistence, each loop spawns full terraform plan+apply. With only 2 managed VMs, the overhead far exceeds the value.

### What Went Right

1. Investigation was methodical — journalctl immediately pointed to ENOSPC
2. GC successfully reclaimed 828 GB on first run
3. Crossplane CPU issue was caught during the same investigation

### Improvements Needed

- [ ] Configure PVE host monitoring and notifications (HA webhook or similar)
- [ ] Add ZFS pool space alerting (warn at 80%, critical at 90%)
- [ ] Fix Crossplane state persistence before re-enabling
- [ ] Document PBS maintenance requirements in setup runbook
- [ ] Consider adding `--freeze-fs-on-backup 0` to vzdump config to avoid freeze on VMs with large disks

## Prevention

### PBS Maintenance Checklist (for any new PBS setup)

1. **Prune job**: `proxmox-backup-manager prune create` with retention policy
2. **GC schedule**: `proxmox-backup-manager datastore update --gc-schedule`
3. **Verify job**: `proxmox-backup-manager verify-job create` weekly
4. **Monitor disk space**: Alert at 80% usage
5. **Test notifications**: Verify alerts actually reach someone

### ZFS Pool Monitoring Script

See: `scripts/monitoring/check-zfs-space.sh` (to be created)

## Related Documents

- Runbook: `docs/runbooks/pbs-backup-maintenance-runbook.md`
- PBS migration: `docs/runbooks/pbs-migration-to-pumped-piglet.md`
- Secret management: `docs/secret-management.md`

## Tags

pbs, proxmox-backup-server, backup, vzdump, zfs, disk-full, enospc, guest-fsfreeze, vm-crash, garbage-collection, gc, prune, retention, crossplane, terraform, cpu, notification, alerting, pumped-piglet, vm-105, k3s, runbook, rca, root-cause-analysis, proxmox, pve

**Owner**: Homelab
**Last Updated**: 2026-02-28
