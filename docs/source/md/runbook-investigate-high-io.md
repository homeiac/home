# Runbook: Investigating High Disk I/O on Proxmox Hosts

## Overview

This runbook describes how to properly investigate high disk I/O on Proxmox hosts before making any application-level changes.

## Key Principle

**Always identify the actual process causing I/O before assuming it's an application problem.**

## Step 1: Identify Which Process is Causing I/O

```bash
# Find processes with highest read_bytes
for pid in $(ls /proc | grep -E '^[0-9]+$'); do
  if [ -f /proc/$pid/io ]; then
    bytes=$(awk '/read_bytes/ {print $2}' /proc/$pid/io 2>/dev/null)
    if [ "$bytes" -gt 1000000000 ] 2>/dev/null; then
      echo "$pid: $bytes - $(cat /proc/$pid/comm 2>/dev/null)"
    fi
  fi
done | sort -t: -k2 -rn | head -10
```

Or if `iotop` is installed:
```bash
iotop -b -o -n 2 -d 2
```

## Step 2: Check for System Operations

Before investigating applications, check for:

### Backups
```bash
# Check for running vzdump/PBS backups
ps aux | grep -E 'vzdump|proxmox-backup'

# Check if any VM is locked for backup
qm config <VMID> | grep lock

# Check active tasks
cat /var/log/pve/tasks/active
```

### ZFS Operations
```bash
# Check for scrubs
zpool status | grep -E 'scan|scrub'

# Check for resilver
zpool status | grep resilver

# Check ZFS I/O per pool
zpool iostat -v 1 3
```

### Replication
```bash
# Check for replication jobs
pvesr status
```

## Step 3: Correlate I/O with Storage

```bash
# Which pool is experiencing I/O?
zpool iostat -v 2 3

# What datasets are on that pool?
zfs list -r <poolname>

# What VMs use that pool?
grep -l "<poolname>" /etc/pve/qemu-server/*.conf
```

## Step 4: Only Then Investigate Applications

If system operations are not the cause, then investigate application-level:

```bash
# Check what's mounted where inside containers/VMs
# Check application logs
# Check application-specific I/O patterns
```

## Common Root Causes

| Symptom | Likely Cause | How to Verify |
|---------|--------------|---------------|
| High read I/O on backup storage | PBS backup running | `ps aux | grep vzdump` |
| High read I/O on VM disk | VM backup in progress | `qm config <id> | grep lock` |
| Sustained write I/O | ZFS scrub or resilver | `zpool status` |
| Spike then sustained I/O | Replication job | `pvesr status` |

## Anti-Patterns (What NOT to Do)

1. **Don't assume** the application you're working on is the cause
2. **Don't make changes** until you identify the actual process
3. **Don't restart services** hoping it fixes I/O issues
4. **Don't delete data** without understanding what's reading it

## Example: Misdiagnosis

In December 2025, high I/O on `local-20TB-zfs` was initially attributed to:
- Frigate detection (wrong)
- VirtioFS read-only mount (wrong)
- Symlinks to old recordings (wrong)
- PVC on USB storage (wrong)

**Actual cause**: PBS backup was reading an 18TB zvol attached to a VM.

**How it should have been diagnosed**:
```bash
# Step 1: What process?
for pid in $(ls /proc | grep -E '^[0-9]+$'); do
  bytes=$(awk '/read_bytes/ {print $2}' /proc/$pid/io 2>/dev/null)
  if [ "$bytes" -gt 1000000000 ] 2>/dev/null; then
    echo "$pid: $bytes - $(cat /proc/$pid/comm 2>/dev/null)"
  fi
done | sort -t: -k2 -rn | head -5

# Result: kvm and proxmox-backup- processes had highest I/O

# Step 2: Is there a backup?
ps aux | grep vzdump
qm config 105 | grep lock
# Result: lock: backup
```

Time to correct diagnosis: **2 minutes** vs **45 minutes** of wrong assumptions.
