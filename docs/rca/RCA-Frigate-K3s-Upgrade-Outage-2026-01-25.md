# RCA: Frigate "No Available Server" During K3s Upgrade

**Date**: 2026-01-25
**Duration**: ~5-10 minutes
**Severity**: Medium (service unavailable)
**Author**: Infrastructure Team

## Summary

Frigate UI showed "no available server" after K3s cluster upgrade from v1.33.6 to v1.35.0. Root cause was delayed kubelet instability on secondary nodes causing MetalLB service IP advertisement failure.

## Timeline

| Time (PST) | Event |
|------------|-------|
| 13:33 | K3s upgrade to v1.34.3 started (intermediate step) |
| 13:38 | K3s upgrade to v1.34.3 completed |
| 13:41 | K3s upgrade to v1.35.0 started |
| 13:45 | K3s upgrade to v1.35.0 completed, all nodes reported Ready |
| 13:46 | fun-bedbug went NotReady (kubelet stopped posting status) |
| 13:52 | still-fawn went NotReady (kubelet stopped posting status) |
| 13:52 | Frigate pod on still-fawn affected by NodeNotReady taint |
| 13:53 | TaintManagerEviction triggered but then cancelled |
| 13:54 | MetalLB speaker on still-fawn stopped announcing Frigate IP |
| ~13:55 | User reports "no available server" in Frigate UI |
| 13:55 | Manual K3s restart on still-fawn |
| 13:56 | MetalLB re-announced Frigate service IPs |
| ~13:58 | Service restored |

## Root Cause

### Primary: Delayed Kubelet Instability After Upgrade

The K3s upgrade automation:
1. Runs install script via `nohup` in background
2. Polls for version change (detected correctly)
3. Waits for node Ready status (passed initially)
4. Uncordons and moves to next node

However, the kubelet instability manifested **5-10 minutes after** the upgrade script completed. The nodes showed as upgraded and Ready, but kubelets subsequently stopped posting heartbeats.

### Secondary: MetalLB L2 Failover Delay

MetalLB L2 mode **is HA** - speakers run on all nodes and leader election handles failover. However, failover is **not instant**:

1. Speaker runs as DaemonSet on all 3 nodes ✓
2. Only ONE speaker announces each service IP (leader election)
3. When still-fawn went NotReady, its speaker stopped responding
4. Leader election had to detect failure and elect new leader
5. New speaker sent gratuitous ARP to update network
6. Client ARP caches needed time to update

Evidence of failover working (eventually):
```
33m   nodeAssigned  service/frigate  announcing from node "k3s-vm-fun-bedbug"
27m   nodeAssigned  service/frigate  announcing from node "k3s-vm-pumped-piglet-gpu"
12m   nodeAssigned  service/frigate  announcing from node "k3s-vm-fun-bedbug"  # after recovery
```

**The outage window was the failover detection + ARP propagation time** (~30-60 seconds), not a complete HA failure. MetalLB L2 provides eventual consistency, not instant failover.

## Evidence

```bash
# Events showing the cascade
12m   NodeNotReady  node/k3s-vm-fun-bedbug
5m    NodeNotReady  node/k3s-vm-still-fawn
5m    NodeNotReady  pod/frigate-7d8ff58b5d-v9n4p
5m    NodeNotReady  pod/metallb-speaker-782f8

# MetalLB re-announcement after recovery
2m    nodeAssigned  service/frigate  announcing from node "k3s-vm-fun-bedbug"
```

## Why Automation Didn't Catch This

The upgrade script's post-upgrade validation:
- Checks version changed: **PASSED**
- Checks node Ready: **PASSED** (initially)
- 30-second inter-node delay: **INSUFFICIENT**

The delayed kubelet failure mode was not detected because the script had already moved on.

## Contributing Factors

1. **Background upgrade via nohup**: K3s restarts asynchronously, new binary may need clean restart cycle
2. **No sustained stability check**: Script doesn't verify node stays healthy over time
3. **Multiple nodes failed simultaneously**: Both fun-bedbug and still-fawn went NotReady within minutes, causing repeated MetalLB leader elections and extended service disruption

## Resolution

### Immediate (Done)
- Manually restarted K3s on affected nodes
- All nodes stable at v1.35.0+k3s1
- Frigate service restored

### Short-term (Recommended)

1. **Add post-upgrade stability monitoring** to `k3s_manager.py`:
   ```python
   # After upgrade, wait 60s and re-verify node Ready
   time.sleep(60)
   if not self.wait_for_node_ready(node.name, timeout=30):
       logger.warning(f"{node.name} became NotReady after upgrade")
   ```

2. **Force K3s service restart** after install script:
   ```python
   # Ensure clean kubelet state
   self._run_qm_exec(node.proxmox_host, node.vmid, "systemctl restart k3s")
   ```

3. **Add MetalLB health check** to upgrade validation

### Long-term (Recommended)

1. Enable pod anti-affinity for critical services
2. Consider Frigate HA if architecture supports it
3. Add Prometheus alerting for NodeNotReady during maintenance windows
4. Implement upgrade canary: upgrade one node, wait 5 minutes, continue

## Lessons Learned

1. **K3s in-place upgrades can cause delayed kubelet instability** - "Ready" immediately after upgrade doesn't guarantee stability
2. **MetalLB L2 is HA but not instant** - failover takes 30-60 seconds for leader election + ARP propagation
3. **Background upgrades need longer observation windows** - 30 seconds is insufficient
4. **Always have manual intervention ready** during cluster upgrades

## Related Documents

- [K3s Upgrade Automation](../../proxmox/homelab/src/homelab/k3s_manager.py)
- [RCA: Frigate Alert Storm](./RCA-Frigate-Alert-Storm-2026-01-17.md)

## Tags

k3s, kubernetes, upgrade, metallb, frigate, outage, kubelet, NotReady, L2advertisement
