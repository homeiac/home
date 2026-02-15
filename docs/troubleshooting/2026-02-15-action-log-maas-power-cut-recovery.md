# Action Log: MAAS Power-Cut Recovery

**Date**: 2026-02-15
**Operator**: Claude Code AI Agent
**Related Runbook**: `docs/runbooks/maas-power-cut-recovery.md`
**Status**: Completed

---

## Context

Power outage occurred overnight. Mac USB Ethernet adapter received link-local IP (`169.254.x.x`) instead of DHCP from MAAS, indicating MAAS VM was down or unreachable.

---

## Recovery Execution

### Step 1: Identify USB Adapter Interface

**Timestamp**: ~09:15

```bash
networksetup -listallhardwareports | grep -A2 "USB 10/100"
```

**Finding**: USB adapter is `en10` (not en4 as initially assumed)

```
Hardware Port: USB 10/100/1000 LAN
Device: en10
Ethernet Address: b0:a4:60:ae:77:0b
```

**Status**: Interface showing link-local `169.254.185.72` - confirms no DHCP

---

### Step 2: Assign Static IP

**Timestamp**: 09:16

```bash
sudo ifconfig en10 192.168.4.250 netmask 255.255.255.0
```

**Result**: Static IP assigned from reserved range

---

### Step 3: Test Connectivity to pve

**Timestamp**: 09:17

```bash
ping -c 3 192.168.4.122
```

**Initial Result**: `Request timeout` - pve not responding

**Action**: Waited for pve to come online (host was still booting after power restoration)

**Second Attempt**: ~2 minutes later
```
PING 192.168.4.122 (192.168.4.122): 56 data bytes
64 bytes from 192.168.4.122: icmp_seq=0 ttl=64 time=0.834 ms
```

**Result**: pve responding

---

### Step 4: Check MAAS VM Status

**Timestamp**: 09:20

```bash
ssh root@192.168.4.122 "qm status 102"
```

**Finding**: MAAS VM (102) already running - set to auto-start

```
status: running
```

**Action**: Waited for MAAS services to initialize

---

### Step 5: Verify MAAS Reachability

**Timestamp**: 09:21

```bash
ping -c 3 192.168.4.53
```

**Initial Result**: Timeout (MAAS services still starting)

**Second Attempt**: ~1 minute later

```
64 bytes from 192.168.4.53: icmp_seq=0 ttl=64 time=1.234 ms
```

**Result**: MAAS VM responding

---

### Step 6: Restore DHCP on Mac

**Timestamp**: 09:23

```bash
sudo ipconfig set en10 DHCP
ipconfig getifaddr en10
```

**Result**: `192.168.4.226` - proper DHCP lease acquired

---

### Step 7: Verify Full Connectivity

**Timestamp**: 09:24

| Host | IP | Status |
|------|-----|--------|
| still-fawn | 192.168.4.17 | UP |
| pumped-piglet | 192.168.4.175 | UP |
| chief-horse | 192.168.4.19 | UP |
| HAOS | 192.168.1.124 | UP (multi-homed) |

---

### Step 8: Check pve Uptime - Critical Discovery

**Timestamp**: 09:25

```bash
ssh root@192.168.4.122 "uptime"
```

**Result**:
```
09:25:18 up 3 min, 0 users, load average: 0.45, 0.28, 0.11
```

**Finding**: pve uptime only 3 minutes - **pve rebooted during outage**

**Root Cause**: pve was NOT plugged into UPS battery backup outlet

---

## Post-Recovery Actions

### Physical UPS Configuration

**Action**: Moved pve power cable from surge-only outlet to UPS battery-backed outlet

**Verification**: CyberPower CP1500 front panel shows pve in battery-protected outlets

### USB Cable for NUT

**Action**: Connected USB cable from UPS to pve for NUT monitoring

**Next Step**: Configure NUT for graceful shutdown (documented in runbook)

---

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Initially tried wrong interface (en4) | Used `networksetup -listallhardwareports` to find correct interface (en10) |
| pve initially unreachable | Waited for host to boot after power restoration |
| MAAS initially unreachable | VM was running, services needed time to start |

---

## Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | Success |
| **Start Time** | ~09:15 |
| **End Time** | ~09:25 |
| **Total Duration** | ~10 minutes |
| **Root Cause** | pve not on UPS battery backup |
| **Corrective Action** | Moved pve to UPS battery outlet, connected USB for NUT |

---

## Lessons Learned

1. **UPS connection matters**: Having a UPS is useless if critical hosts aren't plugged into battery outlets
2. **USB cable for NUT**: Physical UPS connection only keeps power; USB enables graceful shutdown
3. **MAAS VM auto-start works**: VM was already running after pve booted
4. **Interface discovery**: Always verify interface names with `networksetup -listallhardwareports`
5. **BIOS power restore**: Set "Restore on AC Power Loss" to "Last State" so servers auto-boot after power returns

---

## Follow-Up Actions

- [x] Move pve to UPS battery outlet
- [x] Connect USB cable from UPS to pve
- [ ] Configure NUT on pve (`apt install nut`, configure `ups.conf`)
- [ ] Test graceful shutdown with simulated outage
- [ ] Document NUT configuration in infrastructure docs
- [ ] Set BIOS "Restore on AC Power Loss" to "Last State" on pve, still-fawn, chief-horse
- [ ] Document BIOS power restore setting as standard for all homelab machines

---

## Tags

maas, power-cut, recovery, ups, nut, pve, dhcp, action-log, 2026
