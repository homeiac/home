# Runbook: Fix Proxmox Node Boot Failures Due to Ceph Ordering Cycle

## Problem Statement
Proxmox nodes with Ceph installed may experience random boot failures where `pve-cluster` service doesn't start, causing loss of web GUI access. This occurs due to a systemd service ordering cycle between Ceph and Proxmox services.

## Symptoms
- Node accessible via SSH but not via Proxmox web GUI
- Error in logs: "failed to load local private key" from pveproxy
- `pvecm status` shows node in cluster but GUI shows it offline
- Random success/failure on reboots (approximately 50/50 chance)

## Pre-requisites
- SSH access to affected Proxmox node
- Root privileges
- Verify Ceph is not actively used for storage

## Detection

### Check for Ordering Cycle
```bash
# Check current boot for ordering cycles
journalctl -b | grep "ordering cycle"

# Check if pve-cluster failed to start
systemctl status pve-cluster.service

# Look for the problematic drop-in
ls -la /usr/lib/systemd/system/ceph-mon@.service.d/
```

### Verify Ceph Usage
```bash
# Check if Ceph is configured
ceph status

# Check storage configuration
pvesm status | grep ceph

# List Ceph services
systemctl list-units '*ceph*' --all
```

## Resolution Steps

### Step 1: Disable Ceph Services
```bash
# Disable all Ceph services to prevent boot issues
systemctl disable ceph-mon@$(hostname).service
systemctl disable ceph-crash.service
systemctl disable ceph.target
systemctl disable ceph-osd.target
systemctl disable ceph-mon.target
systemctl disable ceph-mgr.target
systemctl disable ceph-mds.target

# Stop running services
systemctl stop ceph-mon@$(hostname).service
systemctl stop ceph-crash.service
systemctl stop ceph.target
```

### Step 2: Remove Ordering Cycle Drop-in
```bash
# Remove the problematic systemd drop-in
rm -f /usr/lib/systemd/system/ceph-mon@.service.d/ceph-after-pve-cluster.conf

# Reload systemd
systemctl daemon-reload
```

### Step 3: Clean Ceph Configuration (if not in use)
```bash
# Purge Ceph configuration from Proxmox
pveceph purge

# Remove Ceph directories
rm -rf /etc/ceph
rm -rf /var/lib/ceph

# Check for Ceph ZFS volumes
zfs list | grep ceph

# If found, destroy them
# zfs destroy <pool>/ceph-osd
```

### Step 4: Verify and Test
```bash
# Reboot the node
reboot

# After reboot, verify no ordering cycles
journalctl -b | grep "ordering cycle"

# Verify pve-cluster is running
systemctl status pve-cluster

# Check web GUI accessibility
curl -k https://localhost:8006 >/dev/null && echo "GUI responding"
```

## Important Notes

### DO NOT Remove Ceph Packages
Ceph packages are dependencies of proxmox-ve meta-package. Removing them may break Proxmox installation:
```bash
# DO NOT RUN: apt remove ceph ceph-common
# This would remove proxmox-ve meta-package
```

### If Ceph is Actually Needed
If you need Ceph functionality:
1. Properly configure Ceph cluster first
2. Ensure all nodes are in quorum
3. Consider alternative dependency management
4. Contact Proxmox support for proper Ceph integration

## Rollback Plan

If issues occur after changes:

### Re-enable Ceph Services
```bash
# Re-enable services if Ceph is needed
systemctl enable ceph-mon@$(hostname).service
systemctl enable ceph.target

# Restore drop-in if needed (not recommended)
mkdir -p /usr/lib/systemd/system/ceph-mon@.service.d/
echo "[Unit]" > /usr/lib/systemd/system/ceph-mon@.service.d/ceph-after-pve-cluster.conf
echo "After=pve-cluster.service" >> /usr/lib/systemd/system/ceph-mon@.service.d/ceph-after-pve-cluster.conf
systemctl daemon-reload
```

## Prevention

### For New Installations
1. Only install Ceph if actively using Ceph storage
2. Properly configure Ceph cluster before enabling services
3. Test boot reliability after Ceph installation

### Monitoring
Add monitoring for:
- pve-cluster service status
- Systemd boot time and errors
- Web GUI availability from external monitoring

## Related Issues
- Proxmox Bug #4353: systemd ordering cycles with Ceph
- Random boot failures on nodes with incomplete Ceph setup
- SSL certificate accessibility depends on pve-cluster mount

## Tags
proxmox, ceph, systemd, boot-failure, pve-cluster, ordering-cycle, troubleshooting