# Blueprint: ThinkStation P520 GRUB Installation Fix

**Date**: October 19, 2025
**Hardware**: Lenovo ThinkStation P520 (Intel Xeon)
**Machine**: pumped-piglet.maas (192.168.4.175)
**Issue**: GRUB installation failure due to `grub-cloud-amd64` attempting BIOS installation on UEFI-only system

---

## Problem Statement

### Root Cause
The custom Debian image uses AMD-specific script (`my-amd-changes.sh`) which purges `grub-cloud-amd64` during Packer build. However, during MAAS deployment, curtin reinstalls dependencies that trigger `grub-cloud-amd64` post-install hook, which attempts BIOS/Legacy GRUB installation on a GPT disk without BIOS Boot Partition.

### Error Message
```
grub-install.real: warning: this GPT partition label contains no BIOS Boot Partition; embedding won't be possible.
grub-install.real: error: will not proceed with blocklists.
dpkg: error processing package grub-cloud-amd64 (--configure)
```

### Hardware Configuration
- **CPU**: Intel Xeon (NOT AMD)
- **Boot Mode**: UEFI with Secure Boot enabled
- **Current Image**: Debian 12 Bookworm with `my-amd-changes.sh` (incorrect for Intel)

---

## Detailed Execution Plan

### Phase 1: Pre-Flight Checks and Documentation Setup

#### Step 1.1: Create GitHub Issue
**Objective**: Track work with GitHub issue for commit references

**Actions**:
```bash
gh issue create \
  --title "Fix GRUB installation failure on Intel Xeon P520" \
  --body "ThinkStation P520 (pumped-piglet.maas) fails MAAS deployment with grub-cloud-amd64 BIOS boot error on UEFI-only system. Need to create Intel-specific Packer script to handle grub-cloud-amd64 properly."
```

**Expected Output**: Issue number (e.g., #123)

**Verification**:
```bash
gh issue list | grep "P520"
```

---

#### Step 1.2: Backup Current Scripts on PVE
**Objective**: Preserve working AMD configuration before modifications

**Actions**:
```bash
ssh root@pve.maas "cd ~/code/packer-maas/debian && \
  cp my-amd-changes.sh my-amd-changes.sh.backup-$(date +%Y%m%d) && \
  ls -la my-amd-changes.sh*"
```

**Expected Output**: Backup file created with timestamp

**Verification**:
```bash
ssh root@pve.maas "ls -la ~/code/packer-maas/debian/my-amd-changes.sh.backup-*"
```

---

#### Step 1.3: Check Current Makefile Configuration
**Objective**: Understand current build configuration

**Actions**:
```bash
ssh root@pve.maas "grep customize_script ~/code/packer-maas/debian/Makefile"
```

**Expected Output**:
```
-var customize_script=my-amd-changes.sh \
```

**Verification**: Confirm it points to AMD script

---

### Phase 2: Create Intel Xeon-Specific Script

#### Step 2.1: Create Intel Xeon Customization Script
**Objective**: Create P520-specific script that properly handles grub-cloud-amd64

**Script Name**: `my-intel-xeon-p520-changes.sh`

**Key Differences from AMD Script**:
1. **Prevent grub-cloud-amd64 post-install hook** from running BIOS installation
2. **Use dpkg-divert** to block problematic behavior
3. **Ensure only UEFI GRUB** is configured

**Actions**:
Create script on PVE at `~/code/packer-maas/debian/my-intel-xeon-p520-changes.sh`

**Script Content**:
```bash
#!/bin/bash
set -e

apt-get install -y gnupg lsb-release
DEBIAN_CODENAME=$(lsb_release -cs)

# Add Proxmox repository
echo "deb [arch=amd64] http://download.proxmox.com/debian/pve ${DEBIAN_CODENAME} pve-no-subscription" > /etc/apt/sources.list.d/pve-install-repo.list
wget https://enterprise.proxmox.com/debian/proxmox-release-bookworm.gpg -O /etc/apt/trusted.gpg.d/proxmox-release-bookworm.gpg

# Verify GPG key
sha512sum /etc/apt/trusted.gpg.d/proxmox-release-bookworm.gpg
echo "7da6fe34168adc6e479327ba517796d4702fa2f8b4f0a9833f5ea6e6b48f6507a6da403a274fe201595edc86a84463d50383d07f64bdde2e3658108db7d6dc87  /etc/apt/trusted.gpg.d/proxmox-release-bookworm.gpg" | sha512sum -c -

# Update and install Proxmox VE
apt-get update && apt full-upgrade -y
apt install -y proxmox-default-kernel
apt-get install -y proxmox-ve postfix open-iscsi chrony zfsutils-linux zfs-initramfs
apt remove -y linux-image-amd64 'linux-image-6.1*'

echo "deb http://ftp.debian.org/debian bookworm main contrib non-free non-free-firmware" >> /etc/apt/sources.list
apt update

# ═══════════════════════════════════════════════════════════════════════
# CRITICAL FIX: Prevent grub-cloud-amd64 from attempting BIOS installation
# ═══════════════════════════════════════════════════════════════════════

# 1) Divert grub-cloud-amd64 postinst to prevent BIOS grub-install
if [ -f /var/lib/dpkg/info/grub-cloud-amd64.postinst ]; then
    dpkg-divert --add --rename --divert /var/lib/dpkg/info/grub-cloud-amd64.postinst.disabled /var/lib/dpkg/info/grub-cloud-amd64.postinst
fi

# 2) Purge BIOS GRUB packages
DEBIAN_FRONTEND=noninteractive apt-get purge -y grub-pc grub-pc-bin || true

# 3) Install UEFI-only GRUB packages
apt-get install -y --no-install-recommends \
  console-setup \
  grub-efi-amd64 \
  grub-efi-amd64-bin \
  shim-signed

# 4) Ensure /boot/efi exists and is mounted
mkdir -p /boot/efi
if ! mountpoint -q /boot/efi; then
    mount /boot/efi || echo "Warning: /boot/efi not mounted, assuming handled by fstab"
fi

# 5) Install GRUB to EFI System Partition
grub-install \
  --target=x86_64-efi \
  --efi-directory=/boot/efi \
  --bootloader-id=Proxmox \
  --no-nvram \
  --recheck

# 6) Generate GRUB configuration
update-grub

# ═══════════════════════════════════════════════════════════════════════
# Cloud-init hosts template for MAAS
# ═══════════════════════════════════════════════════════════════════════
cat <<'EOF' > /etc/cloud/templates/hosts.debian.tmpl
## template:jinja
{#
This file (/etc/cloud/templates/hosts.debian.tmpl) is only utilized
if enabled in cloud-config.  Specifically, in order to enable it
you need to add the following to config:
   manage_etc_hosts: True
-#}
# Your system has configured 'manage_etc_hosts' as True.
# As a result, if you wish for changes to this file to persist
# then you will need to either
# a.) make changes to the master file in /etc/cloud/templates/hosts.debian.tmpl
# b.) change or remove the value of 'manage_etc_hosts' in
#     /etc/cloud/cloud.cfg or cloud-config from user-data
#
{# The value '{{hostname}}' will be replaced with the local-hostname -#}
{{public_ipv4}} {{fqdn}} {{hostname}}
# The following lines are desirable for IPv6 capable hosts
::1 localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
EOF

# ═══════════════════════════════════════════════════════════════════════
# Proxmox repository management
# ═══════════════════════════════════════════════════════════════════════

# Disable Proxmox Enterprise Repository
if [ -f /etc/apt/sources.list.d/pve-enterprise.list ]; then
    sed -i 's|^deb https://enterprise.proxmox.com/debian/pve|#&|' /etc/apt/sources.list.d/pve-enterprise.list
fi

# Verify Changes
grep -r "enterprise.proxmox.com" /etc/apt/sources.list* || echo "✓ Proxmox Enterprise repo disabled"

echo "✓ Intel Xeon P520 customization complete"
```

**Expected Output**: Script file created

**Verification**:
```bash
ssh root@pve.maas "test -f ~/code/packer-maas/debian/my-intel-xeon-p520-changes.sh && echo 'Script exists' || echo 'Script missing'"
ssh root@pve.maas "wc -l ~/code/packer-maas/debian/my-intel-xeon-p520-changes.sh"
```

---

#### Step 2.2: Make Script Executable
**Objective**: Ensure script has execute permissions

**Actions**:
```bash
ssh root@pve.maas "chmod +x ~/code/packer-maas/debian/my-intel-xeon-p520-changes.sh"
```

**Verification**:
```bash
ssh root@pve.maas "ls -la ~/code/packer-maas/debian/my-intel-xeon-p520-changes.sh | grep '^-rwxr-xr-x'"
```

---

#### Step 2.3: Update Makefile to Use Intel Script
**Objective**: Configure Packer to use Intel-specific script

**Actions**:
```bash
ssh root@pve.maas "cd ~/code/packer-maas/debian && \
  sed -i 's/customize_script=my-amd-changes.sh/customize_script=my-intel-xeon-p520-changes.sh/' Makefile"
```

**Expected Output**: Makefile modified

**Verification**:
```bash
ssh root@pve.maas "grep customize_script ~/code/packer-maas/debian/Makefile"
# Expected: -var customize_script=my-intel-xeon-p520-changes.sh \
```

---

### Phase 3: Build New Debian Image

#### Step 3.1: Clean Previous Build Artifacts
**Objective**: Remove old build artifacts to ensure clean build

**Actions**:
```bash
ssh root@pve.maas "cd ~/code/packer-maas/debian && make clean"
```

**Expected Output**:
```
rm -rf output-* debian-custom-*.gz seeds-cloudimg.iso
```

**Verification**:
```bash
ssh root@pve.maas "ls ~/code/packer-maas/debian/ | grep -E 'output-|debian-custom-.*\.gz'"
# Expected: No output (clean directory)
```

---

#### Step 3.2: Build Debian Image with Packer
**Objective**: Build new Debian 12 image with Intel customizations

**Actions**:
```bash
ssh root@pve.maas "cd ~/code/packer-maas/debian && nohup make debian > /tmp/packer-build.log 2>&1 &"
```

**Expected Duration**: 15-20 minutes

**Monitoring**:
```bash
# Monitor progress
ssh root@pve.maas "tail -f /tmp/packer-build.log"

# Check for completion
ssh root@pve.maas "ls -lh ~/code/packer-maas/debian/debian-custom-cloudimg.tar.gz"
```

**Verification**:
```bash
# Check build log for success
ssh root@pve.maas "grep -i 'build.*finished' /tmp/packer-build.log"

# Verify output file exists and size is reasonable (>100MB)
ssh root@pve.maas "ls -lh ~/code/packer-maas/debian/debian-custom-cloudimg.tar.gz | awk '{print \$5}'"
```

---

### Phase 4: Upload Image to MAAS

#### Step 4.1: Copy Image to MAAS Server with Integrity Verification
**Objective**: Transfer built image to MAAS region controller with checksum verification

**Actions**:
```bash
# Step 1: Calculate MD5 checksum on source (PVE)
SOURCE_MD5=$(ssh root@pve.maas "md5sum ~/code/packer-maas/debian/debian-custom-cloudimg.tar.gz | awk '{print \$1}'")
echo "Source MD5: $SOURCE_MD5"

# Step 2: Transfer file to MAAS server
ssh root@pve.maas "scp ~/code/packer-maas/debian/debian-custom-cloudimg.tar.gz gshiva@192.168.4.53:/home/gshiva/"

# Step 3: Verify MD5 checksum on destination (MAAS VM)
DEST_MD5=$(ssh gshiva@192.168.4.53 "md5sum /home/gshiva/debian-custom-cloudimg.tar.gz | awk '{print \$1}'")
echo "Destination MD5: $DEST_MD5"

# Step 4: Compare checksums
if [ "$SOURCE_MD5" = "$DEST_MD5" ]; then
    echo "✓ MD5 checksums match - transfer successful"
else
    echo "✗ MD5 mismatch - transfer corrupted!"
    echo "  Source:      $SOURCE_MD5"
    echo "  Destination: $DEST_MD5"
    exit 1
fi
```

**Expected Output**: "MD5 checksums match - transfer successful"

**Verification**:
```bash
# Verify file size as additional check
SOURCE_SIZE=$(ssh root@pve.maas "stat -c%s ~/code/packer-maas/debian/debian-custom-cloudimg.tar.gz")
DEST_SIZE=$(ssh gshiva@192.168.4.53 "stat -c%s /home/gshiva/debian-custom-cloudimg.tar.gz")
echo "Source size: $SOURCE_SIZE, Destination size: $DEST_SIZE"
test "$SOURCE_SIZE" -eq "$DEST_SIZE" && echo "✓ Sizes match" || echo "✗ Size mismatch!"
```

---

#### Step 4.2: Upload Image to MAAS
**Objective**: Register custom image in MAAS

**Image Name**: `custom/debian-12-intel-xeon`

**Actions**:
```bash
ssh -J root@pve.maas root@192.168.4.19 "maas admin boot-resources create \
  name='custom/debian-12-intel-xeon' \
  title='Proxmox Bookworm Intel Xeon' \
  architecture='amd64/generic' \
  filetype='tgz' \
  content@=/tmp/debian-custom-cloudimg.tar.gz"
```

**Expected Output**: JSON response with resource ID

**Verification**:
```bash
ssh -J root@pve.maas root@192.168.4.19 "maas admin boot-resources read | jq '.[] | select(.name | contains(\"intel-xeon\"))'"
```

---

### Phase 5: Deploy to ThinkStation P520

#### Step 5.1: Release Current Machine
**Objective**: Return pumped-piglet.maas to Ready state

**Actions** (via MAAS UI):
1. Navigate to http://192.168.4.53:5240/MAAS
2. Find machine `pumped-piglet.maas`
3. Click "Release" button
4. Confirm release

**Expected State**: Machine status changes to "Ready"

**Verification** (via CLI):
```bash
ssh -J root@pve.maas root@192.168.4.19 "maas admin machines read | jq '.[] | select(.hostname == \"pumped-piglet\") | {hostname: .hostname, status_name: .status_name}'"
# Expected: "status_name": "Ready"
```

---

#### Step 5.2: Deploy with New Image
**Objective**: Deploy pumped-piglet with Intel-specific image

**Actions** (via MAAS UI):
1. Select `pumped-piglet.maas` machine
2. Click "Deploy"
3. Choose OS: `Custom → debian-12-intel-xeon`
4. Click "Start deployment"

**Expected Duration**: 10-15 minutes

**Verification**:
```bash
# Check deployment status
ssh -J root@pve.maas root@192.168.4.19 "maas admin machines read | jq '.[] | select(.hostname == \"pumped-piglet\") | {hostname: .hostname, status_name: .status_name}'"

# Expected progression: "Deploying" → "Deployed"
```

---

#### Step 5.3: Monitor Deployment Logs
**Objective**: Watch for successful GRUB installation

**Actions** (via MAAS UI):
1. Click on `pumped-piglet.maas` machine
2. Navigate to "Logs" tab
3. Watch installation output for GRUB messages

**Success Indicators**:
- ✓ No "grub-install.real: error: will not proceed with blocklists"
- ✓ "Installing for x86_64-efi platform"
- ✓ "Installation finished" from curtin

**Failure Indicators**:
- ✗ "Installing for i386-pc platform"
- ✗ "grub-cloud-amd64" errors
- ✗ "Failed deployment" status

---

### Phase 6: Verification and Testing

#### Step 6.1: Verify Machine Deployed Successfully
**Objective**: Confirm MAAS shows successful deployment

**Actions**:
```bash
ssh -J root@pve.maas root@192.168.4.19 "maas admin machines read | jq '.[] | select(.hostname == \"pumped-piglet\") | {hostname: .hostname, status_name: .status_name, osystem: .osystem, distro_series: .distro_series}'"
```

**Expected Output**:
```json
{
  "hostname": "pumped-piglet",
  "status_name": "Deployed",
  "osystem": "custom",
  "distro_series": "debian-12-intel-xeon"
}
```

---

#### Step 6.2: Test SSH Access from Mac
**Objective**: Verify cloud-init deployed SSH keys and created user

**Actions**:
```bash
# Test all key/user combinations
for key in ~/.ssh/id_rsa ~/.ssh/id_ed25519_pve ~/.ssh/id_ed25519_windows; do
  if [ -f "$key" ]; then
    echo "=== Testing key: $(basename $key) ==="
    for user in root ubuntu admin gshiva gshiv; do
      echo -n "  $user@192.168.4.175: "
      if timeout 5 ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no -i "$key" "$user@192.168.4.175" "echo SUCCESS" 2>/dev/null; then
        echo "✓ SUCCESS!"
        break 2
      else
        echo "✗ failed"
      fi
    done
  fi
done
```

**Expected Output**: At least one key/user combination succeeds

**Verification**:
```bash
# Once successful combo found, verify system details
ssh [successful-user]@192.168.4.175 "hostname && cat /etc/os-release | grep PRETTY_NAME && uname -r"
```

---

#### Step 6.3: Test SSH Access from PVE
**Objective**: Verify SSH access from Proxmox host

**Actions**:
```bash
ssh root@pve.maas "ssh -o BatchMode=yes -o ConnectTimeout=5 root@192.168.4.175 'hostname && whoami'"
```

**Expected Output**:
```
pumped-piglet
root
```

---

#### Step 6.4: Verify Proxmox Installation
**Objective**: Confirm Proxmox VE packages installed correctly

**Actions**:
```bash
ssh [successful-user]@192.168.4.175 "dpkg -l | grep proxmox-ve"
ssh [successful-user]@192.168.4.175 "systemctl status pve-cluster || echo 'PVE cluster not configured yet (expected)'"
ssh [successful-user]@192.168.4.175 "pveversion"
```

**Expected Output**:
- Proxmox VE packages installed
- pveversion shows version info

---

#### Step 6.5: Verify GRUB Configuration
**Objective**: Confirm UEFI GRUB installed correctly

**Actions**:
```bash
ssh [successful-user]@192.168.4.175 "
  dpkg -l | grep grub | grep -E 'efi|pc' &&
  ls -la /boot/efi/EFI/ &&
  efibootmgr | grep -i proxmox
"
```

**Expected Output**:
- grub-efi-amd64 installed
- NO grub-pc or grub-cloud-amd64
- /boot/efi/EFI/Proxmox directory exists
- efibootmgr shows Proxmox boot entry

---

### Phase 7: Documentation and Cleanup

#### Step 7.1: Download Final Deployment Logs
**Objective**: Preserve successful deployment logs for documentation

**Actions** (via MAAS UI):
1. Navigate to pumped-piglet.maas → Logs
2. Download "Installation output"
3. Save as `pumped-piglet.maas-installation-success-$(date +%Y-%m-%d).log`

---

#### Step 7.2: Create Hardware-Specific Guide
**Objective**: Document P520-specific deployment procedure

**File**: `docs/source/md/guides/packer-maas-p520.md`

**Content**: Based on `packer-maas-ma90.md` template with P520-specific details

---

#### Step 7.3: Commit Changes to Git
**Objective**: Preserve script and documentation changes

**Actions**:
```bash
cd ~/code/home

# Add new files
git add docs/troubleshooting/blueprint-p520-grub-fix.md
git add docs/troubleshooting/action-log-template-p520-grub-fix.md
git add docs/troubleshooting/action-log-p520-grub-fix.md
git add docs/source/md/guides/packer-maas-p520.md

# Commit with issue reference
git commit -m "fix: resolve GRUB installation failure on Intel Xeon P520

- Created Intel-specific Packer script (my-intel-xeon-p520-changes.sh)
- Fixed grub-cloud-amd64 BIOS boot conflict on UEFI-only systems
- Added dpkg-divert to prevent problematic post-install hooks
- Documented P520 deployment procedure

Fixes #[ISSUE_NUMBER]"

# Push
git push origin master
```

---

#### Step 7.4: Update Packer Repo on PVE
**Objective**: Commit Intel script to packer-maas fork

**Actions**:
```bash
ssh root@pve.maas "cd ~/code/packer-maas/debian && \
  git add my-intel-xeon-p520-changes.sh Makefile && \
  git commit -m 'Add Intel Xeon P520 customization script

- Handle grub-cloud-amd64 UEFI conflicts
- Use dpkg-divert to prevent BIOS grub-install
- UEFI + Secure Boot compatible

Hardware: Lenovo ThinkStation P520' && \
  git log --oneline -1"
```

---

## Rollback Plan

### If Deployment Fails

#### Rollback Step 1: Revert Makefile
```bash
ssh root@pve.maas "cd ~/code/packer-maas/debian && \
  sed -i 's/customize_script=my-intel-xeon-p520-changes.sh/customize_script=my-amd-changes.sh/' Makefile"
```

#### Rollback Step 2: Use Previous Image
Via MAAS UI: Deploy pumped-piglet with original `debian-12-amd64` or `Proxmox Bookworm AMD` image

#### Rollback Step 3: Investigate Logs
```bash
# Download and analyze failed deployment logs
# Check for specific error messages
# Adjust script and retry
```

---

## Success Criteria

### Must Have (Deployment Success)
- ✓ Packer build completes without errors
- ✓ MAAS image upload successful
- ✓ Machine deploys to "Deployed" status
- ✓ No GRUB blocklist errors in logs
- ✓ UEFI GRUB installed (x86_64-efi platform)

### Must Have (SSH Access)
- ✓ SSH access works from Mac with at least one key
- ✓ SSH access works from PVE host
- ✓ Cloud-init deployed SSH keys correctly
- ✓ User account created (gshiva or root)

### Should Have (System Verification)
- ✓ Proxmox VE packages installed
- ✓ /boot/efi/EFI/Proxmox exists
- ✓ efibootmgr shows Proxmox entry
- ✓ No grub-pc or grub-cloud-amd64 packages

### Nice to Have (Documentation)
- ✓ Hardware guide created
- ✓ Action log completed
- ✓ Changes committed to git
- ✓ GitHub issue closed

---

**Tags**: blueprint, p520, intel-xeon, grub, uefi, secure-boot, maas, packer, deployment
