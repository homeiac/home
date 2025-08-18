# Root Cause Analysis: High CPU/Memory Usage - August 17, 2025

## Incident Summary

**Date**: 2025-08-17  
**Time Window**: 17:07 - 17:37 PDT  
**Duration**: 30 minutes  
**Severity**: Medium  
**Status**: Resolved  

### Impact
- k3s-vm-pve VM: High memory usage (~80% of 1.8GB available RAM, swap disabled)
- pve Proxmox host: High CPU and memory usage during the same period
- etcd operations experiencing 200ms+ latencies during peak activity
- No service disruption, but potential performance degradation

## Timeline

| Time | Event |
|------|-------|
| 17:07 | Incident begins - CPU/memory spike observed |
| 17:09:37 | etcd compaction (249ms duration) |
| 17:14:37 | etcd compaction (248ms duration) |
| 17:16:28 | **etcd snapshot triggered** (critical event) |
| 17:18:46 | etcd read operations >1 second (1.078s) |
| 17:19:37 | etcd compaction (258ms duration) |
| 17:37 | Incident ends - metrics return to normal |

**Note**: Prometheus node-exporter ran at 17:18 and 17:33 but was not the primary cause.

## Root Cause Analysis

### **CORRECTED**: Primary Root Cause

**etcd Database Maintenance Operations** (Not Prometheus as initially suspected)

1. **etcd Snapshot Event (Critical Trigger)**
   - At 17:16:28: etcd triggered automatic snapshot after reaching 10,000 revision threshold
   - Snapshot operation is I/O and memory intensive
   - Creates point-in-time backup of entire cluster state

2. **etcd Compaction Storm**
   - Multiple compactions every ~5 minutes during incident window
   - 17:09:37 (249ms), 17:14:37 (248ms), 17:19:37 (258ms)
   - CPU-intensive operations to remove old revisions

3. **Memory Pressure Cascade**
   - VM misconfigured: only 1.8GB usable RAM (balloon issue) vs 4GB allocated
   - k3s-server consuming 749MB (40% of available memory)
   - etcd operations + existing memory pressure caused performance degradation
   - No swap configured to handle temporary spikes

### Secondary Contributing Factors

4. **Orphaned Longhorn Resources (Minor Factor)**
   - 3 stuck Longhorn persistent volumes from 9 days prior
   - Continuous "VerifyVolumesAreAttached" errors every minute
   - Added to overall system load but not the primary cause

5. **Prometheus Node Exporter (Ruled Out)**
   - ❌ Initial hypothesis: APT collection every 15 minutes
   - ✅ Evidence: Heavy activity was continuous 17:07-17:37, not just at 15-minute intervals
   - ✅ Prometheus operations were brief (1-2 seconds), not 30-minute sustained load

### Technical Details

**etcd Operations During Incident:**
```
Aug 17 17:16:28 k3s-vm-pve k3s[3084120]: {"msg":"triggering snapshot","local-member-applied-index":58260753}
Aug 17 17:16:28 k3s-vm-pve k3s[3084120]: {"msg":"saved snapshot","snapshot-index":58260753}
Aug 17 17:18:46 k3s-vm-pve k3s[3084120]: {"msg":"apply request took too long","took":"1.078107672s"}
```

**Memory Configuration Issue:**
```bash
# VM Config shows 4GB but balloon limits to 2GB
balloon: 2000  
memory: 4000

# VM sees only 1.8GB usable
MemTotal: 1863668 kB (~1.8GB)
k3s-server: 749MB (40% of available)
```

**Stuck Longhorn Resources (Secondary):**
```
pvc-a5c2b843-2c17-4081-94b0-302a94451c9e (netdata-k8s-state-varlib)
pvc-cc498c64-a1dd-475d-b990-7935e9f23b3e (netdata-parent-database) 
pvc-eb7a4cde-95cf-484d-b74d-6a2da38588ee (netdata-parent-alarms)
```

## Resolution

### Immediate Actions Taken

1. **Cleaned up orphaned Longhorn resources:**
   ```bash
   # Force deleted volume attachments
   kubectl delete volumeattachment <ids> --force --grace-period=0
   
   # Removed stuck persistent volumes
   kubectl delete pv <pv-names>
   
   # Patched finalizers when resources got stuck
   kubectl patch volumeattachment <id> -p '{"metadata":{"finalizers":null}}'
   kubectl patch pv <pv-name> -p '{"metadata":{"finalizers":null}}'
   ```

2. **Verified Netdata using correct storage:**
   - Confirmed all Netdata PVCs using `local-path` storage class
   - No dependencies on Longhorn remaining

### Root Cause Resolution Status
- ✅ Orphaned Longhorn resources removed (secondary issue)
- ✅ **Smart ballooning configured**: VM memory balloon now properly configured with shares parameter
- ❌ **etcd tuning needed**: Snapshot frequency and compaction intervals not optimized for quorum-only node
- ⚠️  k3s VM architecture requires optimization for etcd workload patterns

### Smart Ballooning Configuration Applied
**Problem**: VM was missing `shares` parameter, disabling auto-ballooning entirely
- **Before**: `balloon: 2000, memory: 4000` (no shares = auto-ballooning disabled)
- **After**: `balloon: 2000, memory: 4000, shares: 1000` (auto-ballooning enabled)

**Expected behavior**: 
- Normal operation: VM uses ~2GB (balloon inflated)
- High memory pressure (etcd operations): pvestatd deflates balloon → VM gets up to 4GB
- Pressure reduces: pvestatd inflates balloon → VM returns to ~2GB

## Prevention Measures

### Short-term (Completed)
1. ✅ Removed orphaned Longhorn persistent volumes and volume attachments
2. ✅ Verified clean storage migration completion
3. ✅ Configured smart ballooning with shares parameter for auto-ballooning

### Long-term Recommendations
1. **Monitor smart ballooning effectiveness** (Medium Priority)
   - Track pvestatd auto-ballooning during future etcd operations
   - Verify VM memory expands from 2GB to 4GB during high load
   - Add 2GB swap for additional burst capacity if needed

2. **Optimize etcd for quorum-only role**
   - Reduce snapshot frequency: `--etcd-snapshot-schedule-cron='0 2 * * *'` (daily)
   - Reduce retention: `--etcd-snapshot-retention=3`
   - Tune compaction intervals for lighter workload

3. **Node workload isolation**
   - Apply NoSchedule taint to prevent heavy workloads
   - Limit container memory usage on this node

4. **Implement proper storage migration procedures**
   - Checklist for verifying complete resource cleanup
   - Automated detection of orphaned storage resources

## Lessons Learned

1. **Investigation Methodology**: 
   - ❌ **Don't jump to conclusions**: Initial Prometheus theory was wrong despite circumstantial evidence
   - ✅ **Challenge assumptions**: User's skepticism about Prometheus led to correct diagnosis
   - ✅ **Examine continuous vs periodic patterns**: 30-min continuous load ≠ 15-min periodic job
   - ✅ **Deep log analysis**: etcd trace logs revealed the real smoking gun

2. **Proxmox Memory Ballooning Lessons**:
   - Always verify actual vs configured resources (1.8GB vs 4GB scenario)
   - **Critical**: `shares` parameter required for auto-ballooning (zero disables it)
   - Proxmox GUI shows shares field but provides no explanation of what it does
   - Default shares=1000, but missing shares prevents dynamic memory allocation
   - etcd maintenance operations require burst capacity planning

3. **etcd Operational Awareness**:
   - etcd snapshots and compactions are major resource events
   - Default etcd settings may not suit specialized node roles
   - Memory pressure during etcd operations can cascade to performance issues

4. **Storage Migration Completeness**: Storage class migrations require thorough cleanup verification beyond just pod restart

## Related Documentation

- [Kubernetes Persistent Volume Cleanup Runbook](../md/runbooks/runbook-stuck-persistent-volumes.md)
- [Storage Class Migration Guide](../guides/storage-migration.md) (TODO)
- [k3s Resource Sizing Guidelines](../reference/k3s-sizing.md) (TODO)

## Action Items

### Immediate (Completed)
- [x] Fix VM memory balloon configuration with shares parameter
- [ ] Add 2GB swap to k3s-vm-pve (optional)
- [x] Verify smart ballooning is enabled

### etcd Optimization  
- [ ] Configure daily etcd snapshots vs transaction-based
- [ ] Reduce snapshot retention to 3
- [ ] Tune etcd compaction intervals
- [ ] Add etcd operation duration monitoring

### Infrastructure (Completed)
- [x] Create detective methodology runbook
- [x] Implement monitoring for stuck Kubernetes resources
- [ ] Document k3s resource sizing guidelines for different roles
- [ ] Add pvestatd ballooning monitoring alerts

---

**Prepared by**: Claude Code AI Assistant  
**Review Status**: Complete Analysis (etcd root cause + shares fix applied)  
**Initial Analysis Date**: 2025-08-18  
**Final Update Date**: 2025-08-18  
**Next Review**: 2025-08-25