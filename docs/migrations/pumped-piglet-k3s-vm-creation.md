# Pumped-Piglet K3s VM Creation - Migration Documentation

**Date**: 2025-10-21
**Node**: pumped-piglet.maas (192.168.4.175)
**VM ID**: 105
**VM Name**: k3s-vm-pumped-piglet
**VM IP**: 192.168.4.208
**Purpose**: Migrate K3s workloads from failed still-fawn node

## Summary

Successfully created K3s VM 105 on pumped-piglet using automated migration script after fixing four critical configuration issues. VM boots in ~35 seconds and obtains IP address via cloud-init.

## VM Configuration

### Hardware
- **Memory**: 49152MB (48GB)
- **CPU Cores**: 10
- **CPU Type**: host
- **Machine Type**: i440fx (default, NOT q35)
- **Network**: virtio, bridge=vmbr0
- **SCSI Controller**: virtio-scsi-pci (CRITICAL)

### Storage
- **Boot Disk**: local-2TB-zfs:vm-105-disk-0 (1800GB, NVMe)
- **Cloud-init**: local:snippets/install-k3sup-qemu-agent.yaml
- **Base Image**: noble-server-cloudimg-amd64.img (Ubuntu 24.04 LTS)

### Software
- **Guest Agent**: qemu-guest-agent (enabled)
- **K3s Tools**: k3sup pre-installed via cloud-init
- **SSH**: Ubuntu user with passwordless sudo
- **Network**: DHCP with cloud-init hostname configuration

## Critical Fixes Required

### Fix 1: Cloud-init Snippet Missing on pumped-piglet
**Symptom**: VMs timing out after 180s waiting for IP address
**Root Cause**: `/var/lib/vz/snippets/install-k3sup-qemu-agent.yaml` didn't exist on pumped-piglet
**Fix**:
```bash
scp root@pve.maas:/var/lib/vz/snippets/install-k3sup-qemu-agent.yaml \
    root@pumped-piglet.maas:/var/lib/vz/snippets/
```
**Commit**: `3fb8d35` - "fix: add cloud-init snippet to VM creation"

### Fix 2: Hostname Resolution - "localhost.maas"
**Symptom**: `Failed to resolve 'localhost.maas' ([Errno -2] Name or service not known)`
**Root Cause**: Migration script used `ProxmoxClient("localhost")` which became "localhost.maas"
**Fix**: Changed line 169 in `pumped_piglet_migration.py`:
```python
# Before:
self.proxmox = ProxmoxClient("localhost").proxmox

# After:
self.proxmox = ProxmoxClient(self.NODE).proxmox  # NODE = "pumped-piglet"
```
**Commit**: `d0e8a24` - "fix: use node name instead of localhost for Proxmox API"

### Fix 3: Remove GPU Passthrough (Per User Decision)
**Symptom**: VM created but never booted successfully
**Root Cause**: GPU passthrough configuration (q35 machine type, hostpci) causing boot issues
**Fix**: Removed GPU passthrough entirely:
```python
# Removed from VM creation:
# - --machine q35
# - --serial0 socket
# - --vga serial0
# - hostpci0 configuration
```
**Commit**: `cb4628d` - "fix: remove GPU passthrough from VM creation"

### Fix 4: Missing SCSI Controller Configuration
**Symptom**: VM created and started but never booted (no IP after 180s)
**Root Cause**: VM missing `scsihw` (SCSI hardware controller) - disk couldn't be accessed
**Fix**: Added SCSI controller configuration:
```python
f"qm set {vmid} --scsihw virtio-scsi-pci",
```
**Diagnosis**: Checked `qm config 105` and found no `scsihw` line, compared to working VMs
**Commit**: `6bd16f1` - "fix: add SCSI controller configuration for VM boot"

## VM Creation Command Sequence

```bash
# 1. Create VM with basic config
qm create 105 --name k3s-vm-pumped-piglet --memory 49152 \
  --cores 10 --cpu host --net0 virtio,bridge=vmbr0 --agent enabled=1

# 2. Import Ubuntu cloud image to ZFS pool
qm importdisk 105 /var/lib/vz/template/iso/noble-server-cloudimg-amd64.img local-2TB-zfs

# 3. Configure SCSI controller (CRITICAL - was missing)
qm set 105 --scsihw virtio-scsi-pci

# 4. Attach boot disk
qm set 105 --scsi0 local-2TB-zfs:vm-105-disk-0

# 5. Configure cloud-init drive
qm set 105 --ide2 local-2TB-zfs:cloudinit

# 6. Set boot order
qm set 105 --boot c --bootdisk scsi0

# 7. Attach cloud-init snippet (CRITICAL - was missing)
qm set 105 --cicustom user=local:snippets/install-k3sup-qemu-agent.yaml

# 8. Resize boot disk to 1800GB
qm resize 105 scsi0 1800G

# 9. Start VM
qm start 105
```

## Verification Steps

### 1. Verify VM Status
```bash
ssh root@pumped-piglet.maas "qm list | grep 105"
# Expected: 105 running
```

### 2. Verify VM Configuration
```bash
ssh root@pumped-piglet.maas "qm config 105"
# Check for:
# - scsihw: virtio-scsi-pci
# - scsi0: local-2TB-zfs:vm-105-disk-0
# - cicustom: user=local:snippets/install-k3sup-qemu-agent.yaml
# - agent: 1
```

### 3. Wait for Guest Agent (Usually 30-40s)
```bash
ssh root@pumped-piglet.maas "qm agent 105 network-get-interfaces"
# Expected: JSON with network interfaces including IP address
```

### 4. Verify VM Accessibility
```bash
# Get IP address
VM_IP=$(ssh root@pumped-piglet.maas "qm agent 105 network-get-interfaces" | \
  jq -r '.[] | select(.name == "enp6s18") | ."ip-addresses"[] | select(.["ip-address-type"] == "ipv4") | .["ip-address"]')

# Test SSH access
ssh ubuntu@$VM_IP "hostname && ip a"
# Expected: k3s-vm-pumped-piglet.maas
```

## Migration Script Execution

### Successful Run Output
```
2025-10-21 06:12:38,225 - __main__ - INFO - PHASE 3: K3s VM Creation
2025-10-21 06:12:38,258 - __main__ - INFO - Using VMID: 105
2025-10-21 06:12:38,264 - __main__ - INFO - ▶️  Running step: create_vm
2025-10-21 06:12:38,264 - __main__ - INFO - Creating VM 105 (k3s-vm-pumped-piglet)
2025-10-21 06:12:50,445 - __main__ - INFO - ✅ Step 'create_vm' completed
2025-10-21 06:12:50,445 - __main__ - INFO - ▶️  Running step: get_vm_ip
2025-10-21 06:12:50,445 - __main__ - INFO - Waiting for VM 105 to get IP address...
2025-10-21 06:13:25,418 - __main__ - INFO - ✅ VM IP: 192.168.4.208
```

### Run Migration Script
```bash
cd /Users/10381054/code/home
ssh root@pumped-piglet.maas "cd /root/home && git pull"
ssh root@pumped-piglet.maas "cd /root/home/proxmox/homelab && poetry run python -m homelab.pumped_piglet_migration"
```

### Clear State for Fresh Run
```bash
ssh root@pumped-piglet.maas "rm -f /tmp/pumped_piglet_migration.json"
```

## Troubleshooting Guide

### Issue: VM Timeout Waiting for IP
**Symptoms**:
- Migration script waits 180s for IP
- `qm agent 105 network-get-interfaces` returns error
- VM appears running but no network

**Diagnosis**:
```bash
# Check if cloud-init snippet exists
ssh root@pumped-piglet.maas "ls -lh /var/lib/vz/snippets/install-k3sup-qemu-agent.yaml"

# Check if VM has cloud-init configured
ssh root@pumped-piglet.maas "qm config 105 | grep cicustom"

# Check if SCSI controller is configured
ssh root@pumped-piglet.maas "qm config 105 | grep scsihw"

# Check VM console for boot errors
ssh root@pumped-piglet.maas "qm terminal 105"
```

**Solutions**:
1. Copy cloud-init snippet from working node (Fix 1)
2. Add `--cicustom` to VM configuration (Fix 1)
3. Add SCSI controller with `--scsihw virtio-scsi-pci` (Fix 4)

### Issue: VM Won't Boot
**Symptoms**:
- VM status shows "running"
- Guest agent never starts
- No console output

**Diagnosis**:
```bash
# Check SCSI controller
ssh root@pumped-piglet.maas "qm config 105 | grep scsihw"
# If missing: VM can't access boot disk

# Check machine type
ssh root@pumped-piglet.maas "qm config 105 | grep machine"
# If q35: May conflict with GPU passthrough or hardware

# Check for GPU passthrough
ssh root@pumped-piglet.maas "qm config 105 | grep hostpci"
# If present: Remove GPU passthrough (Fix 3)
```

**Solutions**:
1. Add SCSI controller: `qm set 105 --scsihw virtio-scsi-pci` (Fix 4)
2. Remove GPU passthrough if present (Fix 3)
3. Use default i440fx machine type, not q35

### Issue: Proxmox API Connection Errors
**Symptoms**:
- `Failed to resolve 'localhost.maas'`
- `ConnectionError` from proxmoxer library

**Solution**:
- Use actual node name in `ProxmoxClient()` constructor (Fix 2)
- Never use "localhost" with proxmox_api.py

## Cloud-init Snippet Details

**Location**: `/var/lib/vz/snippets/install-k3sup-qemu-agent.yaml`
**Size**: 6.0K
**Purpose**: Configure VM hostname, SSH keys, packages, and K3s tools

**Key Configuration**:
- Hostname: `k3s-vm-pve.maas` (template, gets customized per node)
- User: `ubuntu` with passwordless sudo
- Packages: `qemu-guest-agent`, `curl`, `k3sup`
- Network: DHCP with cloud-init
- Storage: Auto-grow root filesystem to full disk size
- Swap: Disabled for Kubernetes compatibility

**Required on all Proxmox nodes** that will host K3s VMs.

## Comparison with Working VMs

### VM 107 on pve.maas
```
VMID: 107
Name: k3s-vm-pve
IP: 192.168.4.227
Memory: 49152MB
Cores: 10
SCSI Controller: virtio-scsi-pci ✅
Cloud-init: local:snippets/install-k3sup-qemu-agent.yaml ✅
Machine: i440fx ✅
```

### VM 109 on chief-horse.maas
```
VMID: 109
Name: k3s-vm-chief-horse
IP: 192.168.4.228
Memory: 49152MB
Cores: 10
SCSI Controller: virtio-scsi-pci ✅
Cloud-init: local:snippets/install-k3sup-qemu-agent.yaml ✅
Machine: i440fx ✅
```

### VM 105 on pumped-piglet.maas (THIS VM)
```
VMID: 105
Name: k3s-vm-pumped-piglet
IP: 192.168.4.208
Memory: 49152MB
Cores: 10
SCSI Controller: virtio-scsi-pci ✅ (Fixed)
Cloud-init: local:snippets/install-k3sup-qemu-agent.yaml ✅ (Fixed)
Machine: i440fx ✅ (Fixed)
```

## Next Steps

### Phase 4: K3s Bootstrap (Currently Failing)
**Issue**: Bootstrap script tries to connect to failed still-fawn node (192.168.4.238)

**Required**:
1. Update K3s master node reference from still-fawn to working master
2. Join pumped-piglet K3s VM to existing cluster
3. Migrate workloads from still-fawn to pumped-piglet

**Reference**: Migration script phase 4 starting at line 473 in `pumped_piglet_migration.py`

## Lessons Learned

### Critical Requirements for K3s VMs on Proxmox
1. **SCSI Controller**: MUST be `virtio-scsi-pci` - without it, VM can't boot
2. **Cloud-init Snippet**: MUST exist on the Proxmox node and be referenced in VM config
3. **Machine Type**: Use default `i440fx`, NOT `q35` (unless GPU passthrough tested)
4. **Guest Agent**: MUST be installed and enabled for IP detection
5. **Hostname Resolution**: Never use "localhost" with ProxmoxClient - use actual node name

### Common Pitfalls
- Assuming cloud-init snippets are synced across all nodes (they're not)
- Forgetting SCSI controller configuration (VM creates successfully but won't boot)
- Using GPU passthrough without thorough testing (causes boot failures)
- Using "localhost" instead of node name for API calls (hostname resolution fails)

### Best Practices
- Always compare new VM config with working VMs using `qm config`
- Test VM boot and network before proceeding to K3s installation
- Use state-based migration scripts for resume capability
- Clear state file (`/tmp/pumped_piglet_migration.json`) for fresh runs
- Wait ~35-40s for guest agent to start before checking IP

## Files Modified

### `/Users/10381054/code/home/proxmox/homelab/src/homelab/pumped_piglet_migration.py`
**Changes**:
- Line 169: Changed `ProxmoxClient("localhost")` to `ProxmoxClient(self.NODE)`
- Line 401: Added `f"qm set {vmid} --scsihw virtio-scsi-pci"`
- Line 412: Added `f"qm set {vmid} --cicustom user=local:snippets/install-k3sup-qemu-agent.yaml"`
- Lines 392-415: Removed GPU passthrough configuration

### Git Commits
1. `3fb8d35` - "fix: add cloud-init snippet to VM creation"
2. `d0e8a24` - "fix: use node name instead of localhost for Proxmox API"
3. `cb4628d` - "fix: remove GPU passthrough from VM creation"
4. `6bd16f1` - "fix: add SCSI controller configuration for VM boot"

## References

- **Cloud-init Snippet**: `/var/lib/vz/snippets/install-k3sup-qemu-agent.yaml`
- **Migration Script**: `proxmox/homelab/src/homelab/pumped_piglet_migration.py`
- **VM Manager**: `proxmox/homelab/src/homelab/vm_manager.py`
- **Proxmox API**: `proxmox/homelab/src/homelab/proxmox_api.py`

## Tags

proxmox, proxmocks, k3s, k8s, kubernetes, kubernettes, vm-creation, vm, cloud-init, cloudinit, scsi, scsihw, virtio-scsi-pci, pumped-piglet, migration, gpu-passthrough, qemu-guest-agent, ubuntu, noble, troubleshooting, troublshoot
