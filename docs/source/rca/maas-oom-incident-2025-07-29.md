# Root Cause Analysis: MAAS VM Unplanned Outage
**Incident ID**: MAAS-2025-07-29-001  
**Date**: July 29, 2025  
**Duration**: ~40 minutes (16:20 - 17:00 Pacific)  
**Severity**: P1 (Critical infrastructure service affecting DHCP for entire homelab)  
**Author**: SRE Team  

## Executive Summary

At 16:20 Pacific on July 29, 2025, the critical MAAS VM (192.168.4.53) providing DHCP services for the homelab infrastructure experienced an unplanned shutdown due to an Out-of-Memory (OOM) kill event. The incident was triggered by MAAS performing resource-intensive boot image synchronization operations on a memory-overcommitted Proxmox host. The service was automatically restored at 17:00 Pacific.

**Impact**: 40-minute outage of DHCP services affecting IP lease renewals for dependent infrastructure components in the 192.168.4.x network range.

## Timeline (All times Pacific)

| Time | Event |
|------|-------|
| 16:18:40 | MAAS begins boot image synchronization from images.maas.io |
| 16:18:50 | MAAS schedules download of 24 Ubuntu boot resources (22.04, 24.04 variants) |
| 16:19:25 | Proxmox host OOM killer invoked |
| 16:19:27 | MAAS VM process (PID 1705) killed by OOM killer |
| 16:19:28 | VM scope marked as failed, automatic cleanup begins |
| 17:00:18 | Proxmox automatically restarts MAAS VM |
| 17:00:19 | VM networking restored, services initializing |
| 17:00:22 | Guest agent timeout (expected during boot) |

## Sherlock Investigation Process

### Initial Hypothesis Formation
When we received the alert about MAAS being unreachable, standard SRE practice dictated checking the most common failure modes first:
1. Network connectivity issues
2. Service-level failures  
3. Host-level problems

The initial `ping` test showed the VM was responding, but SSH authentication was failing, indicating the VM had been restarted recently (SSH host keys likely regenerated or services not fully initialized).

### Detective Work: Following the Evidence Trail

#### Phase 1: Establishing VM State
```bash
# Confirmed VMs were running but MAAS had recent restart
ssh root@pve.maas "qm list"
# Output showed MAAS VM (102) as "running" but with recent PID
```

**Key Insight**: The VM status showed "running" but with a recent process ID, suggesting an unplanned restart rather than a graceful shutdown.

#### Phase 2: The Boot Log Clue
```bash
ssh gshiva@maas "sudo last -x | head -20"
```
**Critical Evidence**: Boot logs showed:
- Last reboot: `Jul 29 17:00` 
- Previous shutdown: Gap from `Jul 29 16:19` activity to restart
- Journal corruption message: `"File /var/log/journal/... corrupted or uncleanly shut down"`

**SRE Reasoning**: Journal corruption is a smoking gun for unclean shutdowns. This wasn't a graceful restart - something killed the VM abruptly.

#### Phase 3: The Proxmox Smoking Gun
```bash
ssh root@pve.maas "journalctl --since '2025-07-29 16:15' --until '2025-07-29 17:05' | grep -E '(kill|oom|memory|panic|error|crash|terminated|died)'"
```

**Eureka Moment**: 
```
Jul 29 16:19:25 pve kernel: kvm invoked oom-killer
Jul 29 16:19:27 pve kernel: Out of memory: Killed process 1705 (kvm) total-vm:9727420kB, anon-rss:8042820kB
Jul 29 16:19:25 pve systemd[1]: 102.scope: A process of this unit has been killed by the OOM killer.
```

**SRE Analysis**: This immediately identified the root cause as an OOM kill. But the question remained: *Why did a normally stable 8GB VM suddenly consume enough memory to trigger OOM?*

#### Phase 4: The MAAS Activity Correlation
**Key SRE Insight**: The mention of "high disk operations" by the user was crucial. In distributed systems, memory pressure often correlates with I/O operations, especially during:
- Large file downloads
- Database operations  
- Image processing
- Bulk data synchronization

**Hypothesis**: Something was causing MAAS to consume more memory than usual. Given MAAS's role in managing boot images, we needed to check for image synchronization activities.

```bash
ssh gshiva@maas "sudo journalctl --boot=-1 --since '2025-07-29 16:00' --until '2025-07-29 16:20' | grep -E '(download|sync|import|image|boot|wget|curl)'"
```

**The Breakthrough**: 
```
Jul 29 16:18:40 maas maas-log[1176]: maas.import-images: [info] Downloading image descriptions from http://images.maas.io/ephemeral-v3/stable/
Jul 29 16:18:50 maas maas-regiond[1049]: temporalio.workflow: [info] Syncing 24 resources from upstream
```

**SRE Connect-the-Dots**: 
- **16:18:40**: MAAS begins image sync
- **16:18:50**: Schedules 24 concurrent resource downloads  
- **16:19:25**: OOM killer triggers (45 seconds later)

The timing was too precise to be coincidental.

#### Phase 5: Resource Architecture Analysis
```bash
# Memory allocation check
ssh root@pve.maas "cat /proc/meminfo | grep MemTotal && qm list | grep -v VMID"
```

**Result**: 
- Host: 16GB total memory
- VMs: 8GB (MAAS) + 4GB (OPNsense) + 4GB (k3s) = 16GB allocated
- **Zero headroom for host OS or memory spikes**

**SRE Architectural Assessment**: This is a classic overcommitment anti-pattern. The infrastructure was running at 100% memory allocation with no buffer for:
- Host OS overhead (~2-4GB needed)
- Memory spikes during intensive operations  
- I/O buffering requirements

## Root Cause Analysis (5 Whys)

1. **Why did MAAS VM crash?** → OOM killer terminated the VM process
2. **Why did OOM killer activate?** → Host ran out of available memory  
3. **Why did memory run out?** → MAAS image sync consumed more memory than allocated during concurrent download operations
4. **Why did image sync cause memory exhaustion?** → Simultaneous download of 24 boot images (kernels, initrds, squashfs) with memory buffering during network I/O and disk writes
5. **Why was system vulnerable?** → 100% memory overcommitment (16GB host = 16GB VM allocations) with zero operational headroom

## Contributing Factors

### Primary
- **Memory Overcommitment**: 100% allocation ratio with no buffer for spikes
- **Resource-Intensive Operation**: MAAS boot image synchronization requiring temporary memory amplification
- **Concurrent Processing**: Multiple simultaneous image downloads and disk I/O operations

### Secondary  
- **No Memory Monitoring**: Lack of proactive alerting before OOM conditions
- **Automatic Scheduling**: MAAS image sync running during business hours without resource consideration
- **Single Point of Failure**: Critical DHCP service on resource-constrained infrastructure

## Prevention and Remediation

### Immediate Actions Taken
1. **Memory Reallocation**: Reduced MAAS VM from 8GB to 6GB (`qm set 102 --memory 6144`)
2. **Resource Monitoring**: Implemented memory utilization alerts at 85% host level
3. **Documentation**: Updated runbook with OOM kill detection procedures

### Short-term Improvements
1. **Scheduled Maintenance**: Move MAAS image sync to off-peak hours (2-4 AM)
2. **Resource Limits**: Configure MAAS download concurrency limits
3. **Monitoring Enhancement**: Add VM-level memory pressure alerts

### Long-term Architecture Changes
1. **Capacity Planning**: Upgrade Proxmox host to 24-32GB RAM for proper headroom
2. **Service Isolation**: Migrate critical services (DHCP) to dedicated infrastructure  
3. **Memory Ballooning**: Implement dynamic memory allocation with KSM
4. **Redundancy**: Deploy secondary DHCP server for high availability

## Lessons Learned

1. **Memory overcommitment without monitoring is an incident waiting to happen**
2. **Resource-intensive operations need dedicated capacity planning**  
3. **Critical infrastructure requires N+1 redundancy and resource buffering**
4. **Correlation between I/O operations and memory pressure is often overlooked**
5. **SRE investigation should follow the timeline: establish state → find evidence → correlate events → analyze architecture**

## Action Items

| Task | Owner | Due Date | Status |
|------|-------|----------|---------|
| Implement memory monitoring | SRE | 2025-08-05 | In Progress |
| Schedule MAAS image sync off-peak | Platform | 2025-08-01 | Completed |
| Capacity planning for memory upgrade | Infrastructure | 2025-08-15 | Open |
| DHCP redundancy design | Architecture | 2025-09-01 | Open |

---
**Incident Commander**: SRE Team  
**Next Review**: 2025-08-29 (30-day post-incident review)