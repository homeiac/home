# Runbook: Performance Incident Investigation Methodology

## Overview

This runbook documents systematic approaches for investigating performance incidents in complex infrastructure, based on real-world detective work during a CPU/memory spike investigation on 2025-08-17. It includes both successful techniques and common pitfalls to avoid.

## When to Use This Runbook

### Symptoms Requiring Investigation
- Unexpected CPU or memory spikes
- Performance degradation without obvious cause  
- Resource usage patterns that don't match known workloads
- Intermittent system slowdowns
- Monitoring alerts without clear attribution

### Investigation Scope
- Multi-layer infrastructure (hypervisor, VMs, containers, applications)
- Distributed systems with multiple potential causes
- Time-bound incidents requiring forensic analysis
- Performance issues affecting multiple systems simultaneously

## Investigation Methodology

### Phase 1: Evidence Collection (Don't Jump to Conclusions!)

#### ⚠️ **CRITICAL WARNING: Avoid Premature Attribution**
**Common Pitfall**: Seeing circumstantial evidence and immediately forming a hypothesis.

**Example from 2025-08-17 Incident:**
- ❌ **Wrong thinking**: "I see Prometheus node-exporter running every 15 minutes, and there are spikes around those times"
- ❌ **Hasty conclusion**: "Prometheus must be the culprit"
- ✅ **Correct approach**: "This could be correlation, not causation. Let me gather more evidence."

#### 1.1 Timeline Reconstruction
```bash
# Collect logs from ALL layers for the incident window
# Example: 17:07-17:37 incident window

# Host level
ssh root@host "journalctl --since '2025-08-17 17:05' --until '2025-08-17 17:40'"

# VM/Container level  
ssh user@vm "journalctl --since '2025-08-17 17:05' --until '2025-08-17 17:40'"

# Application level
kubectl logs --since-time="2025-08-17T17:05:00Z" --until-time="2025-08-17T17:40:00Z"
```

#### 1.2 Resource Pattern Analysis
```bash
# Look for continuous vs periodic patterns
# Key insight: 30-minute continuous load ≠ 15-minute periodic job

# Check for all periodic jobs
crontab -l
ls /etc/cron.d/
systemctl list-timers

# Correlate timing with actual resource usage
```

#### 1.3 Multi-Layer Evidence Gathering
```bash
# Don't rely on single source of truth
# Hypervisor level
qm config <vmid>
qm guest exec <vmid> -- free -h

# Container orchestrator level
kubectl top nodes
kubectl top pods --all-namespaces

# Application level
# Check application-specific metrics and logs
```

### Phase 2: Pattern Recognition and Hypothesis Testing

#### 2.1 Challenge Your Initial Hypothesis

**Real Example from Investigation:**
```
Initial Hypothesis: "Prometheus node-exporter causing spikes"
Evidence FOR: Runs every 15 minutes, timestamps correlate
Evidence AGAINST: Spikes are continuous 30-minute periods, not brief 15-minute events

🎯 Key Insight: Continuous patterns suggest maintenance operations, not periodic collections
```

#### 2.2 Look for Sustained Operations
```bash
# Search for long-running operations during incident
grep -E "(compact|snapshot|backup|maintenance)" /var/log/application.log

# etcd specific patterns (common culprits)
journalctl -u k3s | grep -E "(compact|snapshot|apply request took too long)"

# Database maintenance patterns
grep -E "(VACUUM|OPTIMIZE|REINDEX)" /var/log/database.log
```

#### 2.3 Resource Constraint Analysis
```bash
# Check for hidden resource limits
# Memory balloon (common Proxmox gotcha)
qm config <vmid> | grep balloon

# Compare configured vs actual resources
# Configured: memory: 4000
# Actual: MemTotal: 1863668 kB (~1.8GB)
```

### Phase 3: Deep Dive Analysis

#### 3.1 Application-Specific Investigation

**For Kubernetes/etcd Issues:**
```bash
# Look for etcd operational patterns
kubectl logs -n kube-system <k3s-pod> | grep -E "(snapshot|compact|slow)"

# Check etcd database size and operations
du -sh /var/lib/rancher/k3s/server/db/etcd/

# Analyze etcd trace logs
journalctl -u k3s | grep -E "(trace.*transaction|apply request took too long)"
```

**For Database Systems:**
```bash
# Check for maintenance operations
grep -E "(maintenance|analyze|vacuum|checkpoint)" /var/log/database.log

# Look for slow query patterns
grep -E "(slow query|duration.*ms)" /var/log/database.log
```

#### 3.2 I/O and Storage Investigation
```bash
# Check for storage-intensive operations
iostat -x 1 5
iotop -a

# Look for disk space issues
df -h
du -sh /var/log/* | sort -hr

# Check for swap usage (even if disabled)
swapon -s
grep -i swap /proc/meminfo
```

### Phase 4: Smoking Gun Identification

#### 4.1 Timeline Correlation
**Real Example - The Breakthrough Moment:**
```bash
# Found the smoking gun in k3s logs
Aug 17 17:16:28 k3s-vm-pve k3s[3084120]: {"msg":"triggering snapshot","local-member-applied-index":58260753}
Aug 17 17:16:28 k3s-vm-pve k3s[3084120]: {"msg":"saved snapshot","snapshot-index":58260753}
Aug 17 17:18:46 k3s-vm-pve k3s[3084120]: {"took":"1.078107672s","expected-duration":"100ms"}
```

#### 4.2 Causation vs Correlation Test
```bash
# Test the hypothesis
# If etcd snapshots cause the issue, we should see:
# 1. Snapshot events during incident window ✅
# 2. Long-duration operations following snapshots ✅  
# 3. Memory/CPU spikes correlating with these operations ✅
# 4. Pattern independent of other periodic jobs (Prometheus) ✅
```

## Common Investigation Pitfalls

### 1. The "Obvious Suspect" Trap
**Scenario**: First thing you notice gets blamed
```
❌ "I see Prometheus running, it must be the cause"
✅ "Prometheus is one of many things running, let me gather comprehensive evidence"
```

### 2. Insufficient Time Window Analysis
**Scenario**: Looking at too narrow a time window
```
❌ Looking only at exact spike times
✅ Examining 30-60 minutes before and after incident
```

### 3. Single-Layer Investigation
**Scenario**: Only checking one layer of the stack
```
❌ Only checking application logs
✅ Checking host → VM → container → application layers
```

### 4. Confirmation Bias
**Scenario**: Seeing evidence that confirms your initial theory, ignoring contradictory evidence
```
❌ "Prometheus runs at 17:18 and 17:33, that explains it" (ignoring continuous 17:07-17:37 pattern)
✅ "The pattern doesn't match the hypothesis, let me reconsider"
```

### 5. Configuration vs Reality Mismatch
**Scenario**: Trusting configuration files over actual system state
```
❌ "Config shows 4GB RAM, so that's what the system has"
✅ "Config shows 4GB but system reports 1.8GB - there's a discrepancy to investigate"
```

## Investigation Tools and Commands

### Timeline Reconstruction
```bash
# Multi-system log correlation
journalctl --since "YYYY-MM-DD HH:MM" --until "YYYY-MM-DD HH:MM" | grep -v routine_noise

# Combine logs from multiple systems
ssh host1 "journalctl --since '$TIME'" > host1.log &
ssh host2 "journalctl --since '$TIME'" > host2.log &
wait
```

### Resource Analysis
```bash
# Real vs configured resources
free -h                    # Available memory
cat /proc/meminfo         # Detailed memory info
nproc                     # Available CPUs
lscpu                     # CPU details

# Hidden limits
systemd-run --scope -p MemoryLimit=1G command  # Example constraint
```

### Process Analysis
```bash
# Resource-intensive processes during timeframe
ps -eo pid,ppid,cmd,%mem,%cpu,etime --sort=-%cpu | head -20

# Historical process data (if available)
sar -u -s HH:MM:SS -e HH:MM:SS  # CPU usage history
sar -r -s HH:MM:SS -e HH:MM:SS  # Memory usage history
```

### Storage and I/O
```bash
# I/O patterns
iostat -x 1 10              # Real-time I/O stats  
iotop -a                    # I/O by process
lsof +L1                    # Deleted files still consuming space

# Disk usage analysis
du -sh /* | sort -hr         # Directory sizes
find /var/log -size +100M    # Large log files
```

## Real-World Success Story: etcd Detective Work

### The Case: 30-Minute CPU/Memory Spike

**Initial Misleading Evidence:**
- Prometheus node-exporter runs every 15 minutes ✓
- Spikes occur around 17:18 and 17:33 ✓
- Node-exporter consumes 1.3s CPU time ✓

**Why This Was Wrong:**
- Incident was continuous 17:07-17:37, not brief 15-minute events
- 1.3s CPU usage cannot explain 30-minute sustained load
- Pattern was independent of Prometheus timing

**The Breakthrough:**
```bash
# Deep dive into application logs revealed:
Aug 17 17:16:28: etcd snapshot triggered
Aug 17 17:18:46: etcd operations taking >1 second (vs 100ms expected)
Aug 17 17:09:37, 17:14:37, 17:19:37: etcd compactions every ~5 minutes
```

**Root Cause Validation:**
- etcd snapshot at 17:16:28 during incident window ✅
- Multiple slow etcd operations throughout period ✅  
- Memory pressure from 1.8GB usable (not 4GB configured) ✅
- Pattern matches etcd maintenance, not monitoring collection ✅

## Prevention and Monitoring

### Early Warning Systems
```bash
# Monitor for long-duration operations
# etcd examples
journalctl -u k3s -f | grep "took.*[5-9][0-9][0-9]ms\|took.*[0-9]s"

# Database examples  
tail -f /var/log/database.log | grep "duration.*[5-9][0-9][0-9][0-9]ms"

# Generic slow operation detection
tail -f /var/log/application.log | grep -E "(slow|timeout|took.*[0-9]+s)"
```

### Resource Monitoring
```bash
# Configuration drift detection
# Compare configured vs actual resources weekly
diff <(qm config <vmid>) <(previous_config)

# Memory pressure alerts
free | awk '/Mem:/ {if ($3/$2 > 0.8) print "High memory usage: " $3/$2*100 "%"}'
```

## Lessons Learned Template

After each investigation, document:

### What Worked
- Investigation techniques that revealed the truth
- Tools and commands that provided key insights  
- Patterns that led to breakthrough moments

### What Didn't Work  
- Initial hypotheses that were wrong and why
- Tools that provided misleading information
- Time wasted on incorrect leads

### Systemic Issues Found
- Configuration vs reality mismatches
- Missing monitoring for the actual root cause
- Process improvements needed

### Prevention Measures
- Monitoring additions to catch this class of issue earlier
- Configuration changes to prevent recurrence
- Documentation updates for operational teams

## Related Documentation

- [RCA: High CPU/Memory Usage - August 17, 2025](../../rca/rca-2025-08-17-high-cpu-memory.md)
- [etcd Performance Tuning Guide](../guides/etcd-optimization.md) (TODO)
- [Multi-Layer Monitoring Strategy](../monitoring/multi-layer-monitoring.md) (TODO)

## Conclusion

Effective performance investigation requires:
1. **Methodical evidence gathering** before forming hypotheses
2. **Challenging initial assumptions** when patterns don't align  
3. **Multi-layer analysis** across the entire stack
4. **Distinguishing correlation from causation**
5. **Validating hypotheses** with multiple data points

Remember: The most obvious suspect is often innocent. Let the evidence lead the investigation, not your initial assumptions.

---

**Prepared by**: Claude Code AI Assistant  
**Based on**: Real incident investigation 2025-08-17  
**Last Updated**: 2025-08-18  
**Next Review**: 2025-09-18