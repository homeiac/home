# Frigate 0.16 LXC Upgrade - Instructions for Claude

## Goal
Manually install Frigate 0.16 in a new LXC container with Coral TPU support.

## Approach
Build pycoral binaries for Python 3.10+ (Debian 12 default). This is easier than making Frigate work on Python 3.9.

## DO NOT DO (Critical Mistakes That Wasted Time)

### 1. DO NOT run Docker with USB passthrough
```bash
# NEVER DO THIS - it claims USB and blocks LXC
docker run --device=/dev/bus/usb:/dev/bus/usb ...
```
Docker claims the USB exclusively. LXC gets "did not claim interface 0" errors.

### 2. DO NOT leave background tasks running
Check and kill everything before testing:
```bash
docker ps -a
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)
```

### 3. DO NOT set ANY Frigate container to autoboot during experimentation
```bash
# Disable autoboot on ALL Frigate containers first
pct set 113 --onboot 0  # production - disable before experimenting
pct set <new> --onboot 0  # experimental - NEVER enable during testing
```
Only ONE Frigate can use the Coral. Multiple autobooting = disaster.

### 4. DO NOT test Coral from host after assigning to LXC
Testing from host corrupts Coral state. Requires replug or reboot.

### 5. DO NOT install Docker on the Proxmox host for Frigate testing
Use LXC only. Docker on host interferes with LXC USB passthrough.

### 6. DO NOT try to make Frigate work on Python 3.9
Building Python 3.9 is intrusive. Build pycoral for 3.10+ instead.

## MUST DO (Correct Procedure)

### Before starting:
1. Stop LXC 113: `pct stop 113`
2. Disable its autoboot: `pct set 113 --onboot 0`
3. Verify Docker is stopped: `systemctl stop docker`
4. Verify no Docker containers: `docker ps -a` should be empty

### Create experimental LXC:
```bash
# Create with onboot=0
pct create <VMID> <template> --hostname frigate-016 --onboot 0 ...
```

### Build pycoral for Python 3.10+:
The official pycoral wheels only support Python 3.9. Need to build from source:
- Clone pycoral repo
- Build wheel for Python 3.10/3.11
- Install in container

### Configure USB passthrough:
1. Find Coral: `lsusb | grep -E '(Google|Global)'`
2. Run coral-tpu automation to get correct path
3. Add to config: `dev0: /dev/bus/usb/XXX/YYY`

### Only run ONE Frigate at a time:
- Stop 113 before starting experimental
- Stop experimental before starting 113
- NEVER have both running

### After USB issues:
1. Reboot host
2. Replug Coral USB
3. Run coral-tpu automation
4. Then start container

## Existing Helper Scripts (DO NOT REINVENT)

### Coral TPU Automation
**Repo location**: `proxmox/scripts/coral-automation/`
**Host location**: `/root/coral-automation/` (deployed to fun-bedbug.maas)

```bash
# Initialize Coral and configure LXC (run on Proxmox host)
cd /root/coral-automation && python3 scripts/coral_tpu_automation.py --container-id 113
```

Files:
- `scripts/coral_tpu_automation.py` - Main entry point
- `src/homelab/coral_detection.py` - Detect Coral USB state (Unichip/Google mode)
- `src/homelab/coral_initialization.py` - Initialize Coral from Unichip to Google mode
- `src/homelab/coral_config.py` - Update LXC config with correct USB path
- `src/homelab/coral_automation.py` - Orchestrates the full workflow

### Pycoral Source (`/root/code/coral/pycoral/` on host)
Can be used to build wheels for Python 3.10+:
- `scripts/build.sh` - Build pycoral
- `scripts/build_deb.sh` - Build deb package
- `setup.py` - Python package setup

## Technical Requirements for Frigate 0.16 LXC

### Python
- Use Debian 12 default Python 3.11
- Build pycoral from source for 3.11

### Coral TPU
- libedgetpu1-max in container
- pycoral built for Python 3.11
- tflite-runtime for Python 3.11
- USB passthrough via dev0

### VAAPI
- libva-drm2, mesa-va-drivers
- /dev/dri passthrough
- LIBVA_DRIVER_NAME=radeonsi

### LXC Config Requirements
```
dev0: /dev/bus/usb/XXX/YYY
lxc.cgroup2.devices.allow: a
lxc.cap.drop:
lxc.cgroup2.devices.allow: c 188:* rwm
lxc.cgroup2.devices.allow: c 189:* rwm
lxc.cgroup2.devices.allow: c 226:0 rwm
lxc.cgroup2.devices.allow: c 226:128 rwm
lxc.mount.entry: /dev/dri dev/dri none bind,optional,create=dir
```

## Coral TPU Critical Configuration (Version Independent)

### USB Device Path Changes After Replug

**CRITICAL**: The USB device number changes every time Coral is physically unplugged/replugged:

```bash
# Before replug: Bus 003 Device 004
# After replug:  Bus 003 Device 009 (NEW NUMBER!)

# Always check current device number
lsusb | grep -i google

# Update LXC config with new path
sed -i 's|dev0: /dev/bus/usb/003/.*|dev0: /dev/bus/usb/003/NEW_NUM|' /etc/pve/lxc/113.conf
pct stop 113 && pct start 113
```

### Use dev0: Passthrough (NOT Bind Mount)

**Working method**:
```
dev0: /dev/bus/usb/003/009
```

**Does NOT work** (permissions reset on container restart):
```
lxc.mount.entry: /dev/bus/usb dev/bus/usb none bind,optional,create=dir
```

The bind mount method doesn't preserve host udev permissions inside the container.

### USB Permissions Must Be 666

The host udev rules must set 666 permissions:
```bash
# /etc/udev/rules.d/98-coral.rules
SUBSYSTEMS=="usb", ATTRS{idVendor}=="18d1", ATTRS{idProduct}=="9302", MODE="0666", GROUP="plugdev"
```

Verify on host: `ls -la /dev/bus/usb/003/XXX` should show `crw-rw-rw-`

### Hardware Timeout = Physical Replug Required

Symptoms in dmesg:
```
xhci_hcd: Timeout while waiting for setup device command
usb 3-3: device not accepting address, error -62
```

**Only fix**: Physically unplug and replug the Coral USB device.

### pycoral Detection vs tflite Delegate Loading

These can have different results:
```bash
# This may succeed (reads sysfs):
python3 -c "from pycoral.utils.edgetpu import list_edge_tpus; print(list_edge_tpus())"
# Output: [{'type': 'usb', 'path': '/sys/bus/usb/devices/3-3'}]

# But this may fail (actually uses USB device):
python3 -c "from tflite_runtime.interpreter import load_delegate; load_delegate('libedgetpu.so.1')"
# ValueError: Failed to load delegate

# If detection works but loading fails → hardware issue → replug Coral
```

### Verify Coral Working in Frigate

```bash
# Check Frigate logs for TPU detection
pct exec 113 -- cat /dev/shm/logs/frigate/current | grep -i "TPU found"

# Check detector stats (should show inference_speed)
pct exec 113 -- curl -s http://127.0.0.1:5000/api/stats | jq '.detectors'
```

## Why LXC not VM
- Lower overhead on AMD A9-9400
- Direct USB passthrough works
- VAAPI works via lxc.mount.entry
- Simpler than VFIO/IOMMU for VM

## Reference Files

### On Proxmox Host (fun-bedbug.maas)
- Working LXC config: `/etc/pve/lxc/113.conf`
- Coral automation: `/root/coral-automation/scripts/coral_tpu_automation.py`
- Config backups: `/root/coral-backups/`

### In Repository
- LXC container config backup: `proxmox/backups/lxc-113-container-config.conf`
- Frigate app config backup: `proxmox/backups/frigate-app-config.yml`
- Backup restore procedures: `proxmox/backups/README.md`
- Coral TPU integration guide: `proxmox/guides/google-coral-tpu-frigate-integration.md`
- Coral automation runbook: `docs/source/md/coral-tpu-automation-runbook.md`
