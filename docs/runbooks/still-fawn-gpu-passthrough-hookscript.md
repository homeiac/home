# still-fawn GPU Passthrough Hookscript Runbook

## Overview

This runbook documents the AMD RX 580 GPU reset bug mitigation for VM 108 (k3s-vm-still-fawn) on the still-fawn Proxmox host.

## Problem Statement

AMD Polaris GPUs (RX 470/480/570/580/590) have a well-known "GPU Reset Bug" where:
- The GPU doesn't reset cleanly between VM uses
- The `amdgpu` kernel module gets stuck in `Loading` state
- In severe cases: spinlock contention, system hangs

## Solution

**Hookscript with Auto-Reboot:**
1. Performs PCI reset on VM stop/start
2. After VM start, waits 90s then checks for `/dev/dri/renderD128`
3. If GPU failed to initialize → automatically reboots host
4. Max 3 retries before giving up (prevents reboot loops)
5. Retry counter resets on successful GPU init

## Deployment (GitOps)

The hookscript is deployed via GitOps using the `proxmox-provisioner` image:

```
scripts/proxmox/provisioner/           # Docker image source
  ├── Dockerfile
  ├── deploy.sh
  └── scripts/hookscripts/
      └── gpu-reset-vm108.sh

gitops/.../proxmox-provisioner/        # K8s manifests
  ├── cronjob.yaml                     # Daily sync + initial job
  └── kustomization.yaml

.github/workflows/proxmox-provisioner.yml  # Builds image on push
```

**Manual trigger:**
```bash
kubectl create job --from=cronjob/proxmox-provisioner-still-fawn manual-provision -n kube-system
```

## Hardware

| Component | PCI Address | Vendor:Device |
|-----------|-------------|---------------|
| AMD RX 580 GPU | 01:00.0 | 1002:67df |
| AMD RX 580 HDMI Audio | 01:00.1 | 1002:aaf0 |

## VFIO Configuration

The GPU is configured for VFIO passthrough (stays bound to vfio-pci):
```
# /etc/modprobe.d/vfio.conf on still-fawn
options vfio-pci ids=1002:67df,1002:aaf0 disable_vga=1
```

## Files

| Location | Purpose |
|----------|---------|
| `/var/lib/vz/snippets/gpu-reset-vm108.sh` | Hookscript on still-fawn |
| `/var/log/gpu-reset.log` | Hookscript logs |
| `scripts/proxmox/gpu-reset-vm108.sh` | Source copy in git repo |

## How It Works

### pre-start Phase
1. Checks current GPU driver state
2. Ensures GPU is bound to `vfio-pci` for passthrough

### post-stop Phase
1. Waits 3 seconds for VM cleanup
2. Triggers PCI device reset (remove/rescan)
3. Re-binds to vfio-pci

## Quick Reference Commands

### Check if VM is healthy
```bash
ssh root@still-fawn.maas "qm status 108 && qm guest exec 108 -- systemctl is-active k3s"
```

### Check K3s node status
```bash
ssh root@still-fawn.maas "qm guest exec 108 -- kubectl get nodes | grep still-fawn"
```

### Check hookscript logs
```bash
ssh root@still-fawn.maas "tail -20 /var/log/gpu-reset.log"
```

### Check GPU driver state on host
```bash
ssh root@still-fawn.maas "lspci -nnk -s 01:00 | grep driver"
# Should show: vfio-pci (whether VM running or stopped)
```

### Check amdgpu module state in VM
```bash
ssh root@still-fawn.maas "qm guest exec 108 -- lsmod | grep amdgpu"
# "Live" = good, "Loading" = GPU reset bug manifesting
```

## Troubleshooting

### K3s works but GPU is stuck

If K3s is healthy but you need the GPU (for VAAPI/encoding):

```bash
# Reboot the Proxmox host (cleanest fix)
ssh root@still-fawn.maas "reboot"
# Wait ~2 minutes, VM will auto-start (onboot=1)
```

### VM won't start

```bash
# Check hookscript errors
ssh root@still-fawn.maas "tail -50 /var/log/gpu-reset.log"

# Check VM config
ssh root@still-fawn.maas "cat /etc/pve/qemu-server/108.conf"
```

### K3s unhealthy after restart

```bash
# Check K3s status
ssh root@still-fawn.maas "qm guest exec 108 -- systemctl status k3s"

# Restart K3s
ssh root@still-fawn.maas "qm guest exec 108 -- systemctl restart k3s"

# Wait and check
sleep 30
ssh root@still-fawn.maas "qm guest exec 108 -- kubectl get nodes"
```

### Nuclear option - full reset

```bash
# Stop VM, reboot host, wait for auto-start
ssh root@still-fawn.maas "qm stop 108; reboot"
# Wait 3-4 minutes
ssh root@still-fawn.maas "qm status 108 && qm guest exec 108 -- systemctl is-active k3s"
```

## Installation (Already Complete)

```bash
# 1. Copy hookscript to still-fawn
scp scripts/proxmox/gpu-reset-vm108.sh root@still-fawn.maas:/var/lib/vz/snippets/

# 2. Make executable
ssh root@still-fawn.maas "chmod +x /var/lib/vz/snippets/gpu-reset-vm108.sh"

# 3. Attach to VM 108
ssh root@still-fawn.maas "qm set 108 --hookscript local:snippets/gpu-reset-vm108.sh"

# 4. Verify
ssh root@still-fawn.maas "grep hookscript /etc/pve/qemu-server/108.conf"
```

## Removing the Hookscript

```bash
ssh root@still-fawn.maas "qm set 108 --delete hookscript"
```

## Related Documentation

- [Proxmox Hookscripts Wiki](https://pve.proxmox.com/wiki/Hookscripts)
- [AMD GPU Reset Bug Discussion](https://wiki.archlinux.org/title/PCI_passthrough_via_OVMF#AMD_GPU_Reset_Bug)
- GPU Passthrough Guide: `proxmox/guides/nvidia-RTX-3070-k3s-PCI-passthrough.md`

## Tags

gpu, amdgpu, rx580, passthrough, hookscript, vfio, pci, reset-bug, still-fawn, vm108, proxmox
