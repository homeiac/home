# RCA: still-fawn SSH Failure and System Unresponsiveness

**Date**: 2025-11-29
**Duration**: ~11 days (Nov 18 - Nov 29)
**Severity**: High - Node SSH access completely unavailable
**Status**: Resolved (hard reboot), root cause partially unknown

## Summary

The Proxmox host `still-fawn` became unresponsive to SSH connections. The system was pingable and participating in the Proxmox cluster, but SSH connections were reset during key exchange. A hard reboot resolved the issue.

## Timeline

| Date/Time (UTC) | Event |
|-----------------|-------|
| Nov 12 03:07 | System boot |
| Nov 12 03:09 | rpool spam errors begin (every 10 seconds) |
| Nov 17 22:24 | Corosync cluster communication failure - "FAILED TO RECEIVE" |
| Nov 18 09:04 | **Last journal entry** - logs stop being written |
| Nov 18 ~12:00 | **CPU spike begins** - jumps from ~2% to 20%+ (visible in Proxmox graphs) |
| Nov 18 - Nov 29 | System running but degraded, SSH unresponsive |
| Nov 29 ~20:45 | Issue discovered - SSH connection reset during key exchange |
| Nov 29 ~20:59 | Hard reboot performed |
| Nov 29 ~21:01 | System recovered, SSH working |

## Symptoms

1. **SSH Port Open But Connection Reset**: `nc -zv 192.168.4.17 22` succeeded, but SSH connections failed with `kex_exchange_identification: read: Connection reset by peer`
2. **Proxmox Web UI Unresponsive**: TLS handshake worked but HTTP returned empty response
3. **Cluster Membership Active**: Node was voting in Proxmox cluster and counted as online
4. **K3s VM Down**: VM 108 (k3s-vm-still-fawn) was stopped, had to be manually started after reboot
5. **Sustained High CPU**: ~20% CPU usage for 11 days (visible in Proxmox monitoring graphs)

## Root Cause Analysis

### Confirmed Contributing Factor: rpool Storage Misconfiguration

The `local-zfs` storage was configured to use `rpool/data`, but `rpool` does not exist on still-fawn (it uses ext4 root, not ZFS). This caused `pvestatd` to spam errors every 10 seconds:

```
pvestatd[1881]: zfs error: cannot open 'rpool': no such pool
pvestatd[1881]: could not activate storage 'local-zfs', zfs error: cannot import 'rpool': no such pool available
```

**However**: This same misconfiguration affected ALL non-pve nodes in the cluster (chief-horse, fun-bedbug, pumped-piglet), yet only still-fawn failed. Therefore, the rpool spam alone is NOT the root cause.

### Unknown: What Caused the Nov 18 CPU Spike

The journal stopped writing at 09:04 UTC on Nov 18. The CPU spike visible in Proxmox graphs began around 12:00 UTC (~4AM Pacific). We have no logs covering this 3-hour gap or the spike itself.

Possible causes (speculative):
- Journal/systemd-journald failure leading to resource accumulation
- K3s VM workload spike (VM uses 25GB of 31GB RAM, leaving minimal headroom)
- Some scheduled task or external event not captured in logs
- Memory pressure causing swap thrashing (though swap showed 0% usage after reboot)

### Why Logs Stopped

Unknown. Possible causes:
- Journal disk space exhaustion (unlikely - disk was 10% full after reboot)
- systemd-journald process hang
- Rate limiting due to rpool spam volume

## Resolution

### Immediate Fix
- Hard reboot of still-fawn
- Manual start of K3s VM (VM 108)

### Preventive Fix Applied
Added `nodes pve` restriction to `local-zfs` storage configuration:

```bash
# Before (affected all nodes)
zfspool: local-zfs
    pool rpool/data
    content images,rootdir
    sparse 1

# After (only affects pve node which has rpool)
zfspool: local-zfs
    pool rpool/data
    content images,rootdir
    sparse 1
    nodes pve
```

Restarted `pvestatd` on still-fawn to apply the fix.

## Lessons Learned

1. **Storage configurations should have explicit node restrictions** - Shared `/etc/pve/storage.cfg` means all nodes try to access all storage unless restricted
2. **Log monitoring gaps** - No alerting detected that still-fawn stopped writing logs for 11 days
3. **SSH health monitoring needed** - Node was "online" in cluster but SSH was dead; need SSH-specific health checks
4. **Documentation during debugging** - Work performed on still-fawn on Nov 12 (K3s VM provisioning, SSH configuration) was not documented with an RCA, making root cause analysis harder

## Action Items

| Priority | Action | Status |
|----------|--------|--------|
| P1 | Add `nodes` restriction to `local-zfs` storage | ✅ Done |
| P2 | Enable K3s VM autostart on still-fawn | TODO |
| P2 | Add SSH connectivity monitoring/alerting for Proxmox hosts | TODO |
| P3 | Add journal write health monitoring | TODO |
| P3 | Review all storage configs for missing node restrictions | TODO |

## Affected Systems

- **still-fawn.maas** (192.168.4.17) - Proxmox host
- **k3s-vm-still-fawn** (192.168.4.212) - K3s cluster node (down during incident)

## Tags

proxmox, still-fawn, ssh, sshd, rpool, zfs, storage, pvestatd, unresponsive, cpu-spike, journal, systemd
