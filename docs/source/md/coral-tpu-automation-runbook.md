# Coral TPU Automation System - Operations Runbook

This runbook provides procedures for maintaining, updating, and troubleshooting the Coral TPU automation system.

## 🔍 System Overview

The Coral TPU automation system eliminates manual initialization after system restarts by automatically:
- Detecting Coral TPU device state
- Initializing TPU when needed (safely)
- Managing LXC container configuration
- Providing comprehensive logging and monitoring

## 📊 Health Check Procedures

### Quick Status Check

```bash
# Check overall system health
coral-tpu --status-only

# Expected output for healthy system:
# ✅ Coral Mode: GOOGLE
# ✅ Config Matches: ✅
# ✅ Container Status: running
# ✅ Actions: ['no_action']
```

### Detailed Service Verification

```bash
# 1. Check systemd service status
systemctl status coral-tpu-init.service

# Expected: Active (exited) and enabled

# 2. Review recent service logs
journalctl -u coral-tpu-init.service --since "1 hour ago" --no-pager

# Expected: No errors, "System was already optimal"

# 3. Verify service is enabled for boot
systemctl is-enabled coral-tpu-init.service

# Expected: enabled

# 4. Check USB device detection
lsusb | grep -E "(18d1:9302|1a6e:089a)"

# Expected: "ID 18d1:9302 Google Inc." (Google mode)

# 5. Verify LXC container configuration
pct config 113 | grep -E "(dev0|cgroup.*189)"

# Expected: dev0 pointing to correct USB device path
```

### Hardware Verification

```bash
# 1. Check Coral device accessibility
ls -l /dev/bus/usb/003/004

# Expected: Device file exists with proper permissions

# 2. Verify container can access device
pct exec 113 -- ls -l /dev/bus/usb/003/004

# Expected: Device accessible from within container

# 3. Test Coral inference (optional - only if Frigate not using)
pct exec 113 -- python3 -c "from pycoral.utils import edgetpu; print('TPU available:', len(edgetpu.list_edge_tpus()) > 0)"

# Expected: TPU available: True
```

## 🔄 Update Procedures

### Updating Automation Code

When automation code changes are made in the repository:

```bash
# 1. Navigate to repository root
cd /path/to/homelab/repo

# 2. Ensure latest changes are committed
git status
git pull origin master

# 3. Run deployment script
./proxmox/homelab/scripts/sync_coral_automation.sh fun-bedbug.maas

# 4. Verify deployment
ssh root@fun-bedbug.maas "coral-tpu --status-only"

# 5. Restart service to pick up changes
ssh root@fun-bedbug.maas "systemctl restart coral-tpu-init.service"

# 6. Verify service restart
ssh root@fun-bedbug.maas "systemctl status coral-tpu-init.service"
```

### Testing Updates Safely

```bash
# 1. Always test with dry-run first
coral-tpu --dry-run

# 2. Check what actions would be taken
# Expected for healthy system: "System was already optimal"

# 3. If changes are needed, create backup first
cp /etc/pve/lxc/113.conf /root/coral-backups/manual-backup-$(date +%Y%m%d_%H%M%S).conf

# 4. Run automation with verbose logging
coral-tpu --verbose

# 5. Verify no unexpected changes
diff /etc/pve/lxc/113.conf /root/coral-backups/manual-backup-*.conf
```

### Rolling Back Updates

If an update causes issues:

```bash
# 1. Stop the service immediately
systemctl stop coral-tpu-init.service

# 2. Restore previous automation code (if needed)
git log --oneline -10  # Find previous commit
git checkout <previous-commit-hash> -- proxmox/homelab/src/homelab/coral_*

# 3. Redeploy previous version
./proxmox/homelab/scripts/sync_coral_automation.sh fun-bedbug.maas

# 4. Restore LXC config from backup (if modified)
ls -la /root/coral-backups/
cp /root/coral-backups/lxc_113_<timestamp>.conf /etc/pve/lxc/113.conf

# 5. Restart container (if config was restored)
pct stop 113 && pct start 113

# 6. Verify system health
coral-tpu --status-only

# 7. Re-enable service only when confirmed working
systemctl start coral-tpu-init.service
```

## 🚨 Troubleshooting Guide

### Common Issues and Solutions

#### Issue: Service Fails at Boot with "Config file not found"

This is the most common issue - the service runs before Proxmox mounts `/etc/pve/`.

```bash
# Diagnosis - check for this specific error
journalctl -u coral-tpu-init.service --no-pager | grep "Config file not found"

# Example error:
# homelab.coral_config - WARNING - Config file not found: /etc/pve/lxc/113.conf

# Root cause: Service started before pve-cluster.service mounted /etc/pve/
# The /etc/pve/ directory is a FUSE filesystem (pmxcfs) that's only available
# after the Proxmox cluster services start.

# Solution: Update service dependencies
cat > /etc/systemd/system/coral-tpu-init.service << 'EOF'
[Unit]
Description=Coral TPU Initialization Service
After=pve-cluster.service pveproxy.service
Wants=pve-cluster.service
Requires=pve-cluster.service

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/python3 /root/coral-automation/scripts/coral_tpu_automation.py
Environment=PYTHONPATH=/root/coral-automation/src
WorkingDirectory=/root/coral-automation
StandardOutput=journal
StandardError=journal
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# Reload and restart
systemctl daemon-reload
systemctl restart coral-tpu-init.service
```

#### Issue: Service Fails to Start (Other Causes)

```bash
# Diagnosis
systemctl status coral-tpu-init.service -l
journalctl -u coral-tpu-init.service --no-pager

# Common causes:
# 1. Python import errors
# 2. Missing dependencies
# 3. Permission issues
# 4. File path problems

# Solutions
# Install missing dependencies
pip3 install typing-extensions dataclasses pathlib

# Check file permissions
ls -la /root/coral-automation/scripts/coral_tpu_automation.py
chmod +x /root/coral-automation/scripts/coral_tpu_automation.py

# Verify Python path
export PYTHONPATH="/root/coral-automation/src"
python3 /root/coral-automation/scripts/coral_tpu_automation.py --help
```

#### Issue: Coral Device Not Detected

```bash
# Diagnosis
lsusb | grep -E "(18d1:9302|1a6e:089a)"
coral-tpu --status-only

# Solutions
# Check USB connections
lsusb | grep -i google
lsusb | grep -i unichip

# Verify device paths
ls -la /dev/bus/usb/*/

# Check for device changes
dmesg | grep -i coral
dmesg | grep -i usb
```

#### Issue: Container Cannot Access Coral

```bash
# Diagnosis
pct config 113 | grep dev0
pct exec 113 -- ls -l /dev/bus/usb/003/004

# Solutions
# Update device path in config
coral-tpu --dry-run  # See what would be changed
coral-tpu            # Apply changes

# Manual config update (emergency)
nano /etc/pve/lxc/113.conf
# Update dev0 line to correct device path
pct stop 113 && pct start 113
```

#### Issue: Frigate Loses TPU Access

```bash
# Immediate response
systemctl stop coral-tpu-init.service

# Restore from backup
ls -la /root/coral-backups/
cp /root/coral-backups/lxc_113_<latest>.conf /etc/pve/lxc/113.conf
pct stop 113 && pct start 113

# Verify Frigate can access TPU
pct exec 113 -- python3 -c "from pycoral.utils import edgetpu; print(edgetpu.list_edge_tpus())"

# Check Frigate logs
pct exec 113 -- tail -f /opt/frigate/logs/frigate.log
```

### Log Analysis

#### Key Log Messages

**Healthy Operation:**
```
INFO - Coral detected in Google mode: Google Inc.
INFO - System is optimal - Coral initialized and config correct
INFO - ✓ No actions required - system is optimal
```

**Initialization Needed:**
```
INFO - Coral detected in Unichip mode: Global Unichip Corp.
INFO - Container stopped, safe to initialize
INFO - Initializing Coral TPU...
INFO - ✓ Coral initialization successful
```

**Safety Abort:**
```
ERROR - SAFETY VIOLATION: Cannot initialize Coral in Google mode
ERROR - Container running while Coral needs init - not safe
ERROR - Aborting automation due to unsafe conditions
```

#### Log Locations

```bash
# Application logs
tail -f /var/log/coral-tpu-automation.log

# Systemd journal
journalctl -u coral-tpu-init.service -f

# Filter for errors only
journalctl -u coral-tpu-init.service --since "1 day ago" | grep -i error

# Get service start/stop events
journalctl -u coral-tpu-init.service --since "1 week ago" | grep -E "(Started|Stopped|Failed)"
```

## 📅 Maintenance Schedule

### Daily Checks (Automated)

The system performs self-checks on every boot via systemd service.

### Weekly Verification (Manual)

```bash
# 1. Check service health
systemctl status coral-tpu-init.service

# 2. Review logs for any issues
journalctl -u coral-tpu-init.service --since "1 week ago" | grep -i error

# 3. Verify Coral detection
coral-tpu --status-only

# 4. Check backup directory
ls -la /root/coral-backups/ | tail -10
```

### Monthly Tasks

```bash
# 1. Clean old backups (keep last 30 days)
find /root/coral-backups/ -name "lxc_113_*.conf" -mtime +30 -delete

# 2. Verify test suite still passes (development)
cd /path/to/homelab/repo
poetry run pytest tests/test_coral_*.py -v

# 3. Check for automation updates
git log --oneline --since="1 month ago" -- proxmox/homelab/src/homelab/coral_*

# 4. Review system performance
journalctl -u coral-tpu-init.service --since "1 month ago" | grep "execution time"
```

## 🔧 Emergency Procedures

### Complete System Recovery

If the automation system is completely broken:

```bash
# 1. Stop automation service
systemctl stop coral-tpu-init.service
systemctl disable coral-tpu-init.service

# 2. Manual Coral initialization (emergency only)
cd /root/code/coral/pycoral/examples
python3 classify_image.py --model ../test_data/mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite --labels ../test_data/inat_bird_labels.txt --input ../test_data/parrot.jpg

# 3. Restore LXC config from known good backup
cp /root/coral-backups/113.conf.pre-service /etc/pve/lxc/113.conf
pct stop 113 && pct start 113

# 4. Verify Frigate functionality
# Check Frigate web interface for TPU detection

# 5. Re-deploy automation when issue resolved
cd /path/to/homelab/repo
./proxmox/homelab/scripts/sync_coral_automation.sh fun-bedbug.maas
```

### Contact and Escalation

If issues persist after following this runbook:

1. **Check GitHub Issues**: Look for similar problems in the repository
2. **Create New Issue**: Document the problem with logs and steps taken
3. **Manual Operation**: Fall back to manual Coral initialization as temporary measure
4. **System Documentation**: Refer to `README_CORAL_AUTOMATION.md` for detailed architecture

## 📚 Reference Commands

### Quick Reference

```bash
# Status and health
coral-tpu --status-only
systemctl status coral-tpu-init.service
journalctl -u coral-tpu-init.service --since "1 hour ago"

# Operations
coral-tpu --dry-run                    # Preview actions
coral-tpu                             # Execute automation
coral-tpu --verbose                   # Detailed logging

# Service management
systemctl start coral-tpu-init.service
systemctl stop coral-tpu-init.service
systemctl restart coral-tpu-init.service
systemctl disable coral-tpu-init.service

# Configuration
pct config 113 | grep dev0           # Check LXC config
ls -la /root/coral-backups/          # List backups
lsusb | grep -E "(Google|Unichip)"   # Check USB devices

# Emergency manual initialization
cd /root/code/coral/pycoral/examples
python3 classify_image.py --model ../test_data/mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite --labels ../test_data/inat_bird_labels.txt --input ../test_data/parrot.jpg
```

This runbook ensures reliable operation and maintenance of the Coral TPU automation system while providing clear procedures for updates, troubleshooting, and emergency recovery.