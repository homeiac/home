# K3s VM still-fawn Setup Runbook

## Overview

VM 108 on `still-fawn.maas` is a K3s control-plane node with GPU and TPU passthrough for Frigate NVR.

| Component | Details |
|-----------|---------|
| VMID | 108 |
| Hostname | k3s-vm-still-fawn |
| Host | still-fawn.maas |
| CPU | 4 cores (Intel i5-4460) |
| RAM | 25GB |
| Disk | 700GB on local-zfs |
| GPU | AMD Radeon RX 570/580 (VAAPI) |
| TPU | Google Coral USB (1a6e:089a, 18d1:9302) |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Proxmox Host: still-fawn.maas                                   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ VM 108: k3s-vm-still-fawn                               │   │
│  │                                                         │   │
│  │  ┌─────────────────┐  ┌─────────────────┐              │   │
│  │  │ Frigate Pod     │  │ K3s Components  │              │   │
│  │  │ - VAAPI decode  │  │ - etcd          │              │   │
│  │  │ - Coral TPU     │  │ - API server    │              │   │
│  │  │ - 3 cameras     │  │ - scheduler     │              │   │
│  │  └────────┬────────┘  └─────────────────┘              │   │
│  │           │                                             │   │
│  │  ┌────────▼────────┐  ┌─────────────────┐              │   │
│  │  │ /dev/dri        │  │ /dev/bus/usb    │              │   │
│  │  │ (AMD GPU)       │  │ (Coral TPU)     │              │   │
│  │  └────────┬────────┘  └────────┬────────┘              │   │
│  └───────────┼────────────────────┼────────────────────────┘   │
│              │ PCI Passthrough    │ USB Passthrough            │
│  ┌───────────▼────────┐  ┌────────▼────────┐                   │
│  │ AMD RX 570/580     │  │ Coral USB TPU   │                   │
│  │ (hostpci0)         │  │ (usb0, usb1)    │                   │
│  └────────────────────┘  └─────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

## Provisioning

### Crossplane Resources

VM 108 is managed by Crossplane with these resources:

1. **EnvironmentDownloadFile**: `ubuntu-noble-cloud-image-still-fawn`
   - Downloads Ubuntu 24.04 cloud image to `local:import/`

2. **EnvironmentVM**: `k3s-vm-still-fawn`
   - Creates VM with 4 cores, 25GB RAM, 700GB disk
   - Cloud-init joins K3s cluster automatically
   - `started: true` keeps VM running

3. **Job**: `vm108-add-passthrough` (one-time)
   - SSHes to Proxmox as root to add USB/PCI passthrough
   - Required because Crossplane API token lacks `Mapping.Use` permission

### Cloud-Init Requirements

The cloud-init snippet (`scripts/k3s/snippets/k3s-server-still-fawn.yaml`) must include:

```yaml
packages:
  - linux-modules-extra-generic  # amdgpu kernel module
  - linux-firmware               # AMD GPU firmware
  - mesa-va-drivers              # VAAPI userspace drivers
  - vainfo                       # VAAPI diagnostic tool

runcmd:
  # Load AMD GPU driver
  - |
    cat << 'EOF' > /etc/modules-load.d/amdgpu.conf
    amdgpu
    EOF
  - modprobe amdgpu || true
```

## Passthrough Configuration

### Verify on Proxmox Host

```bash
# Check VM config
ssh root@still-fawn.maas "qm config 108 | grep -E '(hostpci|usb)'"
# Expected:
# hostpci0: 0000:01:00,pcie=1
# usb0: host=1a6e:089a,usb3=1
# usb1: host=18d1:9302,usb3=1

# Verify IOMMU enabled
ssh root@still-fawn.maas "dmesg | grep -i iommu | head -3"

# Check GPU driver binding
ssh root@still-fawn.maas "lspci -nnk -s 01:00"
# Should show: Kernel driver in use: vfio-pci
```

### Verify Inside VM

```bash
# Check GPU visible
scripts/k3s/exec-still-fawn.sh "lspci | grep -i amd"

# Check /dev/dri exists
scripts/k3s/exec-still-fawn.sh "ls -la /dev/dri/"

# Verify VAAPI
scripts/k3s/exec-still-fawn.sh "vainfo"
```

## Frigate Status

### Check Frigate Pod

```bash
KUBECONFIG=~/kubeconfig kubectl get pods -n frigate -o wide
KUBECONFIG=~/kubeconfig kubectl logs -n frigate -l app=frigate --tail=50
```

### Verify Hardware Acceleration

```bash
# Check from Frigate API
KUBECONFIG=~/kubeconfig kubectl exec -n frigate -l app=frigate -- \
  curl -s localhost:5000/api/stats | jq '{
    detectors: .detectors,
    gpu_usages: .gpu_usages,
    cameras: [.cameras | to_entries[] | {name: .key, fps: .value.camera_fps}]
  }'
```

Expected output:
- `detectors.coral.inference_speed`: ~20-30ms
- `gpu_usages.amd-vaapi`: Shows GPU/mem usage
- All cameras showing FPS > 0

## Troubleshooting

### GPU Not Visible in VM

1. Check IOMMU groups on host:
   ```bash
   ssh root@still-fawn.maas "ls /sys/kernel/iommu_groups/ | wc -l"
   ```
   If 0, enable VT-d in BIOS (ASUS: Advanced > System Agent > VT-d)

2. Check vfio-pci binding:
   ```bash
   ssh root@still-fawn.maas "lspci -nnk -s 01:00"
   ```
   Should show `vfio-pci`, not `amdgpu`

3. Verify hostpci config:
   ```bash
   ssh root@still-fawn.maas "qm config 108 | grep hostpci"
   ```

### amdgpu Module Not Loading

1. Check if firmware installed:
   ```bash
   scripts/k3s/exec-still-fawn.sh "ls /lib/firmware/amdgpu/polaris10* | head -3"
   ```

2. Install if missing:
   ```bash
   scripts/k3s/exec-still-fawn.sh "apt-get install -y linux-firmware"
   ```

3. Load module:
   ```bash
   scripts/k3s/exec-still-fawn.sh "modprobe amdgpu"
   ```

### Crossplane Keeps Shutting Down VM

Check if `started: false` in Crossplane definition:
```bash
KUBECONFIG=~/kubeconfig kubectl get environmentvm k3s-vm-still-fawn -o jsonpath='{.spec.forProvider.started}'
```
Must be `true` for VM to stay running.

### Coral TPU Not Detected

1. Check USB passthrough:
   ```bash
   scripts/k3s/exec-still-fawn.sh "lsusb | grep -i google"
   ```

2. Check Frigate logs:
   ```bash
   KUBECONFIG=~/kubeconfig kubectl logs -n frigate -l app=frigate | grep -i tpu
   ```

## Related Resources

- Crossplane VM definition: `gitops/clusters/homelab/instances/k3s-vm-still-fawn.yaml`
- Passthrough job: `gitops/clusters/homelab/instances/job-vm108-passthrough.yaml`
- Cloud-init template: `scripts/k3s/snippets/k3s-server-still-fawn.yaml`
- Frigate deployment: `gitops/clusters/homelab/apps/frigate/deployment.yaml`
