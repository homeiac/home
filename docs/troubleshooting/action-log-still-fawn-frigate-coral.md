# Action Log: Frigate Coral LXC on still-fawn

**Date**: 2025-12-10 / 2025-12-11
**Operator**: Claude Code AI Agent
**GitHub Issue**: #168
**Target Host**: still-fawn (192.168.4.17)
**Container VMID**: 110
**Status**: ✅ Completed

---

## Pre-Operation State

### Host Information
- **Hostname**: still-fawn
- **IP Address**: 192.168.4.17
- **Proxmox Version**: 8.x
- **CPU**: Intel Core i5-4460 @ 3.20GHz (4 cores)
- **GPU**: AMD Radeon RX 580
- **Existing Containers**: 104 (docker-webtop)

### Coral USB Detection
| Field | Value |
|-------|-------|
| Vendor ID | 1a6e (uninitialized) |
| Bus | 004 |
| Device | 002 |
| Sysfs Path | 4-2 |

---

## Phase 1: Pre-Flight Investigation

### Step 1.1: Check Prerequisites
**Script**: `01-check-prerequisites.sh`
**Timestamp**: 2025-12-10 23:23 UTC
**Status**: ✅ Passed

### Step 1.2: Verify Coral USB
**Script**: `02-verify-coral-usb.sh`
**Timestamp**: 2025-12-10 23:23 UTC
**Output**: Coral found at Bus 004 Device 002 (1a6e:089a)
**Status**: ✅ Passed

### Step 1.3: Find Sysfs Path
**Script**: `03-find-sysfs-path.sh`
**Sysfs Path**: 4-2
**Status**: ✅ Passed

### Step 1.4: Check Udev Rules
**Script**: `04-check-udev-rules.sh`
**Result**: No Coral-specific rules found
**Status**: ⚠️ Phase 2 Required

---

## Phase 1.5: Fix /dev/dri (Blocking Issue)

**Issue**: `/dev/dri` did not exist on host - blocking PVE Helper Script installation

**Root Cause**: AMD GPU drivers (amdgpu) were blacklisted in `/etc/modprobe.d/pve-blacklist.conf` - leftover from previous NVIDIA RTX 3070 passthrough setup

**Fix Applied**:
1. Removed AMD driver blacklist entries
2. Ran `update-initramfs -u`
3. Rebooted host
4. Created `04a-check-dev-dri.sh` detection script for future deployments

**Status**: ✅ Resolved

---

## Phase 2: Coral Firmware & Udev Rules (CRITICAL FIX)

**Blueprint Issue Found**: Original `05-create-udev-rules.sh` only set permissions, missing the critical `dfu-util` firmware loading rule documented in `docs/source/md/coral-tpu-automation-runbook.md`

**Blueprint Updated**: Added new scripts and phases:
- `05a-install-dfu-util.sh` - Install dfu-util package
- `05b-download-firmware.sh` - Download firmware from Google libedgetpu repo
- `05c-create-udev-rules.sh` - Create udev rules WITH firmware loading

### Step 2.1: Install dfu-util
**Script**: `05a-install-dfu-util.sh`
**Timestamp**: 2025-12-11 03:35 UTC
**Status**: ✅ Completed

### Step 2.2: Download Firmware
**Script**: `05b-download-firmware.sh`
**Timestamp**: 2025-12-11 03:35 UTC
**Firmware**: `/usr/local/lib/firmware/apex_latest_single_ep.bin` (10783 bytes)
**Status**: ✅ Completed

### Step 2.3: Create Udev Rules
**Script**: `05c-create-udev-rules.sh`
**Timestamp**: 2025-12-11 03:35 UTC
**Rules File**: `/etc/udev/rules.d/95-coral-init.rules`
**Content**:
```
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="1a6e", ATTR{idProduct}=="089a", RUN+="/usr/bin/dfu-util -D /usr/local/lib/firmware/apex_latest_single_ep.bin -d 1a6e:089a -R"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="1a6e", ATTRS{idProduct}=="089a", MODE="0666", GROUP="plugdev"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="18d1", ATTRS{idProduct}=="9302", MODE="0666", GROUP="plugdev"
```
**Status**: ✅ Completed

### Step 2.4: Reload Udev and Initialize Coral
**Script**: `06-reload-udev.sh`
**Timestamp**: 2025-12-11 03:35 UTC
**Before**: `1a6e:089a` (Global Unichip - bootloader)
**After**: `18d1:9302` (Google Inc - initialized)
**New Device Path**: `/dev/bus/usb/004/003`
**Status**: ✅ Coral initialized successfully

---

## Phase 3: Container Creation

**Method**: User ran PVE Helper Script interactively via SSH
**Timestamp**: 2025-12-11 ~03:20 UTC
**Settings**:
- RAM: 8192 MB
- CPU: 8 cores
- Disk: 20 GB
- GPU: Yes (RX 580 VAAPI)
**Assigned VMID**: 110
**Container Name**: frigate-sf
**Status**: ✅ Completed by user

---

## Phase 4: USB Passthrough

### Step 4.1: Add USB Passthrough
**Timestamp**: 2025-12-11 03:36 UTC
**Config Line Added**: `dev2: /dev/bus/usb/004/003,mode=0666`
**Note**: dev0/dev1 already used by GPU passthrough from PVE Helper Script
**Status**: ✅ Completed

### Step 4.2: Cgroup Permissions
**Pre-existing**: PVE Helper Script already added `lxc.cgroup2.devices.allow: c 189:* rwm`
**Status**: ✅ Already configured

---

## Phase 5: VAAPI Passthrough

**Status**: ✅ Already configured by PVE Helper Script
- `dev0: /dev/dri/renderD128`
- `dev1: /dev/dri/card0`

---

## Phase 6: Hookscript

### Step 6.1: Create Hookscript
**Timestamp**: 2025-12-11 03:37 UTC
**Hookscript Path**: `/var/lib/vz/snippets/coral-lxc-hook-110.sh`
**Features**:
- Finds Coral by vendor ID (1a6e or 18d1)
- Updates `dev2` path in LXC config (device number may change after reboot)
- Logs to syslog with tag `coral-hook-110`
**Status**: ✅ Completed

### Step 6.2: Attach Hookscript
**Timestamp**: 2025-12-11 03:37 UTC
**Config Line**: `hookscript: local:snippets/coral-lxc-hook-110.sh`
**Status**: ✅ Completed

---

## Phase 7: Initial Verification

### Step 7.1: Start Container
**Timestamp**: 2025-12-11 03:38 UTC
**Initial Failure**: Serial device mounts for non-existent devices
**Fix**: Removed `/dev/ttyUSB*`, `/dev/ttyACM*`, `/dev/serial/by-id` mount entries
**Status**: ✅ Container started after fix

### Step 7.2: Verify Hookscript
**Timestamp**: 2025-12-11 03:38 UTC
**Logs**: `journalctl -t coral-hook-110` showed successful execution
**USB Path Updated**: Yes
**Status**: ✅ Completed

### Step 7.3: Verify USB in Container
**USB Bus Visible**: `/dev/bus/usb/004/` exists in container
**Coral Device**: Accessible at `/dev/bus/usb/004/003`
**Status**: ✅ Completed

---

## Phase 8: Frigate Configuration

### Initial State (OpenVINO)
**Detector**: OpenVINO on CPU
**Inference Speed**: 9.43ms
**CPU Load**: 67.7% user, Load Average 1.51
**Frigate CPU Usage**: ~287% (2.9 cores)

### Step 8.1: Update Frigate Config
**Script**: `40-update-frigate-config.sh` (newly created)
**Timestamp**: 2025-12-11 03:42 UTC
**Backup Created**: `proxmox/backups/still-fawn/frigate-config-before-coral-20251210-194240.yml`
**Change**: Replaced OpenVINO detector with Coral EdgeTPU
**Status**: ✅ Completed

### Step 8.2: Restart Frigate
**Script**: `41-restart-frigate.sh` (newly created)
**Timestamp**: 2025-12-11 03:46 UTC
**Status**: ✅ Completed

---

## Phase 9: Coral Verification

### Step 9.1: Verify Coral Detection
**Script**: `33-verify-coral-detection.sh`
**Timestamp**: 2025-12-11 03:47 UTC
**Output**:
```json
{
  "coral": {
    "detection_start": 1765425123.120152,
    "inference_speed": 10.0,
    "pid": 2777
  }
}
```
**Inference Speed**: 10.0ms
**Status**: ✅ Coral TPU working

### Step 9.2: Verify CPU Load
**Timestamp**: 2025-12-11 03:52 UTC
**CPU Load**: 1.6% user, Load Average 0.34
**Frigate CPU Usage**: 6.2%
**Status**: ✅ Massive improvement

---

## Post-Operation State

### Final Configuration
```
arch: amd64
cores: 8
dev0: /dev/dri/renderD128,gid=105
dev1: /dev/dri/card0,gid=44
dev2: /dev/bus/usb/004/003,mode=0666
features: nesting=1,fuse=1
hookscript: local:snippets/coral-lxc-hook-110.sh
hostname: frigate-sf
memory: 8192
```

### Success Criteria Checklist
- [x] Container starts without errors
- [x] Hookscript executes (check syslog)
- [x] Coral inference speed < 20ms (10.0ms achieved)
- [x] USB visible in container
- [x] No restart loops (stable)

### Performance Comparison

| Metric | Before (OpenVINO/CPU) | After (Coral TPU) | Improvement |
|--------|----------------------|-------------------|-------------|
| Load Average | 1.51 | 0.34 | **77% reduction** |
| CPU Usage | 67.7% | 1.6% | **98% reduction** |
| CPU Idle | 19.4% | 96.7% | **5x more idle** |
| Inference Speed | 9.43ms | 10.0ms | Similar |
| Frigate CPU | ~287% | 6.2% | **98% reduction** |

---

## Issues Encountered

### Issue 1: Blueprint Missing dfu-util Firmware Loading
**Severity**: High
**Time Encountered**: 2025-12-11 03:30 UTC
**Symptoms**: Coral stayed in bootloader mode (1a6e:089a), never initialized

**Root Cause**: `05-create-udev-rules.sh` only set permissions, missing the `RUN+=` dfu-util rule documented in `coral-tpu-automation-runbook.md`

**Resolution**: Created new scripts `05a-install-dfu-util.sh`, `05b-download-firmware.sh`, `05c-create-udev-rules.sh`

**Prevention**: Updated blueprint Phase 2 with complete firmware loading procedure

### Issue 2: Serial Device Mount Failures
**Severity**: Medium
**Time Encountered**: 2025-12-11 03:37 UTC
**Symptoms**: Container failed to start with "No such file or directory" for ttyUSB/ttyACM

**Root Cause**: PVE Helper Script adds optional serial device mounts that don't exist on still-fawn

**Resolution**: Removed non-existent serial device mount entries from LXC config

**Prevention**: Add cleanup step to blueprint or modify script behavior

### Issue 3: Direct File Modification Without Backup
**Severity**: Process Violation
**Time Encountered**: 2025-12-11 03:42 UTC
**Symptoms**: Attempted to modify Frigate config directly without using script/backup

**Root Cause**: Operator (AI) not following established procedures

**Resolution**: Restored from backup, created proper scripts `40-update-frigate-config.sh` and `41-restart-frigate.sh`

**Prevention**: All config modifications must go through scripts that backup first

---

## Phase 10: Storage Passthrough

### Step 10.1: Mount Storage on Host
**Timestamp**: 2025-12-11 04:14 UTC
**Device**: /dev/sdc (USB WD 3TB)
**ZFS Pool**: `local-3TB-backup` (imported from fun-bedbug)
**Host Mount Path**: `/local-3TB-backup`
**Storage Size**: 2.7TB (2.3TB available)
**Status**: ✅ Completed

### Step 10.2: Add Storage Mount to LXC
**Script**: `44-add-storage-mount.sh`
**Timestamp**: 2025-12-11 04:16 UTC
**Config Line Added**: `mp0: /local-3TB-backup,mp=/media/frigate`
**Status**: ✅ Completed

### Step 10.3: Verify Storage
**Script**: `45-verify-storage.sh`
**Timestamp**: 2025-12-11 04:20 UTC
**Storage Mounted**: Yes
**Storage Writable**: Yes
**Available Space**: 2355GB
**Status**: ✅ Completed

### Step 10.4: Update Mount to Access Old Recordings
**Timestamp**: 2025-12-11 05:05 UTC
**Issue**: New mount at `/local-3TB-backup` didn't include old Frigate recordings from fun-bedbug
**Old Recordings Location**: `/local-3TB-backup/subvol-113-disk-0/frigate/` (ZFS subvolume from LXC 113)
**Old Mount**: `mp0: /local-3TB-backup,mp=/media/frigate`
**New Mount**: `mp0: /local-3TB-backup/subvol-113-disk-0/frigate,mp=/media/frigate`
**Old Recordings Preserved**:
- `recordings/`: 88GB
- `clips/`: 1.1GB
- `exports/`: existing exports
- `person-bicycle-car-detection.mp4`: test video
**Status**: ✅ Completed - Old recordings now accessible

---

## Phase 11: Camera Configuration

### Step 11.1: Configure Cameras
**Script**: `42-configure-cameras.sh`
**Timestamp**: 2025-12-11 04:20 UTC
**Config Source**: `proxmox/backups/frigate-app-config.yml`
**Cameras Configured**:
- `old_ip_camera` - MJPEG at 192.168.1.220 (offline)
- `trendnet_ip_572w` - RTSP at 192.168.1.107
- `reolink_doorbell` - RTSP at 192.168.1.158
**Backup Created**: `proxmox/backups/still-fawn/frigate-config-before-cameras-20251210-202005.yml`
**Status**: ✅ Completed

### Step 11.2: Restart Frigate
**Script**: `41-restart-frigate.sh`
**Timestamp**: 2025-12-11 04:23 UTC
**Status**: ✅ Completed

### Step 11.3: Verify Cameras
**Timestamp**: 2025-12-11 04:31 UTC
**Camera Status**:
| Camera | FPS | Detection FPS | Status |
|--------|-----|---------------|--------|
| reolink_doorbell | 5.1 | 1.9 | ✅ Working |
| trendnet_ip_572w | 5.1 | 0 | ✅ Streaming |
| old_ip_camera | 0 | 0 | ❌ Offline |

**Status**: ✅ 2/3 cameras working

---

## Phase 12: Final Verification

### Step 12.1: Final Stats
**Timestamp**: 2025-12-11 04:31 UTC
**Coral Inference Speed**: 7.8ms
**Cameras Streaming**: 2/3
**Object Detection**: Active on reolink_doorbell
**Status**: ✅ Complete

---

## Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | ✅ Success |
| **Start Time** | 2025-12-10 23:23 UTC |
| **End Time** | 2025-12-11 04:31 UTC |
| **Total Duration** | ~5 hours |
| **Container VMID** | 110 |
| **Coral Inference Speed** | 7.8ms |
| **CPU Load Reduction** | 98% |
| **Cameras Working** | 2/3 |
| **Storage Available** | 2.3TB |
| **Old Recordings Preserved** | 88GB recordings + 1.1GB clips |

---

## Follow-Up Actions

- [x] Execute all phases
- [x] Create Frigate container
- [x] Configure Coral TPU
- [x] Verify performance improvement
- [x] Add storage passthrough (3TB ZFS)
- [x] Add real camera configuration
- [ ] Monitor container stability for 24 hours
- [ ] Fix old_ip_camera (MJPEG cam offline)
- [ ] Close GitHub issue #168

---

## Backups Created

| File | Purpose |
|------|---------|
| `proxmox/backups/still-fawn/lxc-110-pre-coral-20251210.conf` | LXC config before Coral setup |
| `proxmox/backups/still-fawn/frigate-config-pre-coral-20251210.yml` | Frigate config (OpenVINO) |
| `proxmox/backups/still-fawn/frigate-config-before-coral-20251210-194240.yml` | Frigate config before Coral switch |
| `proxmox/backups/still-fawn/lxc-110-before-storage-20251210-201650.conf` | LXC config before storage mount |
| `proxmox/backups/still-fawn/frigate-config-before-cameras-20251210-202005.yml` | Frigate config before cameras |

---

## Tags

frigate, coral, tpu, usb, proxmox, lxc, action-log, still-fawn, homelab, dfu-util, edgetpu
