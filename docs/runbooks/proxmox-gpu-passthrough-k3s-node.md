# Runbook: NVIDIA GPU Passthrough for K3s Nodes in Proxmox

**Purpose**: Configure NVIDIA GPU passthrough to Proxmox VMs for K8s GPU workloads
**Tested On**: Proxmox VE 8.x, Ubuntu 24.04 LTS VMs, NVIDIA GeForce RTX 3070
**Last Updated**: October 21, 2025

## Overview

This runbook covers the complete process of passing through an NVIDIA GPU to a Proxmox VM running as a K3s node, including driver installation, Secure Boot handling, and NVIDIA GPU Operator integration.

## Prerequisites

### Host Requirements

- Proxmox VE host with IOMMU enabled (Intel VT-d or AMD-Vi)
- NVIDIA GPU installed in PCIe slot
- GPU bound to vfio-pci driver on host
- Sufficient PCIe lanes and power for GPU

### VM Requirements

- UEFI (OVMF) firmware (not SeaBIOS)
- Q35 machine type
- Ubuntu 24.04 LTS (or compatible Linux distribution)
- Sufficient CPU cores and RAM for GPU workloads
- K3s installed or ready to install

### Verification Commands

```bash
# On Proxmox host: Check IOMMU groups
for d in /sys/kernel/iommu_groups/*/devices/*; do
    n=${d#*/iommu_groups/*}; n=${n%%/*}
    printf 'IOMMU Group %s ' "$n"
    lspci -nns "${d##*/}"
done | grep -i nvidia

# Expected output shows GPU in isolated IOMMU group
# Example: IOMMU Group 34 b3:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA104 [GeForce RTX 3070] [10de:2484]
```

## Part 1: Proxmox Host GPU Configuration

### Step 1: Identify GPU PCI Address

```bash
# On Proxmox host
lspci | grep -i nvidia

# Example output:
# b3:00.0 VGA compatible controller: NVIDIA Corporation GA104 [GeForce RTX 3070] (rev a1)
# b3:00.1 Audio device: NVIDIA Corporation GA104 High Definition Audio Controller (rev a1)
```

**Note**: Record the PCI address (e.g., `b3:00.0`). You may need both GPU and audio device.

### Step 2: Verify vfio-pci Driver Binding

```bash
# Check current driver for GPU
lspci -k -s b3:00.0

# Expected output:
# Kernel driver in use: vfio-pci
# Kernel modules: nvidiafb, nouveau, nvidia_drm, nvidia
```

If not using vfio-pci, bind it manually (see Proxmox GPU Passthrough Guide in docs).

### Step 3: Configure VM for GPU Passthrough

```bash
# On Proxmox host
VMID=105
HOST_GPU_PCI="0000:b3:00.0"  # Use your GPU's PCI address

# Add GPU to VM configuration
qm set $VMID --hostpci0 $HOST_GPU_PCI,pcie=1

# Verify VM uses UEFI and Q35
qm config $VMID | grep -E '(bios|machine)'

# Expected:
# bios: ovmf
# machine: q35
```

If not using UEFI/Q35, reconfigure VM:

```bash
qm set $VMID --bios ovmf --machine q35

# Add EFI disk if not present
qm set $VMID --efidisk0 local-zfs:1,efitype=4m,pre-enrolled-keys=0,size=1M
```

**CRITICAL**: Use `pre-enrolled-keys=0` to avoid Secure Boot issues (explained in Part 3).

### Step 4: Apply GPU Passthrough (Requires Full Stop/Start)

```bash
# Stop VM completely (DO NOT use reboot)
qm stop $VMID

# Start VM with new GPU configuration
qm start $VMID
```

**Important**: VM reboot does NOT activate GPU passthrough changes. Must use stop/start cycle.

### Step 5: Verify GPU Visible in VM

```bash
# From Proxmox host (using qm guest exec)
ssh root@<proxmox-host>.maas "qm guest exec $VMID -- lspci | grep -i nvidia"

# Or SSH directly to VM
ssh ubuntu@<vm-ip> "lspci | grep -i nvidia"

# Expected output:
# 01:00.0 VGA compatible controller: NVIDIA Corporation GA104 [GeForce RTX 3070]
# 01:00.1 Audio device: NVIDIA Corporation GA104 High Definition Audio Controller
```

**If GPU not visible**: Verify IOMMU groups, vfio-pci binding, and perform full stop/start (not reboot).

## Part 2: NVIDIA Driver Installation in VM

### Step 1: Install NVIDIA Drivers

```bash
# SSH into VM
ssh ubuntu@<vm-ip>

# Update package lists
sudo apt update

# Install NVIDIA drivers (using 535 for RTX 3070 compatibility)
sudo DEBIAN_FRONTEND=noninteractive apt install -y \
    nvidia-driver-535 \
    nvidia-utils-535
```

**Driver Version Selection**:
- RTX 30-series (Ampere): nvidia-driver-535 or newer
- RTX 40-series (Ada Lovelace): nvidia-driver-545 or newer
- Check NVIDIA docs for specific GPU compatibility

### Step 2: Attempt Driver Loading

```bash
# Try loading nvidia kernel module
sudo modprobe nvidia

# Check for errors
sudo dmesg | tail -20
```

**If modprobe fails with "Key was rejected by service"**: Proceed to Part 3 (Secure Boot troubleshooting).

**If successful**: Skip Part 3 and proceed to Part 4.

### Step 3: Verify nvidia-smi (After Driver Load Success)

```bash
nvidia-smi

# Expected output:
# +-----------------------------------------------------------------------------+
# | NVIDIA-SMI 535.274.02   Driver Version: 535.274.02   CUDA Version: 12.2     |
# |-------------------------------+----------------------+----------------------+
# | GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
# |   0  NVIDIA GeForce...     Off | 00000000:01:00.0 Off |                  N/A |
# +-------------------------------+----------------------+----------------------+
```

## Part 3: Secure Boot Troubleshooting (If Driver Loading Fails)

### Symptom: Kernel Module Rejected

```bash
sudo modprobe nvidia
# Error: modprobe: ERROR: could not insert 'nvidia': Key was rejected by service
```

### Root Cause

NVIDIA proprietary drivers are unsigned kernel modules. When Secure Boot is enabled, the kernel's lockdown mode rejects unsigned modules for security.

### Diagnosis

```bash
# Check kernel lockdown status
cat /sys/kernel/security/lockdown
# Output: none [integrity] confidentiality
# [integrity] means Secure Boot is active

# Verify Secure Boot enabled
sudo dmesg | grep -i secureboot
# Expected: secureboot: Secure boot enabled
```

### Resolution: Recreate EFI Disk Without Secure Boot Keys

**WARNING**: This will reset the EFI configuration. VM will need to re-detect boot entries.

```bash
# On Proxmox host
VMID=105

# 1. Stop VM
qm stop $VMID

# 2. Delete existing EFI disk
qm set $VMID --delete efidisk0

# 3. Create new EFI disk WITHOUT pre-enrolled Secure Boot keys
qm set $VMID --efidisk0 local-zfs:1,efitype=4m,pre-enrolled-keys=0,size=1M

# Output confirms:
# efidisk0: successfully created disk 'local-zfs:vm-105-disk-2,efitype=4m,pre-enrolled-keys=0,size=1M'

# 4. Start VM
qm start $VMID
```

### Post-Resolution Verification

```bash
# SSH into VM after boot
ssh ubuntu@<vm-ip>

# Verify lockdown disabled
cat /sys/kernel/security/lockdown
# Expected: [none] integrity confidentiality
# [none] means Secure Boot is disabled

# Verify Secure Boot disabled
sudo dmesg | grep -i secureboot
# Should show no "Secure boot enabled" messages

# Load NVIDIA driver
sudo modprobe nvidia

# Verify nvidia-smi works
nvidia-smi
```

### Why This Works

- `pre-enrolled-keys=0`: Creates UEFI firmware without Microsoft/vendor Secure Boot keys
- Fresh EFI disk: Removes any previously enrolled keys from old boot attempts
- VM still uses UEFI: Just without Secure Boot enforcement

**Security Note**: Disabling Secure Boot reduces boot-time security. For homelab GPU workloads, this trade-off is acceptable. For production environments, consider signing NVIDIA modules or using alternative approaches.

## Part 4: NVIDIA GPU Operator Integration (K3s/K8s)

### Overview

The NVIDIA GPU Operator automatically manages NVIDIA software components in Kubernetes, including:
- NVIDIA Container Toolkit
- NVIDIA Device Plugin
- GPU Feature Discovery
- DCGM Exporter (monitoring)
- Node Feature Discovery

**Do NOT manually install NVIDIA Container Toolkit** if using GPU Operator.

### Step 1: Verify GPU Operator Installed

```bash
# From machine with KUBECONFIG access
export KUBECONFIG=~/kubeconfig
kubectl get pods -n gpu-operator

# Expected output (example):
# NAME                                                          READY   STATUS      RESTARTS   AGE
# gpu-operator-666bbffcd-pkwh7                                  1/1     Running     90         85d
# nvidia-container-toolkit-daemonset-qr5f2                      1/1     Running     0          6m
# nvidia-cuda-validator-dn2hh                                   0/1     Completed   0          4m
# nvidia-dcgm-exporter-fr99h                                    1/1     Running     0          6m
# nvidia-device-plugin-daemonset-sm4xn                          2/2     Running     0          6m
# gpu-feature-discovery-tdlch                                   2/2     Running     0          6m
```

**If GPU Operator not installed**: See NVIDIA GPU Operator installation docs.

### Step 2: Verify GPU Operator DaemonSets Deployed to New Node

```bash
# Check DaemonSet pods on GPU node
kubectl get pods -n gpu-operator -o wide | grep <node-name>

# Should see:
# - nvidia-container-toolkit-daemonset-<hash> on new node
# - nvidia-device-plugin-daemonset-<hash> on new node
# - gpu-feature-discovery-<hash> on new node
# - nvidia-dcgm-exporter-<hash> on new node
```

### Step 3: Check CUDA Validation

```bash
# Find CUDA validator pod for new node
kubectl get pods -n gpu-operator | grep cuda-validator

# Check logs
kubectl logs -n gpu-operator nvidia-cuda-validator-<hash>

# Expected output:
# cuda workload validation is successful
```

### Step 4: Verify Node GPU Capacity

```bash
# Check node GPU resources
kubectl describe node <node-name> | grep -A 10 "Capacity:"

# Expected output includes:
# Capacity:
#   cpu:                10
#   memory:             49311516Ki
#   nvidia.com/gpu:     4    <-- GPU resource advertised
#   pods:               110
# Allocatable:
#   nvidia.com/gpu:     4    <-- GPUs available for scheduling
```

**Note**: GPU count may appear as 4 for single RTX 3070 due to MIG (Multi-Instance GPU) mode or NVIDIA resource reporting. This is normal.

### Step 5: Test GPU Workload

```yaml
# Create test-gpu-workload.yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test
spec:
  restartPolicy: Never
  nodeSelector:
    kubernetes.io/hostname: <your-gpu-node-name>
  containers:
  - name: cuda-vectoradd
    image: "nvcr.io/nvidia/k8s/cuda-sample:vectoradd-cuda11.7.1-ubuntu20.04"
    resources:
      limits:
        nvidia.com/gpu: 1
```

```bash
# Deploy test workload
kubectl apply -f test-gpu-workload.yaml

# Monitor pod
kubectl get pod gpu-test -w

# Check logs after completion
kubectl logs gpu-test

# Expected output:
# [Vector addition of 50000 elements]
# Copy input data from the host memory to the CUDA device
# CUDA kernel launch with 196 blocks of 256 threads
# Copy output data from the CUDA device to the host memory
# Test PASSED
```

## Part 5: Troubleshooting

### GPU Not Visible in VM

**Symptoms**:
- `lspci | grep -i nvidia` shows no NVIDIA devices in VM
- VM shows generic VGA controller (Device 1234:1111)

**Diagnosis**:
```bash
# On Proxmox host
qm config $VMID | grep hostpci
# Should show: hostpci0: 0000:b3:00.0,pcie=1

lspci -k -s b3:00.0
# Should show: Kernel driver in use: vfio-pci
```

**Resolution**:
1. Verify GPU bound to vfio-pci on host
2. Perform full VM stop/start cycle (NOT reboot)
3. Check IOMMU groups for conflicts

### nvidia-smi Shows No Devices

**Symptoms**:
- Driver loads without errors
- `nvidia-smi` shows "No devices were found"

**Diagnosis**:
```bash
# Check if GPU visible to kernel
lspci | grep -i nvidia

# Check loaded modules
lsmod | grep nvidia
```

**Resolution**:
1. Verify GPU passthrough active (Part 1, Step 5)
2. Reinstall NVIDIA drivers
3. Check dmesg for kernel errors: `sudo dmesg | grep -i nvidia`

### K8s Pods Not Scheduling to GPU Node

**Symptoms**:
- GPU workload pods stuck in Pending
- No GPU resources showing in node capacity

**Diagnosis**:
```bash
# Check GPU Operator pods
kubectl get pods -n gpu-operator -o wide

# Check node GPU capacity
kubectl describe node <gpu-node> | grep nvidia.com/gpu

# Check pod events
kubectl describe pod <pending-gpu-pod>
```

**Resolution**:
1. Ensure NVIDIA GPU Operator DaemonSets running on node
2. Check nvidia-device-plugin logs: `kubectl logs -n gpu-operator nvidia-device-plugin-<hash>`
3. Verify node labels: `kubectl get node <gpu-node> --show-labels | grep nvidia`
4. Restart GPU Operator pods if needed

## Reference: Complete VM Configuration Example

```bash
# Proxmox host configuration for GPU passthrough VM
VMID=105
VM_NAME="k3s-vm-pumped-piglet-gpu"
HOST_GPU_PCI="0000:b3:00.0"
STORAGE="local-zfs"

# VM settings
qm set $VMID --name $VM_NAME
qm set $VMID --cores 10
qm set $VMID --memory 49152
qm set $VMID --bios ovmf
qm set $VMID --machine q35
qm set $VMID --efidisk0 $STORAGE:1,efitype=4m,pre-enrolled-keys=0,size=1M
qm set $VMID --hostpci0 $HOST_GPU_PCI,pcie=1

# Network, boot disk, etc. configured separately
```

## Tags

gpu, gpu-passthrough, nvidia, proxmox, k3s, kubernetes, k8s, rtx-3070, vfio-pci, uefi, secure-boot, nvidia-gpu-operator, cuda, pcie-passthrough, iommu, virtualization

## Related Documentation

- [Secure Boot and NVIDIA Drivers Troubleshooting](../troubleshooting/secure-boot-nvidia-drivers.md)
- [K3s etcd Stale Member Removal Action Log](../troubleshooting/action-log-k3s-etcd-stale-member-removal.md)
- [NVIDIA GPU Operator Documentation](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/overview.html)
- [Proxmox GPU Passthrough Guide](https://pve.proxmox.com/wiki/PCI_Passthrough)
