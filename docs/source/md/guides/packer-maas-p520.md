# Packer-MAAS build notes — ThinkStation P520 (Intel Xeon / UEFI + Secure Boot)

These are the **exact commands, edits, and error lines** encountered while
building a Proxmox-ready Debian 12 cloud-image with
[canonical/packer-maas](https://github.com/canonical/packer-maas) and importing
it into Ubuntu MAAS for ThinkStation P520 (Intel Xeon W-2123) with UEFI and Secure Boot enabled.

---

## 1  The Curtin error that started it all

```text

grub-install.real: warning: this GPT partition label contains no BIOS Boot Partition; embedding wont be possible.
grub-install.real: warning: Embedding is not possible.  GRUB can only be installed in this setup by using blocklists.
grub-install.real: error: will not proceed with blocklists.
dpkg: error processing package grub-cloud-amd64 (--configure):
installed grub-cloud-amd64 package post-installation script subprocess returned error exit status 1
E: Sub-process /usr/bin/dpkg returned an error code (1)

```

Curtin aborted, the P520 rebooted, and MAAS marked the node **Failed deployment**.

**Root Cause**: The P520 was configured for **UEFI + Secure Boot** only (no CSM/legacy mode).
The `grub-cloud-amd64` package attempts to install BIOS GRUB, which fails on UEFI-only systems.

---

## 2  Hardware Configuration

**Machine**: Lenovo ThinkStation P520
- **CPU**: Intel Xeon W-2123 (4-core, 8-thread)
- **RAM**: 32GB ECC DDR4
- **Boot Mode**: UEFI + Secure Boot (CSM disabled)
- **Target**: Proxmox VE deployment via MAAS

**BIOS Settings**:
- Secure Boot: **Enabled**
- CSM Support: **Disabled** (UEFI only)
- Boot Order: PXE IPv4 first, then SSD

Unlike the AMD MA90, this machine does **not** have boot order persistence issues.

---

## 3  Changes made inside the packer repo

### `debian/Makefile` (excerpts)

```Makefile

PACKER\_LOG = 1          # verbose
SERIES      = bookworm  # always build Debian 12
disk\_size   = "16G"     # avoid space issues
-var customize\_script=my-intel-xeon-p520-changes.sh

```

### `my-intel-xeon-p520-changes.sh`

```bash
#!/bin/bash
set -e

echo "=== Starting Intel Xeon P520 customization script ==="

# Install basic dependencies
apt-get install -y gnupg lsb-release

# Proxmox repository (NO-SUBSCRIPTION)
echo "deb [arch=amd64] http://download.proxmox.com/debian/pve \
$(lsb_release -cs) pve-no-subscription" \
  > /etc/apt/sources.list.d/pve-install-repo.list

# Download Proxmox GPG key
wget https://enterprise.proxmox.com/debian/proxmox-release-$(lsb_release -cs).gpg \
     -O /etc/apt/trusted.gpg.d/proxmox-release.gpg

# Update and upgrade
apt-get update && apt full-upgrade -y

# Install Proxmox VE and dependencies
apt-get install -y proxmox-ve postfix open-iscsi chrony zfsutils-linux zfs-initramfs

# Remove default Debian kernel
apt-get remove -y linux-image-amd64 'linux-image-6.1*'

# ── CRITICAL FIX: UEFI-only GRUB for P520 ────────────────────────────────────
# Problem: grub-cloud-amd64 attempts BIOS installation, fails on UEFI-only systems
# Solution: Purge BIOS GRUB packages, install UEFI GRUB with Secure Boot support

# Step 1: Purge BIOS GRUB packages
echo "Purging grub-pc and grub-cloud-amd64..."
apt-get purge -y grub-pc grub-cloud-amd64

# Step 2: Prevent grub-cloud-amd64 from being reinstalled
echo "Diverting grub-cloud-amd64 to prevent reinstallation..."
dpkg-divert --package grub-cloud-amd64 --rename --divert /etc/grub.d/00_header.distrib /etc/grub.d/00_header

# Step 3: Install EFI-only GRUB with Secure Boot support
echo "Installing grub-efi-amd64 and shim-signed..."
apt-get install -y grub-efi-amd64 shim-signed

# Step 4: Ensure /boot/efi exists and is mounted
# (Packer should have created a 512 MiB FAT32 partition at /boot/efi)
mkdir -p /boot/efi
if ! mountpoint -q /boot/efi; then
    echo "Mounting /boot/efi..."
    mount /boot/efi
fi

# Step 5: Install GRUB into the ESP (EFI System Partition)
echo "Installing GRUB to EFI System Partition..."
grub-install \
  --target=x86_64-efi \
  --efi-directory=/boot/efi \
  --bootloader-id=Proxmox \
  --recheck

# Step 6: Generate GRUB configuration
echo "Generating GRUB configuration..."
update-grub

echo "=== Intel Xeon P520 customization complete ==="

```

**Key Differences from AMD MA90**:
- P520 uses `my-intel-xeon-p520-changes.sh` (NOT `my-amd-changes.sh`)
- Added `dpkg-divert` to **permanently prevent** grub-cloud-amd64 reinstallation
- Explicit check for `/boot/efi` mount point before grub-install
- UEFI Secure Boot compatible with `shim-signed`

---

## 4  Build + upload commands

### 4.1  Build on PVE host

```bash
# SSH to PVE build host
ssh root@pve.maas

# Navigate to packer repo
cd ~/code/packer-maas/debian/

# Clean previous builds
make clean

# Build (takes ~15-20 minutes)
make debian

# Verify output file
ls -lh debian-custom-cloudimg.tar.gz
# Expected: ~1.8GB (1,841,553,788 bytes)
```

### 4.2  Copy to MAAS with MD5 verification

**CRITICAL**: Always verify file integrity with MD5 checksums to prevent corruption.

```bash
# Step 1: Calculate MD5 on source
SOURCE_MD5=$(ssh root@pve.maas "md5sum ~/code/packer-maas/debian/debian-custom-cloudimg.tar.gz | awk '{print \$1}'")
echo "Source MD5: $SOURCE_MD5"

# Step 2: Transfer to MAAS server
ssh root@pve.maas "scp ~/code/packer-maas/debian/debian-custom-cloudimg.tar.gz gshiva@192.168.4.53:/home/gshiva/"

# Step 3: Verify MD5 on destination
DEST_MD5=$(ssh gshiva@192.168.4.53 "md5sum /home/gshiva/debian-custom-cloudimg.tar.gz | awk '{print \$1}'")
echo "Destination MD5: $DEST_MD5"

# Step 4: Compare checksums
if [ "$SOURCE_MD5" = "$DEST_MD5" ]; then
    echo "✓ MD5 checksums match - transfer successful"
else
    echo "✗ MD5 mismatch - transfer corrupted!"
    exit 1
fi
```

**Lesson Learned**: Initial transfer without verification resulted in 1.5GB corrupted file.
Always use MD5 verification for large files.

### 4.3  Upload to MAAS

```bash
# SSH to MAAS region controller
ssh gshiva@192.168.4.53

# Upload custom image
maas admin boot-resources create \
  name='custom/debian-12-intel-xeon-p520-amd64' \
  title='Debian 12 Intel Xeon P520 - Proxmox + UEFI GRUB' \
  architecture='amd64/generic' \
  filetype='tgz' \
  content@=debian-custom-cloudimg.tar.gz

# Verify upload
maas admin boot-resources read | jq '.[] | select(.name | contains("p520"))'
```

MAAS then listed the image under **Images → Custom** and deployments stopped
throwing the blocklist error.

---

## 5  Deployment commands

### 5.1  Deploy to P520 node

```bash
# Release machine if it's in "Failed deployment" state
maas admin machine release n4cmsn

# Deploy with custom image
maas admin machine deploy n4cmsn \
  distro_series=debian-12-intel-xeon-p520

# Monitor deployment status
maas admin machine read n4cmsn | jq '.status_name'
```

### 5.2  Verify deployment

```bash
# Wait for "Deployed" status, then test SSH
# Note: Default user for Debian cloud-init is "debian", not "ubuntu"
ssh debian@192.168.4.175

# Verify Proxmox installation
pveversion
# Expected: proxmox-ve: 8.4.0

# Verify kernel
uname -r
# Expected: 6.8.12-15-pve (Proxmox kernel)

# Verify GRUB installation (CRITICAL)
dpkg -l | grep grub
# Expected:
#   ii  grub-efi-amd64        2.06-13+pmx7
#   ii  grub-efi-amd64-signed 1+2.06+13+deb12u1
# Must NOT show: grub-cloud-amd64

# Verify EFI boot entry
efibootmgr
# Expected:
#   BootCurrent: 0017
#   Boot0017* debian
```

**Success Criteria**:
- ✅ SSH access works with `debian` user
- ✅ Proxmox VE 8.4.0 installed
- ✅ PVE kernel (6.8.12-15-pve) running
- ✅ grub-efi-amd64 present
- ✅ grub-cloud-amd64 **absent**
- ✅ EFI boot entry created

---

## 6  Next time checklist

1. **Build image** with `my-intel-xeon-p520-changes.sh` script
2. **Verify MD5** checksums during SCP transfer
3. **Upload to MAAS** with correct name and title
4. **Deploy** with `distro_series=debian-12-intel-xeon-p520`
5. **Verify** GRUB installation: grub-efi-amd64 only, NO grub-cloud-amd64
6. **Test SSH** with `debian` user (not `ubuntu`)

---

## 7  Common Issues and Solutions

### Issue 1: grub-cloud-amd64 gets reinstalled

**Symptom**: After deployment, `dpkg -l | grep grub` shows grub-cloud-amd64

**Solution**: Ensure `dpkg-divert` command is in the customization script:
```bash
dpkg-divert --package grub-cloud-amd64 --rename --divert /etc/grub.d/00_header.distrib /etc/grub.d/00_header
```

### Issue 2: SSH fails with "Permission denied"

**Symptom**: SSH with `ubuntu` user fails, even with correct keys

**Root Cause**: Debian cloud-init creates `debian` user, not `ubuntu`

**Solution**: Use `ssh debian@<ip>` instead of `ssh ubuntu@<ip>`

### Issue 3: File corruption during SCP

**Symptom**: MAAS deployment fails with tar extraction errors

**Root Cause**: 1.8GB file corrupted during transfer (only 1.5GB transferred)

**Solution**: Always use MD5 verification (see section 4.2)

### Issue 4: "Cannot deploy Failed deployment" state

**Symptom**: `maas admin machine deploy` fails with state error

**Solution**: Release machine first: `maas admin machine release <system_id>`

---

## 8  Comparison: AMD MA90 vs Intel P520

| Hardware | CPU | Script Name | Boot Mode | Special Quirks |
|----------|-----|-------------|-----------|----------------|
| ATOPNUC MA90 | AMD A9-9400 | `my-amd-changes.sh` | UEFI forced | Boot order resets every reboot |
| ThinkStation P520 | Intel Xeon W-2123 | `my-intel-xeon-p520-changes.sh` | UEFI + Secure Boot | No boot order issues |

**Key Similarity**: Both require UEFI-only GRUB (grub-efi-amd64, NOT grub-cloud-amd64)

**Key Difference**: P520 needs `dpkg-divert` to prevent grub-cloud-amd64 reinstallation

---

Last verified: MAAS 3.6 (stable) • October 2025

**Tags**: p520, intel-xeon, proxmox, maas, packer, uefi, secure-boot, grub, grub-efi-amd64, debian-12, bookworm
