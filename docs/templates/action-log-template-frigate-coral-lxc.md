# Action Log Template: Frigate Coral LXC Deployment

**Document Type**: Action Log Template
**Last Updated**: December 2025
**Blueprint**: `docs/troubleshooting/blueprint-frigate-coral-lxc-deployment.md`
**Reference**: `docs/source/md/coral-tpu-automation-runbook.md`

---

## Document Header

```
# Action Log: Frigate Coral LXC on <HOST_NAME>

**Date**: YYYY-MM-DD
**Operator**: [Name/AI Agent]
**GitHub Issue**: #XXX
**Target Host**: <HOST_NAME> (<IP_ADDRESS>)
**Container VMID**: <VMID>
**Status**: [Planning | In Progress | Completed | Failed | Rolled Back]
```

---

## Pre-Operation State

### Host Information
- **Hostname**: [HOST_NAME]
- **IP Address**: [IP]
- **Proxmox Version**: [VERSION]
- **CPU**: [MODEL]
- **GPU**: [MODEL or None]
- **Existing Containers**: [LIST]

### Coral USB Detection
```bash
# Output of 02-verify-coral-usb.sh
```

| Field | Value |
|-------|-------|
| Vendor ID | [1a6e/18d1] |
| Bus | [BUS] |
| Device | [DEV] |
| Sysfs Path | [SYSFS_PATH] |

### Prerequisites Check
```bash
# Output of 01-check-prerequisites.sh
```

---

## Phase 1: Pre-Flight Investigation

### Step 1.1: Check Prerequisites
**Script**: `01-check-prerequisites.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️
**Notes**: [NOTES]

---

### Step 1.2: Verify Coral USB
**Script**: `02-verify-coral-usb.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️
**Notes**: [NOTES]

---

### Step 1.3: Find Sysfs Path
**Script**: `03-find-sysfs-path.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Sysfs Path**: [PATH]
**Status**: ✅/❌/⚠️

---

### Step 1.4: Check Udev Rules
**Script**: `04-check-udev-rules.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Rules Needed**: [Yes/No]
**Status**: ✅/❌/⚠️

---

### Step 1.5: Check /dev/dri (CRITICAL)
**Script**: `04a-check-dev-dri.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**/dev/dri Exists**: [Yes/No]
**Status**: ✅/❌/⚠️

> **If /dev/dri missing**: Check `/etc/modprobe.d/` for GPU driver blacklist.
> Fix with: remove blacklist → `update-initramfs -u` → reboot

---

## Phase 2: Coral Firmware & Udev Rules (CRITICAL)

**Reference**: `docs/source/md/coral-tpu-automation-runbook.md`

### Step 2.1: Install dfu-util
**Script**: `05a-install-dfu-util.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

### Step 2.2: Download Firmware
**Script**: `05b-download-firmware.sh`
**Timestamp**: [HH:MM]
**Firmware Path**: `/usr/local/lib/firmware/apex_latest_single_ep.bin`
**Firmware Size**: [BYTES]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

### Step 2.3: Create Udev Rules
**Script**: `05c-create-udev-rules.sh`
**Timestamp**: [HH:MM]
**Rules File**: `/etc/udev/rules.d/95-coral-init.rules`
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

### Step 2.4: Reload Udev and Initialize Coral
**Script**: `06-reload-udev.sh`
**Timestamp**: [HH:MM]
**Before State**: [1a6e:089a / 18d1:9302]
**After State**: [1a6e:089a / 18d1:9302]
**New Device Path**: [/dev/bus/usb/XXX/XXX]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

> **Expected**: Coral changes from `1a6e:089a` (bootloader) to `18d1:9302` (Google Inc)

---

## Phase 3: Container Creation

### Step 3.1: Create Frigate Container (Manual)
**Method**: PVE Helper Script (interactive via SSH)
**Timestamp**: [HH:MM]
**Command**:
```bash
ssh root@<HOST>.maas
bash -c "$(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/ct/frigate.sh)"
```
**Settings**:
- RAM: [MB]
- CPU: [cores]
- Disk: [GB]
- GPU Passthrough: [Yes/No]

**Assigned VMID**: [VMID]
**Container Name**: [NAME]
**Status**: ✅/❌/⚠️

---

### Step 3.2: Stop Container
**Script**: `10-stop-container.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

## Phase 4: USB Passthrough

### Step 4.1: Add USB Passthrough
**Script**: `11-add-usb-passthrough.sh` (or manual)
**Timestamp**: [HH:MM]
**Config Line Added**: `dev[N]: /dev/bus/usb/XXX/XXX,mode=0666`
**Note**: [dev0/dev1 may be used by GPU if PVE Helper Script enabled it]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

### Step 4.2: Add Cgroup Permissions
**Script**: `12-add-cgroup-permissions.sh`
**Timestamp**: [HH:MM]
**Config Lines Added**:
- `lxc.cgroup2.devices.allow: c 189:* rwm`
**Pre-existing**: [Yes/No - PVE Helper Script may have added this]
**Status**: ✅/❌/⚠️

---

## Phase 5: VAAPI Passthrough (Optional)

### Step 5.1: Add VAAPI
**Script**: `13-add-vaapi-passthrough.sh`
**Timestamp**: [HH:MM]
**Skipped**: [Yes/No]
**Pre-existing**: [Yes/No - if PVE Helper Script configured GPU]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️/Skipped

---

## Phase 6: Hookscript

### Step 6.1: Create Hookscript
**Script**: `20-create-hookscript.sh` (or manual)
**Timestamp**: [HH:MM]
**Hookscript Path**: `/var/lib/vz/snippets/coral-lxc-hook-<VMID>.sh`
**Features**:
- Finds Coral by vendor ID (1a6e or 18d1)
- Updates dev[N] path in LXC config
- Logs to syslog with tag `coral-hook-<VMID>`
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

### Step 6.2: Attach Hookscript
**Script**: `21-attach-hookscript.sh`
**Timestamp**: [HH:MM]
**Config Line Added**: `hookscript: local:snippets/coral-lxc-hook-<VMID>.sh`
**Status**: ✅/❌/⚠️

---

## Phase 7: Initial Verification

### Step 7.1: Start Container
**Script**: `30-start-container.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

> **Common Issue**: Serial device mount failures (ttyUSB/ttyACM).
> Fix: Remove non-existent mount entries from LXC config.

---

### Step 7.2: Verify Hookscript
**Script**: `31-verify-hookscript.sh`
**Timestamp**: [HH:MM]
**Command**: `journalctl -t coral-hook-<VMID> --no-pager -n 20`
**Hookscript Logs**:
```
[PASTE OUTPUT]
```
**USB Path Updated**: [Yes/No]
**Status**: ✅/❌/⚠️

---

### Step 7.3: Verify USB in Container
**Script**: `34-verify-usb-in-container.sh`
**Timestamp**: [HH:MM]
**USB Bus Visible**: [Yes/No]
**Coral Device Path**: [/dev/bus/usb/XXX/XXX]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

## Phase 8: Frigate Configuration

### Initial State
**Detector Type**: [OpenVINO/CPU/Other]
**Inference Speed**: [X.X ms]
**CPU Load**: [X.X%]
**Frigate CPU Usage**: [X.X%]

---

### Step 8.1: Update Frigate Config
**Script**: `40-update-frigate-config.sh`
**Timestamp**: [HH:MM]
**Backup Created**: [PATH]
**Change**: [Describe detector change]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

### Step 8.2: Restart Frigate
**Script**: `41-restart-frigate.sh`
**Timestamp**: [HH:MM]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

## Phase 9: Coral Verification

### Step 9.1: Verify Frigate API
**Script**: `32-verify-frigate-api.sh`
**Timestamp**: [HH:MM]
**Frigate Version**: [VERSION]
**Status**: ✅/❌/⚠️

---

### Step 9.2: Verify Coral Detection
**Script**: `33-verify-coral-detection.sh`
**Timestamp**: [HH:MM]
**Detector Stats**:
```json
[PASTE OUTPUT]
```
**Inference Speed**: [X.X ms]
**Status**: ✅/❌/⚠️

---

### Step 9.3: Verify CPU Load Improvement
**Timestamp**: [HH:MM]
**CPU Load**: [X.X%]
**Frigate CPU Usage**: [X.X%]
**Load Average**: [X.XX]
**Status**: ✅/❌/⚠️

---

## Phase 10: Storage Passthrough (For Recordings)

**Required for production use** - Frigate needs storage for recordings.

### Step 10.1: Mount Storage on Host (Manual)
**Timestamp**: [HH:MM]
**Device**: [/dev/sdX1]
**Host Mount Path**: [/mnt/frigate-storage]
**Storage Size**: [X TB]
**Commands Used**:
```bash
# User physically connects drive, then:
mkdir -p /mnt/frigate-storage
mount /dev/sdX1 /mnt/frigate-storage
# Add to /etc/fstab for persistence
```
**Status**: ✅/❌/⚠️

---

### Step 10.2: Add Storage Mount to LXC
**Script**: `44-add-storage-mount.sh`
**Timestamp**: [HH:MM]
**Host Path**: [/mnt/frigate-storage]
**Container Path**: [/media/frigate]
**Config Line Added**: `mp[N]: /mnt/frigate-storage,mp=/media/frigate`
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

### Step 10.3: Verify Storage
**Script**: `45-verify-storage.sh`
**Timestamp**: [HH:MM]
**Storage Mounted**: [Yes/No]
**Storage Writable**: [Yes/No]
**Available Space**: [X GB/TB]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

### Step 10.4: Migrate Old Recordings (Optional)
**Timestamp**: [HH:MM]
**Skip if**: This is a fresh install with no existing recordings
**Old Recordings Location**: [ZFS subvolume path, e.g., /pool/subvol-XXX-disk-0/frigate/]
**Old Mount**: `mp0: [old path],mp=/media/frigate`
**New Mount**: `mp0: [new path to old frigate folder],mp=/media/frigate`
**Old Recordings Found**:
- `recordings/`: [X GB]
- `clips/`: [X GB]
- `exports/`: [exists/empty]
**Status**: ✅/❌/⚠️/Skipped

---

## Phase 11: Camera Configuration (THE GOAL)

**This is the critical phase** - Frigate is useless without cameras.

### Step 11.1: Configure Cameras
**Script**: `42-configure-cameras.sh`
**Timestamp**: [HH:MM]
**Config Source**: [proxmox/backups/frigate-app-config.yml / other]
**Cameras Configured**:
- [CAMERA_1_NAME] - [RTSP_URL]
- [CAMERA_2_NAME] - [RTSP_URL]
**Backup Created**: [PATH]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

### Step 11.2: Restart Frigate
**Script**: `41-restart-frigate.sh`
**Timestamp**: [HH:MM]
**Status**: ✅/❌/⚠️

---

### Step 11.3: Verify Cameras
**Script**: `43-verify-cameras.sh`
**Timestamp**: [HH:MM]
**Camera Status**:
| Camera | FPS | Detection | Status |
|--------|-----|-----------|--------|
| [NAME] | [X] | [X fps]   | ✅/❌  |

**Output**:
```
[PASTE OUTPUT]
```
**Status**: ✅/❌/⚠️

---

## Phase 12: Final Verification

### Step 12.1: Frigate UI Access
**Frigate URL**: http://[IP]:5000
**All Cameras Visible**: [Yes/No]
**Live Feeds Working**: [Yes/No]
**Status**: ✅/❌/⚠️

---

### Step 12.2: Object Detection Working
**Recent Detections**: [Yes/No]
**Objects Detected**: [person, car, etc.]
**Screenshot/Evidence**: [Optional]
**Status**: ✅/❌/⚠️

---

### Step 12.3: Recording Working
**Recordings Saving**: [Yes/No]
**Storage Location**: [/media/frigate/recordings]
**Storage Used**: [X GB]
**Status**: ✅/❌/⚠️

---

### Step 12.4: Home Assistant Integration (Optional)
**MQTT Connected**: [Yes/No/N/A]
**Entities Created**: [Yes/No/N/A]
**Status**: ✅/❌/⚠️/Skipped

---

## Post-Operation State

### Final Configuration
```bash
# Output of: cat /etc/pve/lxc/<VMID>.conf
```

### Success Criteria Checklist
- [ ] Container starts without errors
- [ ] Hookscript executes (check syslog)
- [ ] Coral inference speed < 20ms
- [ ] USB visible in container
- [ ] No restart loops (stable 10+ min)
- [ ] CPU load reduced compared to OpenVINO/CPU
- [ ] **All cameras streaming** (THE GOAL)
- [ ] **Object detection working** (person/car detections)
- [ ] Recordings being saved
- [ ] Home Assistant integration (if applicable)

### Performance Comparison

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Load Average | [X.XX] | [X.XX] | [X%] |
| CPU Usage | [X.X%] | [X.X%] | [X%] |
| Inference Speed | [X.X ms] | [X.X ms] | [X%] |
| Frigate CPU | [X.X%] | [X.X%] | [X%] |

---

## Issues Encountered

### Issue 1: [Description]
**Severity**: [Low/Medium/High/Critical]
**Time Encountered**: [HH:MM]
**Symptoms**:
- [Symptom 1]
- [Symptom 2]

**Root Cause**: [Analysis]

**Resolution**:
```bash
[Commands used]
```

**Prevention**: [How to prevent in future]

---

## Rollback Actions (if applicable)

**Trigger**: [What necessitated rollback]
**Script**: `90-rollback-full.sh`
**Timestamp**: [HH:MM]
**Result**: [Success/Partial/Failed]

---

## Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | [Success/Partial/Failed] |
| **Start Time** | [HH:MM] |
| **End Time** | [HH:MM] |
| **Total Duration** | [X hours Y minutes] |
| **Container VMID** | [VMID] |
| **Coral Inference Speed** | [X.X ms] |
| **CPU Load Reduction** | [X%] |

---

## Backups Created

| File | Purpose |
|------|---------|
| [PATH] | [DESCRIPTION] |

---

## Follow-Up Actions

- [ ] Monitor container stability for 24 hours
- [ ] Set up MQTT for Home Assistant (if applicable)
- [ ] Configure retention policies for recordings
- [ ] Close GitHub issue
- [ ] Update blueprint if issues were found

---

## Tags

frigate, coral, tpu, usb, proxmox, lxc, action-log, [HOST_NAME], homelab, dfu-util, edgetpu
