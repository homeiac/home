# RCA: Voice PE Stuck Blue - Ollama/GPU Node Outage

**Date**: 2026-01-01
**Duration**: ~10 hours (01:41 UTC - 11:15 UTC)
**Impact**: Voice PE assistant non-functional, package detection automation broken
**Severity**: Medium (single service, home automation)

## Incident Summary

Voice PE device was stuck showing blue LED (listening mode) but not responding to voice commands. The root cause was a cascading failure: USB storage I/O errors suspended a ZFS pool, which blocked the GPU VM from operating normally, which took down Ollama, which broke the Home Assistant conversation agent.

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 01:41 | GPU node `k3s-vm-pumped-piglet-gpu` stops posting node status to k8s |
| 01:42 | Node marked NotReady, taints applied |
| ~01:45 | Ollama pod enters Terminating state |
| ~02:00 | New Ollama pod stuck in Pending (no schedulable GPU node) |
| 09:33 | Package detection automation triggers, Voice PE goes blue waiting for Ollama response |
| 09:37 | User notices Voice PE stuck blue |
| 10:13 | Investigation begins |
| 10:39 | Seagate USB drive unplugged |
| 10:45 | pumped-piglet power cycled |
| 11:08 | Host back online |
| 11:10 | VM 105 started (after removing 20TB disk references) |
| 11:12 | k3s node Ready, Ollama pod Running |
| 11:20 | HA Ollama integration reconfigured with direct IP |
| 11:25 | Voice PE functional |

## Contributing Factors

### Primary Cause: USB Storage I/O Failure
- **What**: 21.8TB Seagate Expansion HDD (USB) encountered I/O errors
- **Evidence**: `dmesg` showed USB disconnect, ZFS pool `local-20TB-zfs` entered SUSPENDED state
- **Why it matters**: ZFS SUSPENDED state blocks ALL I/O operations system-wide waiting for the device

### Contributing Factor 1: ZFS on USB Storage
- **What**: Critical storage pool on consumer USB external drive
- **Risk**: USB connections are unreliable, especially for large sustained I/O
- **Evidence**: Drive was being used for a large copy operation when it failed

### Contributing Factor 2: VM Disk Dependency on Suspended Pool
- **What**: VM 105 had `scsi1` (18TB data disk) on the suspended pool
- **Impact**: Even though root disk was on healthy `local-2TB-zfs`, VM operations blocked
- **Evidence**: `qm guest exec` timed out, `qm reboot` hung

### Contributing Factor 3: No Monitoring/Alerting for ZFS Pool Health
- **What**: No alerts when ZFS pool enters degraded/suspended state
- **Impact**: 10+ hour outage before manual discovery
- **Gap**: Prometheus/Grafana not monitoring ZFS pool states

### Contributing Factor 4: DNS Resolution for Ollama
- **What**: HA configured with `http://ollama.app.homelab` which doesn't resolve outside k8s
- **Impact**: Even after Ollama recovered, HA couldn't connect
- **Evidence**: `resolvectl query ollama.app.homelab` failed on chief-horse

### Contributing Factor 5: Single GPU Node
- **What**: Ollama can only run on `k3s-vm-pumped-piglet-gpu` (only node with RTX 3070)
- **Impact**: No failover when that node goes down
- **Evidence**: Ollama pod stuck Pending with no schedulable nodes

## Root Cause Analysis (5 Whys)

1. **Why was Voice PE stuck blue?**
   - Ollama conversation agent was unavailable

2. **Why was Ollama unavailable?**
   - Ollama pod was Pending/Terminating because GPU node was NotReady

3. **Why was the GPU node NotReady?**
   - VM 105 was hung due to blocked I/O operations

4. **Why were I/O operations blocked?**
   - ZFS pool `local-20TB-zfs` was SUSPENDED due to device errors

5. **Why did the ZFS pool suspend?**
   - USB Seagate drive disconnected/had I/O errors during sustained write operation

## Resolution Steps

1. Identified Ollama as unavailable via HA API
2. Found GPU node NotReady via kubectl
3. Found VM guest agent not responding
4. Discovered ZFS pool SUSPENDED via `zpool status`
5. Identified USB Seagate drive as faulted device
6. Unplugged faulty USB drive
7. Power cycled pumped-piglet (soft reboot was blocked)
8. Removed `scsi1` and `virtiofs0` references from VM 105 config
9. Started VM 105
10. Verified k3s node Ready and Ollama pod Running
11. Reconfigured HA Ollama integration with direct IP

## Action Items

| Priority | Action | Owner | Status |
|----------|--------|-------|--------|
| P1 | Add ZFS pool health monitoring to Prometheus | - | TODO |
| P1 | Create runbook for Voice PE / Ollama diagnosis | - | DONE (this doc) |
| P2 | Investigate Seagate USB drive health | - | TODO |
| P2 | Consider migrating critical data off USB storage | - | TODO |
| P2 | Add DNS entry for ollama.app.homelab in OPNsense | - | TODO |
| P3 | Evaluate GPU redundancy options | - | TODO |
| P3 | Add HA integration health monitoring | - | TODO |

## Lessons Learned

1. **USB storage is not reliable for ZFS pools** - Consider migrating to internal drives or NAS
2. **ZFS SUSPENDED state is catastrophic** - Blocks entire system, requires physical intervention
3. **Monitoring gaps are silent killers** - 10 hours of outage with no alert
4. **DNS complexity bites** - Internal k8s DNS doesn't propagate to external services
5. **Single points of failure** - One GPU node = one Ollama = broken voice assistant

**Tags**: voice-pe, ollama, zfs, usb-storage, seagate, pumped-piglet, k3s, gpu, home-assistant, dns, rca, outage, proxmox

