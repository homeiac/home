# Packer-MAAS build notes — ATOPNUC MA90 (AMD A9-9400 / Radeon R5)

These are the **exact commands, edits, and error lines** encountered while
building a Proxmox-ready Debian 12 cloud-image with
[canonical/packer-maas](https://github.com/canonical/packer-maas) and importing
it into Ubuntu MAAS for ATOPNUC MA90 (AMD A9-9400 / Radeon R5).

---

## 1  The Curtin error that started it all

```log

grub-install.real: warning: this GPT partition label contains no BIOS Boot Partition; embedding wont be possible.
grub-install.real: warning: Embedding is not possible.  GRUB can only be installed in this setup by using blocklists.
grub-install.real: error: will not proceed with blocklists.
dpkg: error processing package grub-cloud-amd64 (--configure):
installed grub-cloud-amd64 package post-installation script subprocess returned error exit status 1
E: Sub-process /usr/bin/dpkg returned an error code (1)

```

Curtin aborted, the MA90 rebooted, firmware jumped back to the half-installed
SSD, and MAAS marked the node **Failed deployment**.

---

## 2  BIOS quirk

*After every reboot* the MA90 firmware re-enabled “Boot from Hard Disk” and
moved it above PXE.
**Work-around:** before each deploy, enter BIOS, disable HDD boot, leave only
“PXE IPv4” enabled.

---

## 3  Changes made inside the packer repo

### `debian/Makefile` (excerpts)

```Makefile

PACKER\_LOG = 1          # verbose
SERIES      = bookworm  # always build Debian 12
disk\_size   = "16G"     # avoid space issues
-var customize\_script=my-amd-changes.sh

````

### `my-amd-changes.sh` (only the lines you added)

```bash
#!/bin/bash
apt-get install -y gnupg lsb-release

# Proxmox repository
echo "deb [arch=amd64] http://download.proxmox.com/debian/pve \
$(lsb_release -cs) pve-no-subscription" \
  > /etc/apt/sources.list.d/pve-install-repo.list
wget https://enterprise.proxmox.com/debian/proxmox-release-$(lsb_release -cs).gpg \
     -O /etc/apt/trusted.gpg.d/proxmox-release.gpg

apt-get update && apt full-upgrade -y
apt-get install -y proxmox-ve postfix open-iscsi chrony zfsutils-linux zfs-initramfs
apt-get remove -y linux-image-amd64 'linux-image-6.1*'

# ── key bit ──────────────────────────────────────────────────────────── purge
# BIOS GRUB to stop the blocklist error
apt-get purge -y grub-pc grub-cloud-amd64
# install EFI-only GRUB
apt-get install -y grub-efi-amd64 shim-signed
update-grub
# ───────────────────────────────────────────────────────────────────────

# (uncertain) the script also ran grub-install and /boot/efi dir creation
# to create an ESP (ESP = EFI System Partition) here; can't confirm
# if this is required

# 3) Make sure /boot/efi exists and is mounted (your image builder must have created
#    a 512 MiB FAT32 partition at /boot/efi and an appropriate fstab entry):
mkdir -p /boot/efi
mount /boot/efi
# 4) Install GRUB into the ESP:
grub-install \
  --target=x86_64-efi \
  --efi-directory=/boot/efi \
  --bootloader-id=Proxmox \
  --recheck

````

‣ **Uncertainty:** creating the ESP in this script *may* have been what finally
satisfied GRUB. The exact block that did it has not been isolated.

---

## 4  Build + upload commands

```bash
# on the build host
cd code/packer-maas/debian/
make                                   # runs packer with edits
scp debian-custom-cloudimg.tar.gz <user>@192.168.4.53:/home/<user>/
```

```bash
# on the MAAS region controller (192.168.4.53)
maas admin boot-resources create \
  name='custom/debian-12-amd64' \
  title='Proxmox Bookworm AMD' \
  architecture='amd64/generic' \
  filetype='tgz' \
  content@=debian-custom-cloudimg.tar.gz
```

MAAS then listed the image under **Images → Custom** and deployments stopped
throwing the blocklist error.

---

## 5  Next time checklist

1. BIOS on AMD MA 90 (Press `F2`) and continuously disable HDD boot.
2. Rebuild / Upload the rebuilt image (if required)
3. Deploy; verify GRUB installs to the ESP, Curtin completes, MAAS flips the
   node to **Deployed**.

---

Last verified: MAAS 3.6 (stable) • May 2025
