# Root Cause Analysis: chief-horse pve-cluster Service Stopped After Reconfiguration

## Incident Summary
- **Date**: January 1, 2026
- **Impact**: chief-horse Proxmox host unresponsive - no web GUI, no API, HAOS VM stopped
- **Duration**: ~40 minutes after hardware reconfiguration
- **Resolution**: Manual service restart and VM start

## Timeline (UTC)
- **~03:27**: User reconfigured system (unplugged cables, hardware changes)
- **03:29**: System booted, pve-cluster service started but later stopped
- **04:05**: Investigation began - host responding to ping but SSH key auth failing
- **04:06**: Identified pve-cluster service dead, `/etc/pve/` empty
- **04:06:28**: Started pve-cluster service, /etc/pve/ mounted
- **04:06:48**: Restarted pveproxy, GUI accessible
- **04:07**: Started HAOS VM 116
- **04:08**: Full functionality restored

## Symptoms Observed
1. **Host pingable** but SSH key authentication failed (password required)
2. **Proxmox web UI not loading** (connection refused)
3. **pveproxy error**: `failed to load local private key at /etc/pve/local/pve-ssl.key`
4. **qm/pvesh commands failing**: `ipcc_send_rec failed: Connection refused`
5. **/etc/pve/ directory empty** (cluster filesystem not mounted)
6. **HAOS VM 116 stopped**

## Root Cause

### Primary Issue: pve-cluster Service Not Running
The `pve-cluster` service was in `inactive (dead)` state after boot, which caused:
1. Cluster filesystem (`/etc/pve/`) not mounted via FUSE
2. SSL certificates unavailable (stored in `/etc/pve/local/`)
3. pveproxy workers crashing on startup
4. All Proxmox management tools failing

### Why pve-cluster Stopped
After hardware reconfiguration (cable changes), the system rebooted. The pve-cluster service either:
- Failed to start due to network timing (corosync needs network)
- Started but stopped due to quorum issues during cluster sync
- Was affected by hardware changes impacting network availability

### Secondary Issue: HAOS VM Not Started
VM 116 (HAOS) was in stopped state - likely was not set to auto-start or the auto-start occurred before pve-cluster was ready.

## Resolution

### Steps Taken
```bash
# 1. SSH with password (key auth failed because /etc/pve not mounted)
ssh root@192.168.4.19  # using password

# 2. Check and start pve-cluster
systemctl status pve-cluster  # showed: inactive (dead)
systemctl start pve-cluster

# 3. Verify /etc/pve mounted
ls /etc/pve/  # now shows cluster config files

# 4. Restart Proxmox services
systemctl restart pvedaemon pvestatd pveproxy

# 5. Start HAOS VM
qm start 116

# 6. Re-add SSH key for future access
ssh-copy-id root@192.168.4.19
```

## Prevention

### Immediate Actions
1. **Verify VM auto-start settings**: Ensure HAOS VM 116 has auto-start enabled with appropriate delay
   ```bash
   qm config 116 | grep onboot
   qm set 116 --onboot 1 --startup order=2,up=60
   ```

2. **Check pve-cluster service dependencies**:
   ```bash
   systemctl list-dependencies pve-cluster.service
   ```

### Monitoring Recommendations
1. Add monitoring for pve-cluster service state
2. Alert on `/etc/pve/` mount status
3. Monitor HAOS API availability

### Hardware Reconfiguration Checklist
Before reconfiguring hardware:
1. Document current VM states
2. Note which VMs have auto-start enabled
3. After boot, verify:
   - `systemctl status pve-cluster` is active
   - `/etc/pve/` contains config files
   - `qm list` shows expected VMs
   - Critical VMs are running

## Related Documentation
- Runbook: [chief-horse-recovery.md](../runbooks/chief-horse-recovery.md)
- Similar incident: [2025-10-04-still-fawn-pve-cluster-failure.md](./2025-10-04-still-fawn-pve-cluster-failure.md)

## Tags
proxmox, pve-cluster, chief-horse, haos, service-failure, hardware-reconfiguration, boot-failure
