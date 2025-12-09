# Coral M.2 A+E PCIe Installation Guide for pumped-piglet

**Date**: December 2025
**Status**: Pending hardware (adapter on order)
**Target Host**: pumped-piglet (ThinkStation P520)

## Overview

This guide documents installing a Google Coral M.2 A+E Key TPU accelerator (Model UA1) on pumped-piglet using a GLOTRENDS WA01 M.2 E-Key to PCIe x1 adapter.

## Hardware

| Component | Details |
|-----------|---------|
| **Host** | pumped-piglet (Lenovo ThinkStation P520) |
| **Proxmox** | 8.4.14 |
| **Kernel** | 6.8.12-15-pve |
| **Coral Model** | M.2 A+E Key (Model UA1) - Single Edge TPU |
| **Adapter** | [GLOTRENDS WA01](https://www.amazon.com/GLOTRENDS-M-2-Key-PCIe-Bluetooth/dp/B09ZDPP43X) M.2 E-Key to PCIe x1 |
| **Target Slot** | PCIe Slot 6 (x4 half-height, open-ended) |

## Why PCIe Instead of USB?

- **Stability**: PCIe passthrough more reliable than USB passthrough
- **Thermal**: PCIe version has built-in thermal throttling (USB omits this)
- **Performance**: ~7ms inference (PCIe) vs ~12ms (USB)

---

## Step 1: Physical Installation

1. Power off pumped-piglet completely
2. Insert Coral M.2 A+E module into GLOTRENDS WA01 adapter
3. Install adapter in PCIe Slot 6 (half-height x4 slot)
4. Power on

---

## Step 2: Verify Hardware Detection

```bash
# SSH to pumped-piglet
ssh root@pumped-piglet.maas

# Check if Coral is detected (vendor 1ac1, device 089a)
lspci -nn | grep 089a
# Expected output:
# XX:00.0 System peripheral [0880]: Global Unichip Corp. Coral Edge TPU [1ac1:089a]

# Get the PCIe address for later
lspci -nn | grep 089a | awk '{print $1}'
```

---

## Step 3: Install Dependencies

```bash
apt update
apt install -y git devscripts dh-dkms dkms pve-headers-$(uname -r)
```

---

## Step 4: Build gasket-dkms from KyleGospo Fork

The standard Google gasket-dkms package doesn't work with kernel 6.8+. Use the KyleGospo fork which has the necessary fixes.

```bash
# Remove any existing gasket-dkms
apt remove gasket-dkms -y 2>/dev/null || true

# Clone the working fork for kernel 6.8+
cd /tmp
git clone https://github.com/KyleGospo/gasket-dkms
cd gasket-dkms
debuild -us -uc -tc -b
cd ..
dpkg -i gasket-dkms_1.0-18_all.deb

# Prevent accidental downgrades during apt upgrade
apt-mark hold gasket-dkms
```

---

## Step 5: Configure udev Rules

```bash
# Create apex group and udev rule
groupadd apex 2>/dev/null || true
echo 'SUBSYSTEM=="apex", MODE="0660", GROUP="apex"' > /etc/udev/rules.d/65-apex.rules
udevadm control --reload-rules
udevadm trigger
```

---

## Step 6: Load Module and Verify

```bash
# Load the apex module
modprobe apex

# Verify device exists
ls -la /dev/apex_0
# Expected: crw-rw---- 1 root apex 120, 0 ... /dev/apex_0

# Check dmesg for any errors
dmesg | grep -i apex

# Note: "signature and/or required key missing - tainting kernel" is NORMAL
# when Secure Boot is disabled
```

---

## Step 7: Make Module Load Persistent

```bash
# Ensure apex module loads on boot
echo "apex" >> /etc/modules-load.d/coral.conf
```

---

## Step 8: Configure for LXC Passthrough (Frigate)

Edit the LXC container configuration:

```bash
# Replace <CTID> with your container ID
nano /etc/pve/lxc/<CTID>.conf
```

Add these lines:

```
# Coral TPU passthrough
lxc.cgroup2.devices.allow: c 120:* rwm
lxc.mount.entry: /dev/apex_0 dev/apex_0 none bind,optional,create=file
```

Restart the container:

```bash
pct restart <CTID>
```

---

## Step 9: Inside LXC Container - Install Coral Runtime

```bash
# Enter container
pct enter <CTID>

# Add Coral repository
echo "deb https://packages.cloud.google.com/apt coral-edgetpu-stable main" | \
  tee /etc/apt/sources.list.d/coral-edgetpu.list
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -
apt update

# Install standard EdgeTPU runtime
apt install -y libedgetpu1-std

# Verify device is accessible
ls -la /dev/apex_0
```

---

## Step 10: Frigate Configuration

Update your Frigate `config.yaml`:

```yaml
detectors:
  coral:
    type: edgetpu
    device: pci
```

Restart Frigate and check the logs for detector initialization.

---

## Alternative: VM Passthrough (Instead of LXC)

If you prefer running Frigate in a VM instead of LXC:

### Enable IOMMU

Edit GRUB:

```bash
nano /etc/default/grub
```

Set:

```
GRUB_CMDLINE_LINUX_DEFAULT="quiet intel_iommu=on iommu=pt"
```

Update and add modules:

```bash
update-grub

cat >> /etc/modules << 'EOF'
vfio
vfio_iommu_type1
vfio_pci
EOF
```

### Blacklist apex driver on host (for VM passthrough only)

```bash
echo "blacklist apex" > /etc/modprobe.d/coral-blacklist.conf
echo "options vfio-pci ids=1ac1:089a" >> /etc/modprobe.d/coral-blacklist.conf
update-initramfs -u -k all
reboot
```

### Add to VM

```bash
# Get PCIe address
lspci -nn | grep 089a
# Example output: 03:00.0

# Add to VM (replace VMID and address)
qm set <VMID> -hostpci0 03:00.0
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `lspci` shows nothing | Check physical seating of adapter in PCIe slot |
| `/dev/apex_0` missing | Run `modprobe apex` and check `dmesg \| grep apex` |
| "signature missing" in dmesg | Normal behavior when Secure Boot is disabled |
| Module build fails | Ensure `pve-headers-$(uname -r)` matches running kernel |
| "Unable to change power state from D3cold" | Install gasket driver on host, even for VM passthrough |
| LXC can't see device | Verify cgroup2 line in container config, restart container |

---

## Kernel Upgrade Warning

After a Proxmox kernel upgrade, you may need to rebuild gasket-dkms:

```bash
# Install headers for new kernel
apt install pve-headers-$(uname -r)

# Rebuild
cd /tmp/gasket-dkms
debuild -us -uc -tc -b
cd ..
dpkg -i gasket-dkms_1.0-18_all.deb

reboot
```

---

## References

- [Proxmox Forum: PCIe Coral gasket-dkms issues](https://forum.proxmox.com/threads/pcie-coral-gasket-dkms-does-not-work.155827/)
- [KyleGospo gasket-dkms fork](https://github.com/KyleGospo/gasket-dkms) (kernel 6.8+ compatible)
- [Proxmox Forum: PCIe Google Coral Install Instructions](https://forum.proxmox.com/threads/pcie-google-coral-install-instructions.143187/)
- [GLOTRENDS WA01 Amazon](https://www.amazon.com/GLOTRENDS-M-2-Key-PCIe-Bluetooth/dp/B09ZDPP43X)
- [Frigate Dual TPU Discussion](https://github.com/blakeblackshear/frigate/discussions/988)

---

## Tags

coral, coral-tpu, edge-tpu, google-coral, m2-accelerator, pcie, proxmox, frigate, gasket-dkms, pumped-piglet, thinkstation-p520, machine-learning, object-detection
