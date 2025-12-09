# Coral TPU Automation System - Operations Runbook

This runbook provides procedures for maintaining, updating, and troubleshooting the Coral TPU automation system.

## 🔍 System Overview

The Coral TPU automation system eliminates manual initialization after system restarts using two mechanisms:

1. **udev rule** - Automatically loads firmware when Coral USB is detected in bootloader mode
2. **LXC hookscript** - Updates container device path before container starts

### How It Works

```
Boot / USB plug-in
    ↓
Coral appears as 1a6e:089a (Global Unichip - bootloader mode)
    ↓
udev rule triggers dfu-util → loads firmware (apex_latest_single_ep.bin)
    ↓
Device re-enumerates as 18d1:9302 (Google Inc - ready)
    ↓
Container start requested (manual or onboot)
    ↓
LXC hookscript (pre-start) → updates dev0 path if device moved
    ↓
Container starts with correct device path
    ↓
Frigate works with Coral TPU
```

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **dfu-util** | `/usr/bin/dfu-util` | Loads firmware into Coral USB |
| **Firmware** | `/usr/local/lib/firmware/apex_latest_single_ep.bin` | EdgeTPU runtime (~10KB) |
| **udev rule** | `/etc/udev/rules.d/95-coral-init.rules` | Triggers firmware load on device detection |
| **LXC hookscript** | `/var/lib/vz/snippets/coral-lxc-hook.sh` | Updates container config before start |

### Legacy System (Disabled)

The old Python-based systemd service (`coral-tpu-init.service`) is disabled but preserved as fallback. It required pycoral, numpy, and model files to run inference for initialization - fragile and slow.

## 📊 Health Check Procedures

### Quick Status Check

```bash
# Check Coral USB state
lsusb | grep -E "(18d1:9302|1a6e:089a)"
# Expected: "ID 18d1:9302 Google Inc." (initialized)

# Check LXC container configuration
pct config 113 | grep -E "(dev0|hookscript)"
# Expected: dev0 pointing to correct USB device path
# Expected: hookscript: local:snippets/coral-lxc-hook.sh

# Check container status
pct status 113
```

### Verify udev Rule

```bash
# Check rule exists
cat /etc/udev/rules.d/95-coral-init.rules

# Check dfu-util is installed
which dfu-util
dfu-util --version

# Check firmware exists
ls -la /usr/local/lib/firmware/apex_latest_single_ep.bin
```

### Verify Hookscript

```bash
# Check hookscript exists and is executable
ls -la /var/lib/vz/snippets/coral-lxc-hook.sh

# Check it's attached to container
grep hookscript /etc/pve/lxc/113.conf

# View recent hookscript logs
journalctl -t coral-hook --no-pager -n 20
```

### Hardware Verification

```bash
# Check Coral device accessibility on host
CORAL=$(lsusb | grep "18d1:9302" | sed 's/Bus \([0-9]*\) Device \([0-9]*\).*/\1 \2/')
BUS=$(echo $CORAL | cut -d' ' -f1)
DEV=$(echo $CORAL | cut -d' ' -f2)
ls -l /dev/bus/usb/$BUS/$DEV

# Verify container can access device (when running)
pct exec 113 -- lsusb | grep Google

# Test Coral inference (optional - only if Frigate not using)
pct exec 113 -- python3 -c "from pycoral.utils import edgetpu; print('TPU available:', len(edgetpu.list_edge_tpus()) > 0)"
```

## 🚨 Troubleshooting Guide

### Issue: Coral Stuck in Bootloader Mode (1a6e:089a)

The device didn't get initialized by the udev rule.

```bash
# Check current state
lsusb | grep -E "(18d1|1a6e)"

# Manual initialization with dfu-util
dfu-util -D /usr/local/lib/firmware/apex_latest_single_ep.bin -d '1a6e:089a' -R

# Wait 2 seconds, then verify
sleep 2
lsusb | grep "18d1:9302"

# Check if udev rule is loaded
udevadm control --reload-rules

# Check dmesg for USB errors
dmesg | tail -30 | grep -i usb
```

### Issue: Coral Not Working After Extended Use

If Coral stops responding or enters a bad state, the simplest fix is a USB replug:

1. **Physical replug** - Unplug and replug the Coral USB device
2. **udev rule triggers automatically** - Device initializes via dfu-util
3. **Verify** - `lsusb | grep "18d1:9302"` should show Google Inc

This is faster than rebooting and works because:
- USB replug triggers the udev `add` action
- dfu-util loads firmware into Coral's volatile memory
- Device re-enumerates as `18d1:9302` (ready state)

### Issue: Container Cannot Access Coral

```bash
# Check current dev0 in config
grep dev0 /etc/pve/lxc/113.conf

# Find actual device path
lsusb | grep "18d1:9302"
# Note the Bus and Device numbers

# Manually update config if needed
# Edit /etc/pve/lxc/113.conf and set dev0 to correct path
# Example: dev0: /dev/bus/usb/003/011

# Restart container
pct stop 113 && pct start 113
```

### Issue: Hookscript Not Running

```bash
# Verify hookscript is attached
pct config 113 | grep hookscript

# If missing, attach it
pct set 113 --hookscript local:snippets/coral-lxc-hook.sh

# Check hookscript permissions
ls -la /var/lib/vz/snippets/coral-lxc-hook.sh
# Should be: -rwxr-xr-x

# Fix permissions if needed
chmod +x /var/lib/vz/snippets/coral-lxc-hook.sh

# Test hookscript manually (dry run - just check output)
/var/lib/vz/snippets/coral-lxc-hook.sh 113 pre-start
```

### Issue: Hookscript Fails

```bash
# Check logs
journalctl -t coral-hook --no-pager

# Common causes:
# 1. Coral not initialized yet (udev rule didn't run)
# 2. Permission issues with /etc/pve/lxc/113.conf
# 3. Syntax error in hookscript
```

### Issue: Device Path Changes After Reboot

This is normal - USB device numbers can change. The hookscript handles this automatically. If it's not working:

```bash
# Check what path Coral is at now
lsusb | grep "18d1:9302"

# Check what config has
grep dev0 /etc/pve/lxc/113.conf

# Manually trigger hookscript logic
/var/lib/vz/snippets/coral-lxc-hook.sh 113 pre-start

# Verify config was updated
grep dev0 /etc/pve/lxc/113.conf
```

## 🔧 Emergency Procedures

### Manual Coral Initialization (No dfu-util)

If dfu-util approach fails, fall back to Python method:

```bash
# This is the OLD method - only use in emergency
cd /root/code/coral/pycoral/examples
python3 classify_image.py \
  --model ../test_data/mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite \
  --labels ../test_data/inat_bird_labels.txt \
  --input ../test_data/parrot.jpg
```

### Re-enable Legacy Systemd Service

If udev/hookscript approach completely fails:

```bash
# Re-enable old service
systemctl enable coral-tpu-init.service
systemctl start coral-tpu-init.service

# Check status
systemctl status coral-tpu-init.service
```

### Complete Fresh Setup

If everything is broken, reinstall the automation:

```bash
# 1. Install dfu-util
apt install dfu-util

# 2. Download firmware
mkdir -p /usr/local/lib/firmware
wget -O /usr/local/lib/firmware/apex_latest_single_ep.bin \
  'https://github.com/google-coral/libedgetpu/raw/master/driver/usb/apex_latest_single_ep.bin'

# 3. Create udev rule
cat > /etc/udev/rules.d/95-coral-init.rules << 'EOF'
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="1a6e", ATTR{idProduct}=="089a", RUN+="/usr/bin/dfu-util -D /usr/local/lib/firmware/apex_latest_single_ep.bin -d 1a6e:089a -R"
EOF
udevadm control --reload-rules

# 4. Create hookscript (see full script in repository)
# Location: /var/lib/vz/snippets/coral-lxc-hook.sh

# 5. Attach hookscript
pct set 113 --hookscript local:snippets/coral-lxc-hook.sh
```

## 📚 Reference

### USB Device IDs

| State | Vendor:Product | Description |
|-------|----------------|-------------|
| Bootloader | `1a6e:089a` | Global Unichip Corp - needs firmware |
| Initialized | `18d1:9302` | Google Inc - ready to use |

### Key Files

```
/etc/udev/rules.d/95-coral-init.rules     # udev rule for auto-init
/usr/local/lib/firmware/apex_latest_single_ep.bin  # EdgeTPU firmware
/var/lib/vz/snippets/coral-lxc-hook.sh    # LXC pre-start hookscript
/etc/pve/lxc/113.conf                     # Frigate container config
```

### Log Locations

```bash
# Hookscript logs
journalctl -t coral-hook

# udev/USB events
dmesg | grep -i usb
journalctl -k | grep -i coral

# Legacy service logs (if re-enabled)
journalctl -u coral-tpu-init.service
```

### Quick Commands

```bash
# Check Coral state
lsusb | grep -E "(18d1|1a6e)"

# Manual init with dfu-util
dfu-util -D /usr/local/lib/firmware/apex_latest_single_ep.bin -d '1a6e:089a' -R

# Check container config
pct config 113 | grep -E "(dev0|hookscript|cgroup)"

# View hookscript logs
journalctl -t coral-hook --no-pager -n 20

# Test hookscript
/var/lib/vz/snippets/coral-lxc-hook.sh 113 pre-start
```

## Tags

coral, coral-tpu, edge-tpu, google-coral, usb-accelerator, frigate, proxmox, lxc, udev, dfu-util, hookscript, fun-bedbug
