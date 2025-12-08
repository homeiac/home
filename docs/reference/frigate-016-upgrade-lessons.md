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

## Why LXC not VM
- Lower overhead on AMD A9-9400
- Direct USB passthrough works
- VAAPI works via lxc.mount.entry
- Simpler than VFIO/IOMMU for VM

## Reference Files
- Working config: `/etc/pve/lxc/113.conf`
- Coral automation: `/root/coral-automation/scripts/coral_tpu_automation.py`
