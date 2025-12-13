# Action Log: Frigate 0.16 K8s - Coral Migration to pumped-piglet

**Date**: 2025-12-12
**Operator**: Claude Code AI Agent
**GitHub Issue**: N/A (homelab improvement)
**Target Host**: pumped-piglet.maas
**K8s VM**: k3s-vm-pumped-piglet-gpu (VMID: 105)
**Status**: Completed

---

## Summary

Successfully migrated Coral USB TPU from still-fawn to pumped-piglet, achieving optimal configuration:
- **Coral TPU**: Object detection at 19ms inference
- **NVIDIA RTX 3070**: Video decode (NVDEC) + face recognition (GPU accelerated)
- **CPU reduction**: 27% → 8.5% (face recognition now on GPU instead of CPU)

---

## Pre-Operation State

### Infrastructure
| Component | Value |
|-----------|-------|
| Proxmox Host | pumped-piglet.maas |
| K8s VM Name | k3s-vm-pumped-piglet-gpu |
| K8s VM VMID | 105 |
| GPU | RTX 3070 (passed through) |
| Coral Location | still-fawn.maas (before migration) |

### Previous Configuration (still-fawn)
| Metric | Value |
|--------|-------|
| Coral inference | 28ms |
| CPU baseline | 27% |
| CPU with face recognition | 62% (CPU fallback) |
| Face recognition | Working but expensive |

---

## Execution Log

### Phase 1: Physical Move (User Action)
**Timestamp**: 2025-12-12 ~21:00
- User unplugged Coral USB from still-fawn
- User plugged Coral USB into pumped-piglet USB 3.0 port
- Verified on host: `1a6e:089a` (bootloader mode, USB 3.0 at 5000Mbps)

### Phase 2: USB Passthrough
**Timestamp**: 2025-12-12 21:27
**Script**: `scripts/frigate/pumped-piglet-coral/02-setup-usb-passthrough.sh`
```
usb0: host=1a6e:089a,usb3=1
usb1: host=18d1:9302,usb3=1
```
**Note**: Both Coral USB IDs configured (bootloader + initialized states)

### Phase 3: VM Restart
**Timestamp**: 2025-12-12 21:27
**Script**: `scripts/frigate/pumped-piglet-coral/03-restart-vm.sh`
- VM 105 stopped and started
- Waited 60 seconds for boot
- Coral visible in VM at Bus 010 Device 002

### Phase 4: Install libedgetpu
**Timestamp**: 2025-12-12 21:30
**Script**: `scripts/frigate/pumped-piglet-coral/05-install-libedgetpu.sh`
**CRITICAL**: SSH doesn't work on this VM - used `qm guest exec` instead
```bash
ssh root@pumped-piglet.maas "qm guest exec 105 -- apt-get install -y libedgetpu1-std"
```
**Result**: libedgetpu1-std version 16.0 installed

### Phase 5: Label K8s Node
**Timestamp**: 2025-12-12 21:31
**Script**: `scripts/frigate/pumped-piglet-coral/06-label-k8s-node.sh`
```bash
kubectl label node k3s-vm-pumped-piglet-gpu coral.ai/tpu=usb
```

### Phase 6: Update K8s Manifests
**Timestamp**: 2025-12-12 21:35-21:36
**Files Modified**:
- `k8s/frigate-016/deployment.yaml`: Image changed to `frigate:0.16.0` (not tensorrt), USB volume enabled
- `k8s/frigate-016/configmap.yaml`: Detector changed from `cpu` to `coral` (edgetpu)

### Phase 7: Deploy and Verify
**Timestamp**: 2025-12-12 21:37
**Script**: `scripts/frigate/pumped-piglet-coral/08-deploy-and-verify.sh`
- Applied configmap and deployment
- Rollout completed successfully
- Pod running on k3s-vm-pumped-piglet-gpu

### Phase 8: Cleanup still-fawn
**Timestamp**: 2025-12-12 21:42
```bash
ssh root@still-fawn.maas "qm set 108 --delete usb0"
```
- Removed USB passthrough from still-fawn VM 108

---

## Issues Encountered

### Issue 1: SSH Not Working on pumped-piglet GPU VM
**Severity**: Medium
**Symptoms**: SSH connection refused to k3s-vm-pumped-piglet-gpu
**Root Cause**: VM network configuration doesn't expose SSH
**Resolution**: Used `qm guest exec` via Proxmox host instead
**Prevention**: Document SSH limitations per VM, always use scripts that handle this

### Issue 2: Running Ad-hoc Commands Instead of Scripts
**Severity**: Low (process issue)
**Symptoms**: User frustration at inconsistent approach
**Root Cause**: Not following established script-based workflow
**Resolution**: Created proper scripts in `scripts/frigate/pumped-piglet-coral/`
**Prevention**: "Use scripts for everything, even one-liners"

### Issue 3: Traefik IP Stolen by frigate-webrtc-udp
**Severity**: High
**Timestamp**: 2025-12-12 21:48
**Symptoms**: frigate.app.homelab not accessible, Traefik service showing `<pending>` IP
**Root Cause**: `frigate-webrtc-udp` service took IP 192.168.4.80 which was Traefik's IP
**Resolution**: Deleted redundant frigate-webrtc-udp service (ports already in main frigate service)
**Prevention**: Don't create separate WebRTC services; include all ports in main service

---

## Final Results

| Metric | still-fawn (AMD RX 580) | pumped-piglet (RTX 3070) |
|--------|-------------------------|--------------------------|
| **CPU baseline** | 27% | **8.5%** |
| **CPU w/ face rec** | 62% | **8.5%** |
| **Coral inference** | 28ms | **19.17ms** |
| **Video decode** | AMD VAAPI | NVIDIA CUDA/NVDEC |
| **Face recognition** | CPU (slow) | **NVIDIA GPU (fast)** |
| **GPU memory** | N/A | 3.5GB / 8GB |
| **GPU utilization** | N/A | 1% |

---

## Scripts Created

| Script | Purpose |
|--------|---------|
| `01-check-coral-on-host.sh` | Verify Coral on Proxmox host |
| `02-setup-usb-passthrough.sh` | Configure USB passthrough |
| `03-restart-vm.sh` | Restart VM to apply changes |
| `04-check-coral-in-vm.sh` | Verify Coral visible in VM |
| `05-install-libedgetpu.sh` | Install libedgetpu (uses qm guest exec) |
| `06-label-k8s-node.sh` | Add coral.ai/tpu=usb label |
| `08-deploy-and-verify.sh` | Deploy Frigate and verify |
| `09-cleanup-still-fawn.sh` | Remove USB config from still-fawn |

---

## Key Lessons

1. **SSH doesn't work on k3s-vm-pumped-piglet-gpu** - Use `qm guest exec` instead
2. **Use scripts for everything** - Even one-liners should be scripted
3. **USB 3.0 flag is critical** - Always use `usb3=1` for Coral passthrough
4. **Regular image works with Coral + NVIDIA** - No need for tensorrt image
5. **Don't create redundant services** - WebRTC ports already in main service

---

## Tags

frigate, coral, tpu, usb, k8s, kubernetes, gpu, rtx3070, nvidia, face-recognition, pumped-piglet, migration, action-log
