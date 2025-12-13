# Coral TPU Migration: From AMD to NVIDIA for GPU-Accelerated Face Recognition

*Moving Coral USB TPU to pumped-piglet for the best of both worlds*

---

```
    BEFORE (still-fawn)              AFTER (pumped-piglet)
    +-----------------+              +-------------------+
    | Coral TPU: 28ms |              | Coral TPU: 19ms   |
    | AMD RX 580      |      ->      | RTX 3070          |
    | Face rec: CPU   |              | Face rec: GPU     |
    | CPU: 27-62%     |              | CPU: 8.5%         |
    +-----------------+              +-------------------+
```

## The Problem

After deploying Frigate 0.16 with Coral TPU on still-fawn, I had a working setup but with a significant flaw:

| Component | Performance |
|-----------|-------------|
| Coral TPU detection | 28ms (acceptable) |
| AMD VAAPI decode | Working |
| Face recognition | **62% CPU** (ouch) |

The AMD RX 580 can't accelerate face recognition - ROCm 6.x dropped Polaris support. Every face detection event caused CPU spikes from 27% baseline to 62%.

Meanwhile, the RTX 3070 on pumped-piglet was running ONNX detection at 45% CPU with no Coral.

**Solution**: Move Coral to pumped-piglet. Get Coral detection efficiency + NVIDIA GPU face recognition.

## The Migration

### Script Everything

User feedback from previous sessions was clear: *"Use scripts for even one-liners."*

Created 8 scripts in `scripts/frigate/pumped-piglet-coral/`:

```
01-check-coral-on-host.sh      # Verify Coral on Proxmox host
02-setup-usb-passthrough.sh    # Configure USB passthrough
03-restart-vm.sh               # Restart VM to apply changes
04-check-coral-in-vm.sh        # Verify Coral visible in VM
05-install-libedgetpu.sh       # Install libedgetpu runtime
06-label-k8s-node.sh           # Add coral.ai/tpu=usb label
08-deploy-and-verify.sh        # Deploy and verify
09-cleanup-still-fawn.sh       # Remove old USB config
```

### The SSH Gotcha

k3s-vm-pumped-piglet-gpu doesn't have SSH access. Discovery happened mid-migration:

```bash
ssh ubuntu@k3s-vm-pumped-piglet-gpu
# Connection refused
```

**Solution**: Use Proxmox guest agent commands instead:

```bash
ssh root@pumped-piglet.maas "qm guest exec 105 -- apt-get install -y libedgetpu1-std"
```

This should have been documented from previous work. Lesson learned.

### USB 3.0 Passthrough

Both Coral USB IDs need passthrough - the device presents different IDs during initialization:

```bash
qm set 105 --usb0 host=1a6e:089a,usb3=1  # Bootloader mode
qm set 105 --usb1 host=18d1:9302,usb3=1  # Initialized mode
```

The `usb3=1` flag is critical. Without it, Coral runs at USB 2.0 speeds with ~80ms inference instead of ~20ms.

### K8s Manifest Changes

**deployment.yaml**:
- Image: `frigate:0.16.0` (not tensorrt - regular image has Coral support)
- USB volume enabled: `/dev/bus/usb` mounted

**configmap.yaml**:
```yaml
detectors:
  coral:
    type: edgetpu
    device: usb
```

## The MetalLB Incident

After deployment, `frigate.app.homelab` didn't work. Investigation:

```bash
kubectl get svc traefik -n kube-system
# EXTERNAL-IP: <pending>
```

Traefik had no IP. MetalLB events showed:

```
AllocationFailed: can't change sharing key for "kube-system/traefik",
address also in use by frigate/frigate-webrtc-udp
```

A redundant `frigate-webrtc-udp` service had grabbed IP 192.168.4.80 (Traefik's IP). MetalLB wouldn't share between services with different sharing keys.

**Fix**: Delete the redundant service. The main frigate service already includes port 8555/UDP.

```bash
kubectl delete svc frigate-webrtc-udp -n frigate
# Traefik immediately recovered to 192.168.4.80
```

**Lesson**: Don't create separate services for WebRTC UDP. Include all ports in the main service.

## Results

| Metric | still-fawn (AMD) | pumped-piglet (NVIDIA) |
|--------|------------------|------------------------|
| **Coral inference** | 28ms | **19ms** |
| **CPU baseline** | 27% | **8.5%** |
| **CPU w/ face rec** | 62% | **8.5%** |
| **Face recognition** | CPU fallback | **GPU accelerated** |
| **GPU memory** | N/A | 3.5GB / 8GB |

The RTX 3070 handles everything face recognition throws at it without touching CPU. Combined with Coral's efficient detection, this is the optimal Frigate 0.16 setup.

## Key Takeaways

### 1. Script Everything
Even one-liners. Especially for multi-step operations where you might forget a flag.

### 2. Document VM Access Methods
Not all VMs have SSH. Know which VMs need `qm guest exec` before starting work.

### 3. USB 3.0 Flag Matters
```bash
qm set VMID --usb0 host=VID:PID,usb3=1
#                              ^^^^^^
```

### 4. Regular Frigate Image Supports Coral + NVIDIA
No need for the tensorrt image when using Coral for detection. The regular image supports both Coral EdgeTPU and NVIDIA NVDEC.

### 5. MetalLB IP Conflicts Are Silent
Services can steal IPs from each other during reconciliation. Check `kubectl describe svc` for `AllocationFailed` events.

## Final Architecture

```
pumped-piglet.maas (Proxmox)
└── VM 105: k3s-vm-pumped-piglet-gpu
    ├── Coral USB TPU
    │   └── Object detection: 19ms inference
    ├── RTX 3070 (PCI passthrough)
    │   ├── Video decode: NVDEC
    │   ├── Face recognition: GPU accelerated
    │   └── Video encode: NVENC (for birdseye)
    └── Frigate 0.16.0
        └── CPU: 8.5%
```

---

*Tags: frigate, coral, coral-tpu, nvidia, rtx3070, gpu, face-recognition, k8s, kubernetes, proxmox, usb-passthrough, metallb, migration*
