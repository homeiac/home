# Troubleshooting: Loud Fan on Intel NUC (chief-horse) - PBS Backup

**Date**: 2025-12-21
**Symptom**: Loud fan noise from Intel NUC
**Root Cause**: Daily PBS backup job at 22:30 UTC

## Investigation Flowchart

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LOUD FAN TROUBLESHOOTING FLOWCHART                       │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│ User reports:        │
│ "Someone's fan is    │
│  working very hard"  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐     ┌─────────────────────────────────────────────┐
│ Check all 4 Proxmox  │     │ Results:                                    │
│ hosts via SSH:       │────▶│  • chief-horse: load 4.54 ← HIGH!           │
│ uptime + ps aux      │     │  • still-fawn:  load 1.37                   │
│                      │     │  • pumped-piglet: load 2.53                 │
└──────────────────────┘     │  • fun-bedbug: load 0.28                    │
                             └──────────────────┬──────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ✅ Claude correctly identifies: chief-horse has high load                   │
│ ❌ BUT incorrectly identifies the hardware as "N100 mini-PC"                │
│                                                                             │
│ User sees "N100" → knows pve.maas is the N100 → thinks Claude is wrong     │
│ User: "no it is coming from the intel nux"                                  │
│ (User means: chief-horse IS the Intel NUC, not N100)                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ❌ CLAUDE FUCKUP #1: Misunderstood user's correction                        │
│    Thought user was saying "different machine"                              │
│    Actually user was saying "right machine, wrong hardware label"           │
│    Claude tries SSH to still-fawn and pumped-piglet                         │
│    User: "it is neither" → "fucking read the docs to find out"              │
└─────────────────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
┌──────────────────────┐     ┌─────────────────────────────────────────────┐
│ Claude reads docs    │     │ Docs say (WRONG):                           │
│ homelab-service-     │────▶│  • pve.maas: "Intel Xeon"                   │
│ inventory.md         │     │  • chief-horse: "Intel Xeon"                │
└──────────────────────┘     └──────────────────┬──────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ❌ CLAUDE FUCKUP #2: Docs were wrong, Claude trusted them                   │
│    User: "omg when did intel nuc ever have i5"                              │
│    User: "is n100 i3?" → Claude explains N100 is not i-series               │
│    User: "i don't have 2 N100 mini-pc.. pve.maas has n100"                  │
│    User: "so fucker the inventory needs update"                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
┌──────────────────────┐     ┌─────────────────────────────────────────────┐
│ Finally check actual │     │ Results:                                    │
│ hardware via lscpu:  │────▶│  • pve.maas: Intel N100 mini-PC             │
│                      │     │  • chief-horse: Intel i3-4010U NUC ← THIS!  │
└──────────────────────┘     └──────────────────┬──────────────────────────┘
                                                │
                                                ▼
┌──────────────────────┐
│ Update docs +        │
│ OpenMemory with      │
│ correct hardware     │
└──────────┬───────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ❌ CLAUDE FUCKUP #3: Said "k3s-vm on chief horse" causing load              │
│    User: "k3s-vm on chief horse?"                                           │
│    qm list shows: VM 109 STOPPED, only HAOS (VM 116) running                │
└─────────────────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ❌ CLAUDE FUCKUP #4: Said "maybe a backup" without checking                 │
│    User: "instead of fucking maybe, can't you fucking look at pbs"          │
└─────────────────────────────────────────────────────────────────────────────┘
                                                │
                                                ▼
┌──────────────────────┐     ┌─────────────────────────────────────────────┐
│ Check backup jobs:   │     │ Found: backup-ff3d789f-f52b                 │
│ pvesh + journalctl   │────▶│  • Schedule: 22:30 UTC daily                │
│                      │     │  • Started: Dec 21 22:30:06                 │
│                      │     │  • Target: HAOS VM 116                      │
└──────────────────────┘     └──────────────────┬──────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            ROOT CAUSE IDENTIFIED                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Daily PBS backup of HAOS (VM 116) at 22:30 UTC / 14:30 PST                │
│  on chief-horse (i3-4010U NUC) causing 30% iowait for ~25 min              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Root Cause Details

### Backup Job Configuration

```
Job ID:        backup-ff3d789f-f52b
Schedule:      22:30 UTC daily (14:30 PST)
Mode:          snapshot
Target:        All VMs except LXC 103 (PBS itself)
Storage:       homelab-backup (PBS on pumped-piglet)
Retention:     keep-daily=3, keep-weekly=2
```

### Why It Causes High Load

- **Hardware**: chief-horse is Intel Core i3-4010U @ 1.70GHz (4 cores, Haswell NUC)
- **VM being backed up**: HAOS (VM 116) - 6GB RAM, 40GB disk
- **I/O Impact**: 50-90 MB/s sustained ZFS reads, 700-1800 IOPS
- **CPU Impact**: Load spikes to 4.54 (100%+ on 4-core), 30% iowait
- **Duration**: ~25 minutes

### Grafana Evidence

CPU graph showed:
- 14:30-14:55 PST: Yellow "Busy Iowait" at ~30%
- 14:55 PST: Returned to 95.5% idle after backup completion

## Hardware Inventory Corrections

This investigation revealed incorrect hardware labels in `docs/reference/homelab-service-inventory.md`:

| Host | Docs Said | Actually Is |
|------|-----------|-------------|
| pve.maas | Intel Xeon | Intel N100 (Alder Lake-N mini-PC) |
| chief-horse.maas | Intel Xeon | Intel Core i3-4010U (Haswell NUC) |

Docs were updated to reflect actual hardware.

## Lessons Learned

1. **KNOW YOUR HARDWARE** - Don't mislabel machines with wrong CPU types
2. **When user corrects terminology** - Ask "same machine, wrong label?" before hunting for other machines
3. **Docs can be wrong** - Verify with `lscpu` before trusting inventory docs
4. **Check `qm list`** - Before assuming which VM is causing load on a host
5. **Check backup/cron IMMEDIATELY** - Don't say "maybe" when investigating load spikes

## Quick Reference Commands

```bash
# Check load on all hosts
for host in pve chief-horse pumped-piglet fun-bedbug; do
  echo "=== $host ===" && ssh root@$host.maas uptime
done

# Check what's running on a host
ssh root@chief-horse.maas "qm list"

# Check backup job schedule
ssh root@chief-horse.maas "pvesh get /cluster/backup"

# Check recent backup activity
ssh root@chief-horse.maas "journalctl --since '1 hour ago' | grep -i vzdump"

# Check actual CPU model
ssh root@chief-horse.maas "lscpu | grep 'Model name'"
```

## Tags

troubleshooting, fan-noise, loud-fan, backup, pbs, proxmox-backup-server, vzdump, chief-horse, intel-nuc, i3-4010u, haos, home-assistant, iowait, zfs, lessons-learned
