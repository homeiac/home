# RCA: High I/O Misdiagnosis on pumped-piglet

## Incident Date: 2025-12-12

## Summary

High disk I/O (12MB/s constant reads) on `local-20TB-zfs` was misattributed to Frigate NVR, leading to 45+ minutes of unnecessary troubleshooting and data loss. The actual cause was a PBS backup job.

## Timeline

| Time | Action | Result |
|------|--------|--------|
| 16:00 | Noticed high CPU on Frigate pod (1188m) | Started investigating Frigate |
| 16:05 | Found detection disabled on cameras | Enabled detection, added to configmap |
| 16:10 | Found /import VirtioFS mount was read-only | Changed to read-write |
| 16:15 | Frigate cleanup started deleting old recordings | Partial fix assumed |
| 16:20 | Found symlinks to /import causing I/O | Deleted symlinks |
| 16:25 | Deleted remaining symlinks (Dec 6-11 data lost) | I/O still high |
| 16:28 | Removed VirtioFS mount from deployment | I/O still high |
| 16:30 | Reset Frigate database | I/O still high |
| 16:32 | Assumed PVC was on USB storage | Investigated storage layout |
| 16:35 | User asked about backups | Checked for backups |
| 16:36 | **Found PBS backup running** | Actual root cause identified |

## Root Cause

A PBS backup job was running for VM 105 (K3s VM), reading the 18TB USB-attached zvol (`scsi1`).

```
lock: backup
task UPID:pumped-piglet:001854D2:1B2ADD95:693C976B:vzdump:105:root@pam:
```

## What Should Have Been Done

```bash
# Step 1: Identify process causing I/O (2 minutes)
for pid in $(ls /proc | grep -E '^[0-9]+$'); do
  bytes=$(awk '/read_bytes/ {print $2}' /proc/$pid/io 2>/dev/null)
  if [ "$bytes" -gt 1000000000 ] 2>/dev/null; then
    echo "$pid: $bytes - $(cat /proc/$pid/comm 2>/dev/null)"
  fi
done | sort -t: -k2 -rn | head -5

# Result would show:
# 1491496: 16669911851008 - kvm
# 2403359: 270580526222 - proxmox-backup-

# Step 2: Check for backup
ps aux | grep vzdump
qm config 105 | grep lock
# Result: lock: backup
```

## Impact

1. **Data Loss**: Recordings from Dec 6-11 deleted (symlinks removed)
2. **Unnecessary Changes**:
   - VirtioFS mount removed from deployment
   - Frigate database reset
   - Multiple pod restarts
3. **Time Wasted**: 45+ minutes on wrong diagnosis

## Lessons Learned

1. **Always identify the process causing I/O first** - not the application you assume is responsible
2. **Check for system operations** (backups, scrubs, replication) before application-level investigation
3. **Use Linux I/O tools** (`/proc/*/io`, `iotop`) not assumptions
4. **Don't make changes without proper diagnosis** - each change makes root cause harder to find

## Preventive Actions

1. Added runbook: `docs/source/md/runbook-investigate-high-io.md`
2. Updated CLAUDE.md with investigation methodology
3. Document the proper I/O investigation commands

## Commands to Remember

```bash
# Find top I/O processes
for pid in $(ls /proc | grep -E '^[0-9]+$'); do
  bytes=$(awk '/read_bytes/ {print $2}' /proc/$pid/io 2>/dev/null)
  if [ "$bytes" -gt 1000000000 ] 2>/dev/null; then
    echo "$pid: $bytes - $(cat /proc/$pid/comm 2>/dev/null)"
  fi
done | sort -t: -k2 -rn | head -10

# Check for backups
ps aux | grep -E 'vzdump|proxmox-backup'
qm config <VMID> | grep lock
cat /var/log/pve/tasks/active

# Check ZFS I/O per pool
zpool iostat -v 2 3
```
