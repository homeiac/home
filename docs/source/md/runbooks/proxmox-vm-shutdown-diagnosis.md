# Proxmox VM Sudden Shutdown Diagnosis Runbook

**Purpose**: Systematic approach to diagnosing unexpected Proxmox VM shutdowns and crashes  
**Target Audience**: SRE, Platform Engineers, Operations Team  
**Severity**: P1/P2 (Critical infrastructure services)  
**Last Updated**: July 30, 2025

## Overview

Unexpected VM shutdowns in Proxmox can have multiple root causes ranging from host-level resource exhaustion to guest OS issues. This runbook provides a structured diagnostic approach based on SRE best practices and incident response procedures.

## Prerequisites

- SSH access to Proxmox host(s) with root or sudo privileges
- SSH access to affected VMs (if accessible)
- Knowledge of VM IDs and host assignments
- Basic understanding of Linux system administration

## Diagnostic Framework

### Phase 1: Initial Triage (5 minutes)

#### 1.1 Establish Current VM State
```bash
# Check VM status across all hosts
ssh root@pve.maas "qm list"
ssh root@still-fawn.maas "qm list"

# Look for:
# - VMs showing "running" with recent PIDs
# - VMs in "stopped" state unexpectedly
# - Memory/CPU usage anomalies
```

#### 1.2 Quick Connectivity Test
```bash
# Test basic connectivity
ping -c 3 <vm-ip>

# Test SSH access (will fail if VM restarted recently)
ssh <user>@<vm-ip> "uptime"
```

**Decision Point**: If VM is accessible and shows long uptime → Service-level issue, not VM shutdown. Skip to Phase 4.

### Phase 2: Evidence Collection (10 minutes)

#### 2.1 Check VM Boot History
```bash
# On the VM (if accessible)
ssh <user>@<vm-ip> "sudo last -x | head -20"

# Look for:
# - Recent reboot entries
# - Gaps in activity timeline
# - Shutdown vs reboot patterns
```

#### 2.2 Detect Unclean Shutdowns
```bash
# Check for journal corruption (smoking gun for unclean shutdown)
ssh <user>@<vm-ip> "sudo journalctl --list-boots"
ssh <user>@<vm-ip> "sudo dmesg | grep -i 'corrupted\|unclean'"

# Look for:
# - "File corrupted or uncleanly shut down"
# - Journal recovery messages
# - Missing boot entries
```

#### 2.3 Proxmox Host Investigation
```bash
# Check VM start/stop events
ssh root@<proxmox-host> "journalctl -u qemu-server@<vmid> --since '1 hour ago'"

# Look for:
# - qmstart entries (VM was restarted)
# - Unexpected scope failures
# - Guest agent timeouts
```

### Phase 3: Root Cause Analysis (15 minutes)

#### 3.1 Memory Pressure Investigation (Most Common)
```bash
# Check for OOM killer events (CRITICAL CHECK)
ssh root@<proxmox-host> "journalctl --since '2 hours ago' | grep -E '(oom-killer|Out of memory|killed process)'"

# Detailed OOM analysis
ssh root@<proxmox-host> "journalctl --since '2 hours ago' | grep -A 10 -B 5 'oom-killer'"

# Check current memory state
ssh root@<proxmox-host> "free -h && cat /proc/meminfo | grep -E '(MemTotal|MemAvailable|MemFree)'"

# VM memory allocations
ssh root@<proxmox-host> "qm list | awk '{sum += \$4} END {print \"Total VM Memory: \" sum \" MB\"}'"
```

**OOM Kill Pattern Recognition**:
```
kernel: <process> invoked oom-killer: gfp_mask=0x...
kernel: Out of memory: Killed process <pid> (<name>) total-vm:<size>kB
systemd[1]: <vmid>.scope: A process of this unit has been killed by the OOM killer
```

#### 3.2 Storage Issues Investigation
```bash
# Check for disk errors
ssh root@<proxmox-host> "dmesg | grep -E '(I/O error|read error|write error|disk|sda|nvme)' | tail -20"

# Storage space check
ssh root@<proxmox-host> "df -h"
ssh root@<proxmox-host> "zpool status" # If using ZFS

# Look for:
# - Disk I/O errors
# - Full filesystems (>95%)
# - ZFS pool degradation
```

#### 3.3 Hardware Issues Investigation
```bash
# System temperature and hardware health
ssh root@<proxmox-host> "sensors" # If available
ssh root@<proxmox-host> "journalctl --since '2 hours ago' | grep -E '(temperature|thermal|hardware|mce)'"

# Power/thermal events
ssh root@<proxmox-host> "grep -E '(thermal|power|acpi)' /var/log/kern.log"
```

#### 3.4 Application-Level Investigation
If VM is accessible, check what the guest was doing:

```bash
# Check for application memory consumption before crash
ssh <user>@<vm-ip> "sudo journalctl --boot=-1 --since '30 minutes before crash' | grep -E '(download|sync|import|backup|update)'"

# Process memory usage patterns
ssh <user>@<vm-ip> "sudo journalctl --boot=-1 | grep -E '(memory|oom|killed)'"

# Look for:
# - Large downloads/imports
# - Database operations
# - Backup activities
# - System updates
```

### Phase 4: Correlation Analysis

#### 4.1 Timeline Reconstruction
Create a timeline of events:

1. **What was running**: Application activities from guest logs
2. **When pressure started**: Memory/disk pressure indicators
3. **Trigger event**: OOM kill, hardware failure, or other
4. **Recovery time**: How long until service restored

#### 4.2 Resource Correlation
```bash
# Check if multiple VMs affected (indicates host issue)
ssh root@<proxmox-host> "journalctl --since '2 hours ago' | grep -E 'oom-kill|Failed.*scope'"

# Network correlation (if applicable)
ping -c 5 <gateway-ip>
```

## Common Root Causes and Solutions

### 1. Memory Overcommitment (Most Common)
**Symptoms**: OOM killer messages, memory pressure
**Diagnosis**: Total VM allocations ≥ Host memory
**Solution**: 
- Immediate: Reduce VM memory allocations
- Long-term: Add more host RAM or redistribute VMs

### 2. Resource-Intensive Operations
**Symptoms**: OOM during specific application activities
**Diagnosis**: Memory spikes during downloads, backups, etc.
**Solution**: 
- Schedule intensive operations during off-peak hours
- Add resource limits to applications
- Increase VM memory temporarily during operations

### 3. Storage Exhaustion
**Symptoms**: Disk full errors, I/O failures
**Diagnosis**: >95% disk usage, I/O errors in logs
**Solution**: 
- Clean up disk space
- Expand storage
- Move data to alternative storage

### 4. Hardware Issues
**Symptoms**: Thermal shutdowns, MCE errors
**Diagnosis**: Temperature alerts, hardware error logs
**Solution**: 
- Check cooling systems
- Review hardware health monitoring
- Consider hardware replacement

## Prevention and Monitoring

### Immediate Actions
1. **Memory Monitoring**: Set up alerts at 85% host memory usage
2. **Resource Documentation**: Document VM memory allocations vs host capacity
3. **Application Scheduling**: Move resource-intensive operations off-peak

### Long-term Improvements
1. **Capacity Planning**: Maintain 20-30% memory headroom
2. **Resource Ballooning**: Implement dynamic memory allocation
3. **Redundancy**: Deploy critical services across multiple hosts
4. **Monitoring**: Implement comprehensive infrastructure monitoring

## Escalation Criteria

**Escalate Immediately If**:
- Multiple VMs affected simultaneously
- Hardware error messages detected
- Storage corruption indicated
- Unable to restart affected VMs

**Escalation Contacts**:
- Platform Team: Critical infrastructure issues
- Hardware Team: Physical hardware problems
- Application Teams: Service-specific investigations

## Troubleshooting Commands Reference

### Quick Status Checks
```bash
# Host memory status
free -h && cat /proc/meminfo | head -5

# VM process status
ps aux | grep qemu | grep <vmid>

# Recent system events
journalctl --since '1 hour ago' --priority=err

# VM configuration
qm config <vmid>
```

### Log Analysis
```bash
# OOM events
journalctl --since 'yesterday' | grep -E '(oom|killed|memory)'

# VM specific logs
journalctl -u qemu-server@<vmid> --since '1 hour ago'

# System resource logs
sar -r 1 10  # Memory usage over time (if available)
```

### Recovery Commands
```bash
# Start stopped VM
qm start <vmid>

# Reset VM (if hung)
qm reset <vmid>

# Check VM status
qm status <vmid>
```

## Post-Incident Actions

1. **Document Findings**: Update incident tracking with root cause
2. **Implement Fixes**: Apply immediate and long-term solutions
3. **Monitor Effectiveness**: Track resolution success
4. **Update Runbooks**: Incorporate lessons learned
5. **Review Architecture**: Assess if infrastructure changes needed

---
**Runbook Version**: 1.0  
**Next Review**: 2025-10-30  
**Feedback**: Submit improvements via documentation repository