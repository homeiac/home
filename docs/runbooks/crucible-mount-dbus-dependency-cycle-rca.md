# RCA: Crucible Mount Unit Causes Systemd Dependency Cycle, Kills dbus on Boot

**Date**: 2026-02-25
**Severity**: High
**Impact**: K3s VM failed to start after reboot; dbus, uuidd, apparmor, systemd-resolved all killed at boot
**Resolution**: Added `DefaultDependencies=no` to Crucible mount unit on all 5 Proxmox hosts

---

## Executive Summary

After rebooting pumped-piglet, the K3s GPU VM (VMID 105) failed to start with `org.freedesktop.DBus.Error.FileNotFound: Failed to connect to socket /run/dbus/system_bus_socket`. Investigation revealed that the Crucible NBD storage mount unit (`mnt-crucible\x2dstorage.mount`) created a systemd dependency cycle at boot. Systemd broke the cycle by dropping `dbus.socket` from the startup sequence, which cascaded into failures across the entire system. The same latent bug existed on all 5 Proxmox hosts.

### Failure Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        WHAT HAPPENED ON BOOT                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   pumped-piglet reboots                                                     │
│         │                                                                   │
│         ▼                                                                   │
│   systemd builds dependency graph                                           │
│         │                                                                   │
│         ▼                                                                   │
│   ╔═══════════════════════════════════════╗                                  │
│   ║  CYCLE DETECTED in boot graph!       ║                                  │
│   ║                                       ║                                  │
│   ║  sysinit ──► local-fs ──► crucible   ║                                  │
│   ║     ▲         mount ──► nbd-connect  ║                                  │
│   ║     │                       │         ║                                  │
│   ║     └───────────────────────┘         ║                                  │
│   ╚═══════════════════════════════════════╝                                  │
│         │                                                                   │
│         ▼                                                                   │
│   systemd drops jobs to break cycle                                         │
│         │                                                                   │
│         ├──► dbus.socket     ──► DROPPED  ╌╌╌► qm start FAILS              │
│         ├──► uuidd.socket    ──► DROPPED       pve-guests FAILS             │
│         ├──► local-fs.target ──► DROPPED       PAM sessions FAIL            │
│         └──► (others)        ──► DROPPED       pmxcfs FAILS                 │
│                                                                             │
│   Result: Host boots but is severely degraded                               │
│           VMs cannot start, SSH sessions impaired                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Investigation: How We Found the Cycle

This section documents the exact investigation steps so the methodology can be reused for any future systemd boot failures.

### Step 1: Identify the Symptom

The VM failed to start with a dbus error:
```
TASK ERROR: org.freedesktop.DBus.Error.FileNotFound: Failed to connect to socket /run/dbus/system_bus_socket: No such file or directory
```

First question: **Is dbus actually running?**

```bash
ssh root@pumped-piglet.maas "systemctl status dbus"
# Result: Active: inactive (dead)

ssh root@pumped-piglet.maas "ls -la /run/dbus/"
# Result: No system_bus_socket file — only an empty 'containers' subdir
```

dbus is completely dead. On a Proxmox host, dbus is critical infrastructure — it should always be running. Something prevented it from starting at boot.

### Step 2: Check Why dbus Didn't Start

dbus.socket and dbus.service are both `static` units (not `enabled`), meaning they rely on being pulled in as dependencies by other units rather than starting on their own. Check what pulls them in:

```bash
ssh root@pumped-piglet.maas "systemctl list-dependencies dbus.socket --reverse --no-pager"
# dbus.socket
# ├─dbus.service
# ├─systemd-logind.service
# └─sockets.target         ← dbus.socket is part of sockets.target
#   └─basic.target
#     └─multi-user.target
```

dbus.socket is pulled in via `sockets.target`. If `sockets.target` started normally, dbus should be running. Something must have interfered.

### Step 3: Check the Boot Journal for Errors

This is the key diagnostic command — **always check error-priority boot messages first**:

```bash
ssh root@pumped-piglet.maas "journalctl -b --no-pager -p err --lines=50"
```

The smoking gun was in the output:
```
sockets.target: Found ordering cycle on dbus.socket/start
sockets.target: Job dbus.socket/start deleted to break ordering cycle starting with sockets.target/start
```

**Translation**: systemd detected a circular dependency during boot. To break the deadlock, it **dropped** `dbus.socket` from the startup plan. This is systemd's last-resort cycle-breaking mechanism — it sacrifices jobs to prevent a boot hang.

### Step 4: Trace the Full Cycle Chain

The journal showed multiple cycles. To understand the full chain, filter for all cycle messages:

```bash
ssh root@pumped-piglet.maas "journalctl -b --no-pager | grep -i 'ordering cycle'"
```

Output (annotated):
```
sockets.target: Found ordering cycle on uuidd.socket/start                    # victim 1
sockets.target: Job uuidd.socket/start deleted to break ordering cycle
basic.target: Found ordering cycle on systemd-pcrphase-sysinit.service/start  # victim 2
basic.target: Job systemd-pcrphase-sysinit.service/start deleted
sockets.target: Found ordering cycle on dbus.socket/start                     # victim 3 (THE critical one)
sockets.target: Job dbus.socket/start deleted
crucible-nbd-connect.service: Found ordering cycle on sysinit.target/start    # THE CYCLE SOURCE
crucible-nbd-connect.service: Job local-fs.target/start deleted
```

The last two lines reveal the cycle source: `crucible-nbd-connect.service` has a cycle involving `sysinit.target` and `local-fs.target`.

### Step 5: Understand WHY crucible-nbd-connect Creates a Cycle

Read the service unit and its dependencies:

```bash
ssh root@pumped-piglet.maas "cat /etc/systemd/system/crucible-nbd-connect.service"
# [Unit]
# After=crucible-nbd.service
# Requires=crucible-nbd.service
# [Install]
# WantedBy=multi-user.target
```

This service itself looks fine — it depends on `crucible-nbd.service` and is wanted by `multi-user.target`. But the journal said `local-fs.target` was involved. What pulls `local-fs.target` into this?

Check for mount units:

```bash
ssh root@pumped-piglet.maas "ls /etc/systemd/system/*.mount"
# /etc/systemd/system/mnt-crucible\x2dstorage.mount

ssh root@pumped-piglet.maas "cat '/etc/systemd/system/mnt-crucible\x2dstorage.mount'"
# [Unit]
# After=crucible-nbd-connect.service
# Requires=crucible-nbd-connect.service
# [Mount]
# What=/dev/nbd0
# Where=/mnt/crucible-storage
```

**Key insight**: This is a `.mount` unit. systemd has special handling for `.mount` units — unless you set `DefaultDependencies=no`, systemd automatically adds implicit dependencies including `Before=local-fs.target`. This means:

1. `local-fs.target` waits for the Crucible mount to complete
2. But the Crucible mount needs `crucible-nbd-connect.service`
3. Which implicitly needs `sysinit.target` (all services do by default)
4. But `sysinit.target` needs `local-fs.target` to complete first
5. **Cycle!**

### Step 6: Verify the Cycle with systemd-analyze

The definitive proof:

```bash
ssh root@pumped-piglet.maas "systemd-analyze verify 'mnt-crucible\x2dstorage.mount' 2>&1"
```

This outputs the exact cycle chain:
```
sysinit.target: Found ordering cycle on systemd-binfmt.service/start
sysinit.target: Found dependency on local-fs.target/start
sysinit.target: Found dependency on mnt-crucible\x2dstorage.mount/start
sysinit.target: Found dependency on crucible-nbd-connect.service/start
sysinit.target: Found dependency on sysinit.target/start    ← CYCLE CONFIRMED
```

### Step 7: Check if Other Hosts Have the Same Bug

```bash
ssh root@still-fawn.maas "journalctl -b --no-pager | grep -i 'ordering cycle' | head -5"
# local-fs.target: Found ordering cycle on mnt-crucible\x2dstorage.mount/start
# local-fs.target: Job mnt-crucible\x2dstorage.mount/start deleted
```

Same cycle on still-fawn, but systemd chose to drop the **mount itself** instead of dbus — so still-fawn appeared healthy while carrying the same latent bug.

### Investigation Flow

```
┌─────────────────────────┐
│  Symptom: qm start      │
│  fails with dbus error   │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐     ┌──────────────────────────┐
│  Is dbus running?        │────►│  YES: Problem is          │
│  systemctl status dbus   │     │  elsewhere (not this RCA) │
└────────────┬────────────┘     └──────────────────────────┘
             │ NO
             ▼
┌─────────────────────────┐     ┌──────────────────────────┐
│  Check boot errors       │────►│  No cycles: dbus may have │
│  journalctl -b -p err    │     │  a config/package issue   │
│  grep "ordering cycle"   │     └──────────────────────────┘
└────────────┬────────────┘
             │ CYCLES FOUND
             ▼
┌─────────────────────────┐     ┌──────────────────────────┐
│  Which unit is the       │     │  Not a mount: check the   │
│  cycle source?           │────►│  unit's After=/Requires=  │
│  grep "Found dependency" │     │  for circular refs        │
└────────────┬────────────┘     └──────────────────────────┘
             │ IT'S A .mount UNIT
             ▼
┌─────────────────────────┐     ┌──────────────────────────┐
│  Does it have            │────►│  YES: Different problem.  │
│  DefaultDependencies=no? │     │  Check After=/Requires=   │
└────────────┬────────────┘     └──────────────────────────┘
             │ NO (MISSING!)
             ▼
┌─────────────────────────┐
│  ROOT CAUSE FOUND        │
│  Add DefaultDeps=no      │
│  Run fix script          │
│  Check all other hosts   │
└─────────────────────────┘
```

### Investigation Summary

| Step | Command | What It Reveals |
|------|---------|-----------------|
| 1 | `systemctl status dbus` | Is the critical service running? |
| 2 | `systemctl list-dependencies dbus.socket --reverse` | What should have started it? |
| 3 | `journalctl -b -p err --lines=50` | Boot errors including cycle-breaking messages |
| 4 | `journalctl -b \| grep -i "ordering cycle"` | Full list of all cycles and victims |
| 5 | `cat /etc/systemd/system/*.mount` | Find mount units that may cause cycles |
| 6 | `systemd-analyze verify '<unit>'` | Definitively prove the cycle exists |
| 7 | Check other hosts | Is this a fleet-wide latent bug? |

---

## Root Cause Analysis

### Problem Statement

The Crucible storage mount unit is a `.mount` unit that systemd **automatically** adds to `local-fs.target` (via default dependencies). However, the mount depends on `crucible-nbd-connect.service`, which itself cannot start until `sysinit.target` completes. Since `local-fs.target` is a dependency of `sysinit.target`, this creates a circular dependency.

### The Dependency Cycle

```
                    ┌──────────────────────────────────────────────────────────┐
                    │                  NORMAL BOOT ORDER                       │
                    │                                                          │
                    │  sysinit.target ──► basic.target ──► multi-user.target   │
                    │       │                                                  │
                    │       ├──► sockets.target ──► dbus.socket                │
                    │       │                                                  │
                    │       └──► local-fs.target                               │
                    │                 │                                        │
                    │                 └──► (local block device mounts)         │
                    │                                                          │
                    └──────────────────────────────────────────────────────────┘

                    ┌──────────────────────────────────────────────────────────┐
                    │              WITH CRUCIBLE MOUNT (THE BUG)               │
                    │                                                          │
                    │              ┌─────────── CYCLE ───────────┐             │
                    │              │                              │             │
                    │              ▼                              │             │
                    │       sysinit.target                        │             │
                    │           │                                 │             │
                    │           └──► local-fs.target              │             │
                    │                     │                       │             │
                    │                     │  (systemd auto-adds   │             │
                    │                     │   .mount units here)  │             │
                    │                     ▼                       │             │
                    │            crucible-storage.mount           │             │
                    │                     │                       │             │
                    │                     │  Requires=            │             │
                    │                     ▼                       │             │
                    │          crucible-nbd-connect.service       │             │
                    │                     │                       │             │
                    │                     │  (implicit default    │             │
                    │                     │   dependency)         │             │
                    │                     └───────────────────────┘             │
                    │                                                          │
                    │  systemd breaks cycle by DROPPING jobs:                  │
                    │    ✗ dbus.socket (collateral damage)                     │
                    │    ✗ uuidd.socket                                        │
                    │    ✗ local-fs.target                                     │
                    │                                                          │
                    └──────────────────────────────────────────────────────────┘
```

### Why dbus Was the Victim

Systemd's cycle-breaking algorithm drops jobs to resolve the cycle. The algorithm does not prioritize critical services - it picks based on graph traversal order. On pumped-piglet, it dropped:

| Dropped Job | Impact |
|-------------|--------|
| `dbus.socket` | No D-Bus IPC - breaks `qm start`, `pve-guests`, PAM sessions |
| `uuidd.socket` | No UUID generation |
| `systemd-pcrphase-sysinit.service` | TPM PCR phase tracking broken |
| `local-fs.target` | Local filesystem target not reached |

On still-fawn (same bug), systemd chose differently and only dropped the mount itself - so dbus survived. The outcome is **non-deterministic** and depends on boot timing.

```
  Same bug, different victims:
  ════════════════════════════

  pumped-piglet                          still-fawn
  ┌────────────────────────┐             ┌────────────────────────┐
  │  Cycle detected!       │             │  Cycle detected!       │
  │                        │             │                        │
  │  Dropped:              │             │  Dropped:              │
  │    ✗ dbus.socket       │             │    ✗ crucible mount    │
  │    ✗ uuidd.socket      │             │                        │
  │    ✗ local-fs.target   │             │  Kept:                 │
  │    ✗ apparmor          │             │    ✓ dbus.socket       │
  │    ✗ systemd-resolved  │             │    ✓ local-fs.target   │
  │                        │             │    ✓ everything else   │
  │  Outcome:              │             │                        │
  │    VMs can't start     │             │  Outcome:              │
  │    PAM broken          │             │    Looks healthy!      │
  │    SSH degraded        │             │    (mount just missing) │
  │                        │             │                        │
  │  CATASTROPHIC          │             │  SILENT / LATENT       │
  └────────────────────────┘             └────────────────────────┘
```

### The Buggy Unit File

```ini
# /etc/systemd/system/mnt-crucible\x2dstorage.mount (BEFORE fix)
[Unit]
Description=Crucible Storage Mount
After=crucible-nbd-connect.service
Requires=crucible-nbd-connect.service

[Mount]
What=/dev/nbd0
Where=/mnt/crucible-storage
Type=ext4
Options=defaults,noatime

[Install]
WantedBy=multi-user.target
```

The problem: **No `DefaultDependencies=no`**. Without this, systemd adds implicit dependencies that pull the mount into `local-fs.target`, creating the cycle.

### Contributing Factors

1. **systemd default behavior**: `.mount` units get auto-added to `local-fs.target` unless `DefaultDependencies=no` is set
2. **NBD is not a local filesystem**: The Crucible mount depends on network services (NBD client/server) but systemd treats it as a local mount
3. **Non-deterministic failure**: The bug existed on all hosts but only manifested catastrophically on pumped-piglet due to systemd's cycle-breaking algorithm choosing different victims per host
4. **No monitoring**: No alerting on systemd dependency cycles or dbus failures

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 2026-02-25 16:03:08 | pumped-piglet boots, systemd detects ordering cycles |
| 2026-02-25 16:03:08 | systemd drops `dbus.socket`, `uuidd.socket`, `local-fs.target` to break cycles |
| 2026-02-25 16:03:12 | `pmxcfs` fails (quorum_initialize, cpg_initialize) - no dbus |
| 2026-02-25 16:03:22 | `pve-guests` fails trying to auto-start VM 105 - no dbus socket |
| 2026-02-25 16:05:07 | SSH sessions show `pam_systemd: Failed to connect to system bus` |
| 2026-02-25 16:05:24 | Manual fix: `systemctl start dbus.socket && systemctl start dbus.service` |
| 2026-02-25 ~16:05:30 | `qm start 105` succeeds, K3s VM running |
| 2026-02-25 ~16:10:00 | Root cause identified: Crucible mount dependency cycle |
| 2026-02-25 ~16:15:00 | Fix applied to all 5 Proxmox hosts |

---

## Resolution

### Fix Applied

Added `DefaultDependencies=no` to the mount unit's `[Unit]` section on all Proxmox hosts:

```ini
# /etc/systemd/system/mnt-crucible\x2dstorage.mount (AFTER fix)
[Unit]
Description=Crucible Storage Mount
DefaultDependencies=no
After=crucible-nbd-connect.service
Requires=crucible-nbd-connect.service

[Mount]
What=/dev/nbd0
Where=/mnt/crucible-storage
Type=ext4
Options=defaults,noatime

[Install]
WantedBy=multi-user.target
```

`DefaultDependencies=no` prevents systemd from automatically adding:
- `Before=local-fs.target` (the cycle trigger)
- `Requires=local-fs.target` / `After=local-fs.target` implicit deps
- Various `sysinit.target` ordering constraints

The mount still starts via `WantedBy=multi-user.target`, which is the correct ordering for a network-backed filesystem.

### Before vs After: How the Fix Breaks the Cycle

```
  BEFORE (DefaultDependencies=yes, the default)         AFTER (DefaultDependencies=no)
  ══════════════════════════════════════════════         ═══════════════════════════════

  sysinit.target                                         sysinit.target
      │                                                      │
      ├──► sockets.target ──► dbus.socket                    ├──► sockets.target ──► dbus.socket  ✓
      │                                                      │
      └──► local-fs.target                                   └──► local-fs.target  ✓
                │                                                  (no crucible mount here!)
                └──► crucible-storage.mount ◄── INJECTED
                          │                     BY SYSTEMD
                          └──► crucible-nbd-connect             multi-user.target
                                    │                               │
                                    └──► [sysinit.target]           └──► crucible-storage.mount  ✓
                                              │                              │
                                              └──── CYCLE! ────             └──► crucible-nbd-connect  ✓
                                                                                     │
                                                                                     └──► crucible-nbd  ✓
                                                                                          (network-online)

  Result: dbus KILLED                                    Result: Everything starts in order
```

### Hosts Fixed

| Host | Fixed | Verified |
|------|-------|----------|
| pumped-piglet | Yes | `systemd-analyze verify` clean |
| still-fawn | Yes | `systemd-analyze verify` clean |
| pve | Yes | `systemctl daemon-reload` done |
| chief-horse | Yes | `systemctl daemon-reload` done |
| fun-bedbug | Yes | `systemctl daemon-reload` done |

---

## Verification

```bash
# 1. Check for dependency cycles (should return nothing)
systemd-analyze verify 'mnt-crucible\x2dstorage.mount' 2>&1

# 2. After next reboot, check dbus is running
systemctl is-active dbus.socket dbus.service

# 3. Check no ordering cycles in journal
journalctl -b | grep -i "ordering cycle"

# 4. Check Crucible mount is working
mount | grep crucible
```

---

## Lessons Learned

### What Went Wrong

1. `.mount` units for network-backed storage (NBD) must not use systemd's default dependencies, which assume local block devices
2. The bug was latent on all 5 hosts since Crucible was deployed but only triggered catastrophic failure on pumped-piglet after a reboot
3. still-fawn had the same cycle but systemd broke it differently (dropped the mount instead of dbus), masking the severity

### What Went Right

1. The dbus error message was specific enough to diagnose quickly
2. Starting dbus manually was a clean workaround
3. `journalctl -b -p err` immediately showed the cycle-breaking messages

### Improvements

| Area | Improvement |
|------|-------------|
| Monitoring | Add alerting on `journalctl` messages containing "ordering cycle" |
| Monitoring | Add check for `systemctl is-active dbus` in node health checks |
| Process | Review all custom `.mount` units for `DefaultDependencies=no` when they depend on non-local services |
| Testing | Run `systemd-analyze verify` on all custom units as part of deployment |

---

## Prevention

### Design Principle

**Any `.mount` unit that depends on a service (not just a block device) MUST set `DefaultDependencies=no`** to prevent being auto-added to `local-fs.target`. This applies to:

- NBD mounts (Crucible)
- NFS mounts
- iSCSI mounts
- Any mount requiring network connectivity

### Detection Script

See: `scripts/crucible/fix-mount-dependency-cycle.sh`

---

## References

- [Crucible Mount Dependency Cycle Runbook](crucible-mount-dependency-cycle-runbook.md)
- [Proxmox Systemd Degraded State Fix](proxmox-systemd-degraded-state-fix.md)
- [systemd.mount(5) - DefaultDependencies](https://www.freedesktop.org/software/systemd/man/systemd.mount.html)

---

**Tags**: crucible, cruicble, systemd, systemctl, dbus, d-bus, dependency-cycle, ordering-cycle, boot-failure, boot, reboot, VM-not-starting, local-fs-target, DefaultDependencies, nbd, mount, proxmox, pumped-piglet, still-fawn, pve, chief-horse, fun-bedbug, k3s, qm-start

**Owner**: homelab
**Last Updated**: 2026-02-25
