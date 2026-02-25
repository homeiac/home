# Runbook: Crucible Mount Systemd Dependency Cycle

## When to Use This Runbook

Use this runbook when you observe ANY of the following after a Proxmox host reboot:

- `qm start` fails with: `org.freedesktop.DBus.Error.FileNotFound: Failed to connect to socket /run/dbus/system_bus_socket`
- SSH login shows: `pam_systemd(sshd:session): Failed to connect to system bus`
- `systemctl status` shows `State: degraded` with dbus or other core services dead
- `journalctl -b` shows: `Found ordering cycle on ... /start`
- VMs with `onboot: 1` fail to auto-start after reboot

### Decision Flowchart

```
┌──────────────────────────────────────┐
│  VM won't start / dbus error         │
│  after Proxmox reboot                │
└──────────────────┬───────────────────┘
                   │
                   ▼
        ┌─────────────────────┐
        │  Need VMs running   │──── YES ──► Quick Fix (below)
        │  RIGHT NOW?         │             systemctl start dbus.socket
        └─────────┬───────────┘             systemctl start dbus.service
                  │ NO                      qm start <VMID>
                  ▼
        ┌─────────────────────┐
        │  Want automated     │──── YES ──► scripts/crucible/
        │  fix?               │             fix-mount-dependency-cycle.sh
        └─────────┬───────────┘
                  │ NO (want to understand)
                  ▼
        ┌─────────────────────┐
        │  Go to Diagnosis    │
        │  section below      │
        └─────────────────────┘
```

---

## Quick Fix (Get VMs Running Immediately)

If you need VMs running NOW before investigating the root cause:

```bash
# Start dbus (the immediate blocker)
systemctl start dbus.socket
systemctl start dbus.service

# Start the VM
qm start <VMID>
```

This is a **temporary workaround**. dbus will not survive the next reboot unless the root cause is fixed.

---

## Diagnosis

### Step 1: Confirm dbus is dead

```bash
systemctl is-active dbus.socket dbus.service
# Expected (if broken): "inactive" for both

# Also check the socket file directly
ls -la /run/dbus/system_bus_socket
# If missing, dbus never started
```

**Why dbus?** dbus is the system message bus. Proxmox uses it for VM management (`qm`), guest agent comms, and PAM sessions. If dbus is dead after boot, something prevented it from starting — most commonly a dependency cycle.

### Step 2: Check the boot journal for cycle-breaking messages

This is the most important diagnostic command:

```bash
journalctl -b --no-pager -p err --lines=50
```

Look for lines containing **"ordering cycle"** and **"deleted to break"**:
```
sockets.target: Found ordering cycle on dbus.socket/start
sockets.target: Job dbus.socket/start deleted to break ordering cycle starting with sockets.target/start
```

**What this means**: systemd detected a circular dependency at boot. To avoid a deadlock, it sacrificed `dbus.socket` by removing it from the startup plan. systemd picks victims non-deterministically — the same cycle may kill different services on different hosts or different boots.

### Step 3: Trace the full cycle chain

Get ALL cycle messages to find the root cause (not just the victim):

```bash
journalctl -b --no-pager | grep -i "ordering cycle"
```

Look for the **dependency chain** that systemd reports:
```
crucible-nbd-connect.service: Found ordering cycle on sysinit.target/start
crucible-nbd-connect.service: Found dependency on local-fs.target/start          # ← connects to sysinit
crucible-nbd-connect.service: Found dependency on mnt-crucible\x2dstorage.mount  # ← the mount unit
crucible-nbd-connect.service: Found dependency on crucible-nbd-connect.service   # ← back to start
crucible-nbd-connect.service: Found dependency on sysinit.target/start           # ← CYCLE
```

### Step 4: Confirm the Crucible mount is the cycle source

```bash
# Quick check: is DefaultDependencies=no present?
grep -c "DefaultDependencies" /etc/systemd/system/mnt-crucible\\x2dstorage.mount
# 0 = missing (broken), 1 = present (fixed)

# Definitive proof: run systemd's built-in cycle detector
systemd-analyze verify 'mnt-crucible\x2dstorage.mount' 2>&1
# Any "ordering cycle" output = broken
# Clean/empty output = fixed
```

**Why this specific unit?** `.mount` units get special treatment by systemd — they are automatically added to `local-fs.target` unless `DefaultDependencies=no` is set. Since our mount depends on `crucible-nbd-connect.service` (a network service), this creates a cycle: `sysinit.target → local-fs.target → mount → nbd-service → sysinit.target`.

### Step 5: Check other hosts for the same latent bug

```bash
# Run from your Mac against all hosts
for host in pumped-piglet still-fawn pve chief-horse fun-bedbug; do
    echo "=== $host ==="
    ssh root@$host.maas "journalctl -b | grep -c 'ordering cycle'" 2>/dev/null
done
```

**Important**: A host may have the cycle but not show symptoms if systemd breaks the cycle by dropping a non-critical job. still-fawn had the same cycle but dropped the mount itself (not dbus), so it appeared healthy.

### General Methodology for Any Systemd Boot Failure

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  1. SERVICE DOWN │────►│  2. WHO STARTS   │────►│  3. BOOT JOURNAL │
│                  │     │     IT?           │     │                  │
│  systemctl       │     │  list-deps        │     │  journalctl -b   │
│  is-active XXX   │     │  --reverse        │     │  -p err          │
└──────────────────┘     └──────────────────┘     └────────┬─────────┘
                                                           │
                                          ┌────────────────┴──────────────┐
                                          │                               │
                                          ▼                               ▼
                                  ┌──────────────┐               ┌──────────────┐
                                  │  CYCLE FOUND │               │  NO CYCLE    │
                                  │              │               │              │
                                  │  grep for    │               │  Check unit  │
                                  │  "ordering   │               │  config, pkg │
                                  │   cycle"     │               │  status, etc │
                                  └──────┬───────┘               └──────────────┘
                                         │
                              ┌──────────┴──────────┐
                              │                     │
                              ▼                     ▼
                      ┌──────────────┐      ┌──────────────┐
                      │  .mount unit │      │  Other unit  │
                      │              │      │              │
                      │  Check for   │      │  Check       │
                      │  DefaultDeps │      │  After= and  │
                      │  =no         │      │  Requires=   │
                      └──────────────┘      └──────────────┘
                              │
                              ▼
                      ┌──────────────┐      ┌──────────────┐
                      │  VERIFY FIX  │────►│  CHECK FLEET │
                      │              │      │              │
                      │  systemd-    │      │  Same bug on │
                      │  analyze     │      │  other hosts?│
                      │  verify      │      │              │
                      └──────────────┘      └──────────────┘
```

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `systemctl is-active <service>` | Is the service running? |
| 2 | `systemctl list-dependencies <unit> --reverse` | What should have started it? |
| 3 | `journalctl -b -p err --lines=50` | Boot errors, cycle-breaking msgs |
| 4 | `journalctl -b \| grep "ordering cycle"` | All cycles and their victims |
| 5 | `ls /etc/systemd/system/*.mount` | Custom mount units (common cycle source) |
| 6 | `systemd-analyze verify '<unit>'` | Prove a specific unit has a cycle |
| 7 | Check fleet | Is the bug latent on other hosts? |

---

## Fix Procedure

### Option A: Run the automated script (recommended)

```bash
# From the home repo on your Mac:
scripts/crucible/fix-mount-dependency-cycle.sh

# Target a specific host:
scripts/crucible/fix-mount-dependency-cycle.sh pumped-piglet.maas

# Dry run (check only, no changes):
scripts/crucible/fix-mount-dependency-cycle.sh --check
```

### Option B: Manual fix on a single host

```bash
# SSH to the affected host
ssh root@<hostname>.maas

# Edit the mount unit
cat > '/etc/systemd/system/mnt-crucible\x2dstorage.mount' << 'EOF'
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
EOF

# Reload systemd
systemctl daemon-reload

# Verify no cycles
systemd-analyze verify 'mnt-crucible\x2dstorage.mount' 2>&1
```

---

## Post-Fix Verification

### Immediately after fix (no reboot needed)

```bash
# 1. Verify no dependency cycles detected
systemd-analyze verify 'mnt-crucible\x2dstorage.mount' 2>&1
# Should produce no output

# 2. Verify the unit file has the fix
grep "DefaultDependencies=no" /etc/systemd/system/mnt-crucible\\x2dstorage.mount
# Should return the line

# 3. If dbus was down, start it
systemctl start dbus.socket dbus.service
systemctl is-active dbus.socket dbus.service
# Both should show "active"
```

### After next reboot

```bash
# 1. dbus should be running
systemctl is-active dbus.socket dbus.service

# 2. No ordering cycles in journal
journalctl -b | grep -c "ordering cycle"
# Should be 0

# 3. Crucible mount should be up
mount | grep crucible-storage
# Should show /mnt/crucible-storage

# 4. VMs with onboot=1 should have auto-started
qm list | grep running
```

---

## Affected Hosts

All Proxmox hosts with Crucible NBD storage:

```
                              ┌─────────────────────────┐
                              │   Proper Raptor (Oxide)  │
                              │   192.168.4.189          │
                              │   Crucible Storage       │
                              └────────────┬────────────┘
                                           │ NBD (TCP 3840-3842)
                 ┌─────────────┬───────────┼───────────┬─────────────┐
                 │             │           │           │             │
                 ▼             ▼           ▼           ▼             ▼
          ┌────────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
          │ pumped-    │ │ still-   │ │  pve   │ │ chief-   │ │  fun-    │
          │ piglet     │ │ fawn     │ │        │ │ horse    │ │ bedbug   │
          │            │ │          │ │        │ │          │ │          │
          │ VM 105     │ │ VM 108   │ │ VM 107 │ │ VM 116   │ │ LXC 114 │
          │ K3s+GPU    │ │ K3s+VAAPI│ │ standby│ │ HAOS     │ │ disabled │
          │            │ │          │ │        │ │          │ │          │
          │ /mnt/      │ │ /mnt/    │ │ /mnt/  │ │ /mnt/    │ │ /mnt/    │
          │ crucible-  │ │ crucible-│ │ cruci- │ │ crucible-│ │ crucible-│
          │ storage    │ │ storage  │ │ ble-   │ │ storage  │ │ storage  │
          │            │ │          │ │ storage│ │          │ │          │
          └────────────┘ └──────────┘ └────────┘ └──────────┘ └──────────┘
              ALL 5 hosts had the same latent dependency cycle bug
```

| Host | VMID(s) | Crucible Mount |
|------|---------|----------------|
| pumped-piglet.maas | 105 (K3s GPU) | /mnt/crucible-storage |
| still-fawn.maas | 108 (K3s) | /mnt/crucible-storage |
| pve.maas | 107 (K3s standby) | /mnt/crucible-storage |
| chief-horse.maas | 116 (HAOS) | /mnt/crucible-storage |
| fun-bedbug.maas | 114 (K3s disabled) | /mnt/crucible-storage |

---

## Understanding the Cycle

### The Crucible Storage Stack

```
┌─────────────────────────────────────────────────────────────────┐
│                    CRUCIBLE STORAGE STACK                        │
│                                                                 │
│  Proper Raptor (Oxide)        Proxmox Host                      │
│  ┌──────────────────┐         ┌──────────────────────────────┐  │
│  │  Crucible storage │ ◄─NBD──│  crucible-nbd.service        │  │
│  │  (192.168.4.189)  │  net   │  (nbd-server wrapper)        │  │
│  └──────────────────┘         │           │                  │  │
│                               │           ▼                  │  │
│                               │  crucible-nbd-connect.service│  │
│                               │  (nbd-client 127.0.0.1:10809)│  │
│                               │           │                  │  │
│                               │           ▼                  │  │
│                               │  /dev/nbd0                   │  │
│                               │           │                  │  │
│                               │           ▼                  │  │
│                               │  mnt-crucible-storage.mount  │  │
│                               │  (ext4 → /mnt/crucible)      │  │
│                               └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Why the Cycle Exists

```
  WITHOUT DefaultDependencies=no:         WITH DefaultDependencies=no:
  ═══════════════════════════════         ════════════════════════════

  systemd adds IMPLICIT deps             No implicit deps added
  to .mount units:                        Mount only starts when
    Before=local-fs.target                multi-user.target pulls it in
    After=local-fs-pre.target

       sysinit.target ◄─────────┐             sysinit.target
           │                     │                 │
           ▼                     │                 ▼
       local-fs.target           │             sockets.target ──► dbus  ✓
           │                     │                 │
           ▼ (auto-injected)     │                 ▼
   ┌── crucible mount ──┐       │             basic.target
   │       │             │       │                 │
   │       ▼             │       │                 ▼
   │  nbd-connect.svc    │       │             multi-user.target
   │       │             │       │                 │
   │       │  (implicit  │       │                 ├──► crucible mount  ✓
   │       │   default   │       │                 │        │
   │       │   dep)      │       │                 │        ▼
   │       └─────────────┘───────┘                 │    nbd-connect  ✓
   │                                               │
   └── CYCLE ──► dbus KILLED                       └──► ALL SERVICES START  ✓
```

---

## Related Documentation

- [RCA: Crucible Mount dbus Dependency Cycle](crucible-mount-dbus-dependency-cycle-rca.md)
- [Proxmox Systemd Degraded State Fix](proxmox-systemd-degraded-state-fix.md)

---

**Tags**: crucible, cruicble, systemd, dbus, d-bus, dependency-cycle, ordering-cycle, boot, reboot, runbook, fix, DefaultDependencies, mount, nbd, proxmox, qm-start, VM-not-starting

**Owner**: homelab
**Last Updated**: 2026-02-25
