# Blueprint: Frigate Coral USB TPU LXC Deployment

**Date**: December 2025
**GitHub Issue**: #168
**Hardware**: Coral USB Accelerator
**Target Hosts**: Proxmox VE nodes (still-fawn, fun-bedbug, etc.)

---

## Problem Statement

### Background
Coral USB TPU provides hardware-accelerated object detection for Frigate NVR, reducing inference time from ~100ms (CPU) to ~10ms. However, USB passthrough to LXC containers has several challenges:

1. **USB device numbers change** after reboot or re-enumeration
2. **Coral requires initialization** (switches from `1a6e:089a` to `18d1:9302`)
3. **"Did not claim interface 0" errors** occur without proper USB reset

### Solution
Use a **pre-start hookscript** to:
- Reset the USB device before container start
- Dynamically update the `dev0` path in LXC config
- Ensure consistent Coral TPU access

---

## Prerequisites

### Host Requirements
| Package | Purpose | Install Command |
|---------|---------|-----------------|
| `usbutils` | USB device detection | `apt install usbutils` |
| `jq` | JSON parsing (optional) | `apt install jq` |

### Hardware
- Coral USB Accelerator (v2 recommended)
- USB 3.0 port (for best performance)
- **External Storage for Recordings** (recommended 1TB+ HDD/SSD)
  - Frigate recordings can consume 50-100GB+ per camera per week
  - Mount point: `/media/frigate` inside container
  - Must be passed through to LXC container

### Software
- Proxmox VE 7.x or newer
- PVE Helper Scripts (for Frigate container creation)

### Host GPU Requirement (CRITICAL)

**The PVE Helper Script `frigate-install.sh` ALWAYS attempts hardware acceleration setup for privileged containers.**

Lines 37-43 of `install/frigate-install.sh`:
```bash
msg_info "Setting Up Hardware Acceleration"
$STD apt-get -y install {va-driver-all,ocl-icd-libopencl1,intel-opencl-icd,vainfo,intel-gpu-tools}
if [[ "$CTTYPE" == "0" ]]; then
  chgrp video /dev/dri      # <-- FAILS if /dev/dri doesn't exist
  chmod 755 /dev/dri
  chmod 660 /dev/dri/*
fi
```

**This is NOT controlled by `var_gpu` wizard option.** It runs unconditionally for privileged containers.

#### If Host Has No `/dev/dri`:
The install will fail with:
```
chgrp: cannot access '/dev/dri': No such file or directory
exit code 39
```

#### Common Causes of Missing `/dev/dri`:
1. **GPU driver blacklisted** (check `/etc/modprobe.d/*.conf` for `blacklist amdgpu` or `blacklist radeon`)
2. **GPU passed through to VM** (bound to vfio-pci)
3. **No GPU installed**

#### Solutions:

**Option A: Enable GPU on Host (Recommended)**
```bash
# Check for blacklist
grep -r "blacklist.*amdgpu\|blacklist.*radeon" /etc/modprobe.d/

# Remove blacklist entries, then:
update-initramfs -u
reboot
# Verify: ls -la /dev/dri/
```

**Option B: Use Unprivileged Container**
Set `var_unprivileged=1` - skips the hardware acceleration block, but **USB passthrough won't work**.

**Option C: Pre-create /dev/dri (Workaround)**
```bash
# On host before install:
mkdir -p /dev/dri
# Install will succeed but VAAPI won't actually work
```

---

## Script Directory

All scripts in `scripts/frigate-coral-lxc/`:

| Script | Purpose |
|--------|---------|
| `config.env` | Configuration (PVE_HOST, VMID, USB paths) |
| `01-check-prerequisites.sh` | Verify host packages |
| `02-verify-coral-usb.sh` | Confirm Coral USB detection |
| `03-find-sysfs-path.sh` | Find sysfs path for hookscript |
| `04-check-udev-rules.sh` | Check udev rules exist |
| `04a-check-dev-dri.sh` | **CRITICAL**: Verify /dev/dri exists on host |
| `05a-install-dfu-util.sh` | Install dfu-util package |
| `05b-download-firmware.sh` | Download Coral firmware to /usr/local/lib/firmware/ |
| `05c-create-udev-rules.sh` | Create udev rules WITH dfu-util firmware loading |
| `06-reload-udev.sh` | Reload udev rules and trigger firmware load |
| `10-stop-container.sh` | Stop container for config |
| `11-add-usb-passthrough.sh` | Add dev0 line to config |
| `12-add-cgroup-permissions.sh` | Add cgroup USB permissions |
| `13-add-vaapi-passthrough.sh` | Add GPU passthrough (optional) |
| `20-create-hookscript.sh` | Deploy hookscript to host |
| `21-attach-hookscript.sh` | Attach hookscript to container |
| `30-start-container.sh` | Start container |
| `31-verify-hookscript.sh` | Verify hookscript execution |
| `32-verify-frigate-api.sh` | Verify Frigate API |
| `33-verify-coral-detection.sh` | Verify Coral inference speed |
| `34-verify-usb-in-container.sh` | Verify USB in container |
| `40-update-frigate-config.sh` | Update Frigate config for Coral (backs up first) |
| `41-restart-frigate.sh` | Restart Frigate service |
| `42-configure-cameras.sh` | Apply camera configuration from backup/template |
| `43-verify-cameras.sh` | Verify cameras streaming and detecting |
| `44-add-storage-mount.sh` | Add external storage passthrough to LXC |
| `45-verify-storage.sh` | Verify storage mounted and writable |
| `90-rollback-full.sh` | Full rollback |
| `hookscript-template.sh` | Hookscript template |
| `camera-config-template.yml` | Template for camera configuration |

---

## Execution Plan

### Phase 0: Setup
1. Create GitHub issue
2. Update `config.env` with target host

### Phase 1: Pre-Flight
1. Run `01-check-prerequisites.sh`
2. Run `02-verify-coral-usb.sh`
3. Run `03-find-sysfs-path.sh`
4. Run `04-check-udev-rules.sh`
5. Run `04a-check-dev-dri.sh` **(BLOCKING - install fails without /dev/dri)**

### Phase 1.5: Fix /dev/dri (if missing)
If `/dev/dri` doesn't exist:
1. Check for GPU driver blacklist: `grep -r "blacklist.*amdgpu\|blacklist.*radeon" /etc/modprobe.d/`
2. Remove blacklist entries from config files
3. Run `update-initramfs -u`
4. Reboot host
5. Verify: `ls -la /dev/dri/`

### Phase 2: Coral Firmware & Udev Rules (CRITICAL)

**Reference**: `docs/source/md/coral-tpu-automation-runbook.md` - Complete Fresh Setup section

The Coral USB requires firmware loading via `dfu-util` when detected in bootloader mode (`1a6e:089a`).
This is triggered by a udev rule that runs on device detection.

1. Run `05a-install-dfu-util.sh` - Install dfu-util package
2. Run `05b-download-firmware.sh` - Download firmware from Google's libedgetpu repo
3. Run `05c-create-udev-rules.sh` - Create udev rules WITH firmware loading
4. Run `06-reload-udev.sh` - Reload rules and trigger (Coral should switch to `18d1:9302`)

**Manual verification**:
```bash
# Before: Coral in bootloader mode
lsusb | grep "1a6e:089a"  # Global Unichip Corp

# After firmware load: Coral initialized
lsusb | grep "18d1:9302"  # Google Inc
```

**Files created**:
- `/usr/bin/dfu-util` - Firmware loading utility
- `/usr/local/lib/firmware/apex_latest_single_ep.bin` - EdgeTPU firmware (~10KB)
- `/etc/udev/rules.d/95-coral-init.rules` - udev rule with `RUN+=` for auto-init

### Phase 3: Container Creation
1. SSH to host and run PVE Helper Script interactively
2. Note assigned VMID
3. Update `config.env` with VMID
4. Run `10-stop-container.sh`

### Phase 4: USB Passthrough
1. Run `11-add-usb-passthrough.sh`
2. Run `12-add-cgroup-permissions.sh`

### Phase 5: VAAPI (Optional)
1. Run `13-add-vaapi-passthrough.sh`

### Phase 6: Hookscript
1. Run `20-create-hookscript.sh`
2. Run `21-attach-hookscript.sh`

### Phase 7: Initial Verification
1. Run `30-start-container.sh`
2. Run `31-verify-hookscript.sh`
3. Run `34-verify-usb-in-container.sh`

### Phase 8: Frigate Configuration
1. Run `40-update-frigate-config.sh` - Updates config.yml for Coral (backs up first)
2. Run `41-restart-frigate.sh` - Restarts Frigate service

### Phase 9: Coral Verification
1. Run `32-verify-frigate-api.sh`
2. Run `33-verify-coral-detection.sh` - Verify inference speed < 20ms

### Phase 10: Storage Passthrough (For Recordings)

**Required for production use** - Frigate needs storage for recordings.

**Manual step (user must do):**
1. Physically connect external HDD to host
2. Mount on host: `mount /dev/sdX1 /mnt/frigate-storage`
3. Add to `/etc/fstab` for persistence

**Scripted steps:**
1. Run `44-add-storage-mount.sh` - Adds bind mount to LXC config
2. Run `45-verify-storage.sh` - Verifies storage accessible in container

**Storage Requirements:**
- Minimum: 500GB for basic retention
- Recommended: 1-3TB for multiple cameras with week+ retention
- Path in container: `/media/frigate`

**Migrating Old Recordings (if applicable):**
If migrating from a previous Frigate instance (e.g., ZFS subvolume with old LXC disk):
1. Identify old recordings location: `zfs list` to find old subvolumes
2. Old Frigate data typically at: `<pool>/subvol-<old-vmid>-disk-0/frigate/`
3. Update mount to point directly to frigate folder:
   ```
   mp0: /pool/subvol-xxx-disk-0/frigate,mp=/media/frigate
   ```
4. This preserves: recordings/, clips/, exports/, and test videos
5. Restart container to apply mount change

### Phase 11: Camera Configuration (THE GOAL)

**This is the critical phase** - Frigate is useless without cameras.

1. Run `42-configure-cameras.sh` - Applies camera config (backs up first)
2. Run `41-restart-frigate.sh` - Restart Frigate to load cameras
3. Run `43-verify-cameras.sh` - Verify all cameras streaming and detecting

**Camera Config Sources:**
- Existing backup: `proxmox/backups/frigate-app-config.yml`
- Previous Frigate instance (fun-bedbug LXC 113)
- User-provided RTSP URLs

**Required Camera Information:**
- RTSP URL (or HTTP for MJPEG)
- Resolution (width x height)
- Credentials (user:password)
- Objects to track (person, car, etc.)

### Phase 12: Final Verification
1. Verify all cameras visible in Frigate UI
2. Verify object detection working (person/car detections appearing)
3. Verify recordings being saved to external storage
4. Verify MQTT events (if Home Assistant integration)

---

## Hookscript Details

### Location
`/var/lib/vz/snippets/coral-lxc-hook-<VMID>.sh`

### Features
1. **Coral Detection**: Searches `/sys/bus/usb/devices/` for vendor IDs `1a6e` or `18d1`
2. **USB Reset**: Unbinds and rebinds USB device to refresh state
3. **Config Update**: Updates `dev0` path in LXC config with current device number
4. **Logging**: All actions logged to syslog with tag `coral-hook-<VMID>`

### Execution
Runs automatically on `pre-start` phase when container starts.

---

## Success Criteria

| Criterion | Verification |
|-----------|--------------|
| Container starts | `pct status <VMID>` shows running |
| Hookscript executes | `journalctl -t coral-hook-<VMID>` shows logs |
| Coral detected | Inference speed 8-15ms in `/api/stats` |
| USB visible | `lsusb` inside container shows Google device |
| No restart loops | Container stable for 10+ minutes |

---

## Rollback

### Partial Rollback (config only)
```bash
# Remove hookscript line from config
ssh root@<HOST> "sed -i '/^hookscript:/d' /etc/pve/lxc/<VMID>.conf"
```

### Full Rollback
Run `90-rollback-full.sh` to:
1. Stop and destroy container
2. Remove hookscript file
3. Optionally remove udev rules

---

## Troubleshooting

### Coral Not Detected
1. Check `lsusb` on host - device should show
2. Verify udev rules with `ls -la /dev/bus/usb/<BUS>/<DEV>`
3. Try unplugging and replugging Coral USB

### Hookscript Not Running
1. Check hookscript attached: `grep hookscript /etc/pve/lxc/<VMID>.conf`
2. Check script exists: `ls /var/lib/vz/snippets/coral-lxc-hook-<VMID>.sh`
3. Check script permissions: should be executable

### "Did Not Claim Interface 0"
1. USB reset should fix this
2. If persists, physical unplug/replug required
3. NEVER run Coral tests on host while container is using it

---

## References

- [Coral USB Get Started](https://coral.ai/docs/accelerator/get-started/)
- [Frigate Object Detectors](https://docs.frigate.video/configuration/object_detectors/#single-usb-coral)
- [Proxmox USB Passthrough](https://forum.proxmox.com/threads/passthrough-usb-device-to-lxc-keeping-the-path-dev-bus-usb-00x-00y.127774/)

---

## Tags

frigate, coral, tpu, usb, proxmox, lxc, hookscript, passthrough, homelab
