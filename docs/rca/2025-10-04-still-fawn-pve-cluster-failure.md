# Root Cause Analysis: still-fawn Node pve-cluster Service Failure

## Incident Summary
- **Date**: October 4, 2025
- **Impact**: Proxmox node `still-fawn` lost web GUI access after reboot
- **Duration**: September 19 - October 4, 2025 (intermittent)
- **Resolution**: October 5, 2025

## Timeline (Pacific Time)
- **Sep 18, 8:03 PM**: Last known good reboot
- **Oct 3, 9:27 AM**: System rebooted, pve-cluster service failed to start
- **Oct 3, 9:30 AM**: pveproxy errors: "failed to load local private key"
- **Oct 4, 6:36 PM**: Another reboot, pve-cluster started successfully
- **Oct 5, 6:30 PM**: Root cause identified and permanent fix applied

## Root Cause

### Primary Issue: Systemd Service Ordering Cycle
A circular dependency existed between Ceph and Proxmox services:
1. `ceph-mon@still-fawn.service` had `After=pve-cluster.service` (via drop-in)
2. `pve-cluster.service` requires cluster filesystem mount
3. Circular dependency detected by systemd on boot

### Critical Finding
Systemd randomly chose which service to sacrifice when breaking the ordering cycle:
- **Oct 4 Boot (Failed)**: systemd deleted `pve-cluster.service/start`
- **Oct 5 Boot (Successful)**: systemd deleted `ceph-mon@still-fawn.service/start`

### Evidence
```
Oct 04 16:27:58 systemd[1]: ceph-mon@still-fawn.service: Found ordering cycle on pve-cluster.service/start
Oct 04 16:27:58 systemd[1]: ceph-mon@still-fawn.service: Job pve-cluster.service/start deleted to break ordering cycle
```

## Impact Analysis

### When pve-cluster Failed to Start:
1. Cluster filesystem (`/etc/pve`) not mounted properly
2. SSL certificates not accessible (`/etc/pve/local/pve-ssl.key`)
3. pveproxy unable to serve web GUI
4. Node appeared offline in cluster despite SSH access working

### Services Affected:
- pve-cluster (Proxmox cluster filesystem)
- pveproxy (Web GUI)
- pvedaemon (API daemon)
- All dependent Proxmox services

## Resolution

### Immediate Fix Applied:
1. **Disabled Ceph services** (not in use)
   ```bash
   systemctl disable ceph-mon@still-fawn.service ceph-crash.service ceph.target
   ```

2. **Removed problematic systemd drop-in**
   ```bash
   rm /usr/lib/systemd/system/ceph-mon@.service.d/ceph-after-pve-cluster.conf
   systemctl daemon-reload
   ```

3. **Cleaned Ceph remnants**
   - Removed `/etc/ceph` and `/var/lib/ceph`
   - Destroyed unused ZFS volume `local-2TB-zfs/ceph-osd`
   - Kept Ceph packages (Proxmox dependencies)

### Secondary Issue Fixed:
- Proxmox Backup Server storage using non-resolving hostname
- Changed from `proxmox-backup-server.maas` to IP `192.168.4.218`

## Prevention

### Short-term:
- Monitor systemd boot logs for ordering cycles
- Ensure critical services have proper dependency declarations
- Regular verification of service start order

### Long-term:
- Add MAAS DNS entry for PBS container
- Document all storage dependencies
- Implement monitoring for pve-cluster service health

## Lessons Learned

1. **Systemd ordering cycles are non-deterministic** - The service deleted to break the cycle is randomly chosen
2. **Unused services should be removed** - Ceph was installed but not configured or used
3. **DNS dependencies matter** - Storage backends should use IPs or ensure DNS availability
4. **Service dependencies need careful review** - Especially for critical infrastructure services

## Verification

Post-fix verification completed:
- ✅ Node rebooted successfully
- ✅ pve-cluster starts reliably
- ✅ No ordering cycle errors in journalctl
- ✅ Web GUI accessible
- ✅ PBS storage repositories active

## Related Issues
- Ceph installation was incomplete/abandoned
- MAAS DNS missing entry for PBS container
- No monitoring for cluster filesystem health

## Tags
proxmox, pve-cluster, systemd, ordering-cycle, ceph, boot-failure, gui-access, ssl-certificate