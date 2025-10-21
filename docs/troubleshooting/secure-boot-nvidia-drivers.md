# Troubleshooting: Secure Boot and NVIDIA Drivers

**Issue**: NVIDIA proprietary drivers fail to load due to Secure Boot
**Affected Systems**: Proxmox VMs with UEFI firmware and GPU passthrough
**Last Updated**: October 21, 2025

## Symptom

```bash
sudo modprobe nvidia
# Error: modprobe: ERROR: could not insert 'nvidia': Key was rejected by service
```

## Root Cause

NVIDIA proprietary drivers are unsigned kernel modules. When Secure Boot is enabled, Linux kernel lockdown mode rejects unsigned modules for security.

## Quick Diagnosis

```bash
# Check kernel lockdown status
cat /sys/kernel/security/lockdown
# [integrity] means Secure Boot is active

# Verify Secure Boot enabled
sudo dmesg | grep -i secureboot
# Expected: "secureboot: Secure boot enabled"
```

## Resolution: Recreate EFI Disk Without Secure Boot Keys

### Step 1: Stop VM

```bash
# On Proxmox host
VMID=105
qm stop $VMID
```

### Step 2: Delete Existing EFI Disk

```bash
qm set $VMID --delete efidisk0
```

### Step 3: Create New EFI Disk WITHOUT Pre-Enrolled Keys

```bash
qm set $VMID --efidisk0 local-zfs:1,efitype=4m,pre-enrolled-keys=0,size=1M
```

**Key Parameter**: `pre-enrolled-keys=0` creates UEFI firmware without Microsoft/vendor Secure Boot keys.

### Step 4: Start VM and Verify

```bash
qm start $VMID

# After VM boots, verify Secure Boot disabled
ssh ubuntu@<vm-ip>
cat /sys/kernel/security/lockdown
# Expected: [none] means Secure Boot is disabled

# Load NVIDIA driver
sudo modprobe nvidia

# Verify nvidia-smi works
nvidia-smi
```

## Why This Works

- Fresh EFI disk removes any previously enrolled Secure Boot keys
- `pre-enrolled-keys=0` prevents automatic enrollment of Microsoft keys
- VM still uses UEFI (modern firmware) without Secure Boot enforcement
- Allows loading unsigned kernel modules like NVIDIA drivers

## Security Considerations

**Trade-off**: Disabling Secure Boot reduces boot-time security by allowing unsigned bootloaders and kernel modules.

**For Homelab GPU Workloads**: This trade-off is generally acceptable.
**For Production Environments**: Consider these alternatives:
- Sign NVIDIA modules with Machine Owner Key (MOK)
- Use open-source nouveau drivers (limited GPU features)
- Use datacenter GPUs with signed drivers

## Alternative: Sign NVIDIA Modules (Advanced)

Instead of disabling Secure Boot, you can sign NVIDIA modules:

```bash
# Generate signing keys
sudo mokutil --import /var/lib/shim-signed/mok/MOK.der

# Reboot and enroll MOK in firmware
# Sign NVIDIA modules with your key
# This is complex and beyond scope of this quick guide
```

**Reference**: See Ubuntu/Red Hat documentation for MOK signing procedures.

## Tags

secure-boot, uefi, nvidia, nvidia-drivers, gpu, gpu-passthrough, proxmox, kernel-modules, lockdown-mode, troubleshooting

## Related Documentation

- [GPU Passthrough Runbook](../runbooks/proxmox-gpu-passthrough-k3s-node.md)
- [Proxmox VM GPU Passthrough Guide](https://pve.proxmox.com/wiki/PCI_Passthrough)
