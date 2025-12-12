# Frigate 0.16 K8s Deployment with GPU Detection Options

## Overview

This deployment runs Frigate 0.16 on K8s with multiple detection options:
- **CPU Detector** (default): 10ms inference, sufficient for 3 cameras
- **ONNX GPU Detector** (optional): <5ms inference with NVIDIA CUDA
- **NVIDIA RTX 3070 GPU** for hardware acceleration (NVDEC/NVENC) and face recognition
- **MetalLB LoadBalancer** for external access

**Note**: Frigate 0.16 removed built-in TensorRT support. For GPU detection, use the ONNX detector with YOLOv9 models.

## Prerequisites

1. **Hardware**
   - RTX 3070 passed through to k3s-vm-pumped-piglet-gpu (VMID 105)

2. **K8s Cluster Ready**
   - NVIDIA GPU Operator running
   - Node labeled: `nvidia.com/gpu.present=true`

## Deployment

### Pre-Flight Check

```bash
# Verify GPU node is ready
KUBECONFIG=~/kubeconfig kubectl get nodes -l nvidia.com/gpu.present=true

# Check NVIDIA device plugin
KUBECONFIG=~/kubeconfig kubectl get pods -n gpu-operator | grep nvidia

# Verify GPU is available
KUBECONFIG=~/kubeconfig kubectl describe node k3s-vm-pumped-piglet-gpu | grep -A5 "Allocatable:" | grep nvidia
```

### Manual Deployment (First Time)

**Option 1: CPU Detector (Default)**
```bash
# Apply manifests with CPU detector
KUBECONFIG=~/kubeconfig kubectl apply -k k8s/frigate-016/

# Monitor pod startup
KUBECONFIG=~/kubeconfig kubectl get pods -n frigate -w

# Check logs for detector initialization
KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate | grep -i "detector"
```

**Option 2: ONNX GPU Detector (Requires Model Build)**
```bash
# Build YOLOv9 ONNX model first (5-15 minutes)
cd /Users/10381054/code/home/k8s/frigate-016/models
/Users/10381054/code/home/scripts/frigate/build-yolov9-onnx.sh c 640

# Apply ONNX configmap instead of default
KUBECONFIG=~/kubeconfig kubectl apply -f k8s/frigate-016/namespace.yaml
KUBECONFIG=~/kubeconfig kubectl apply -f k8s/frigate-016/pvc.yaml
KUBECONFIG=~/kubeconfig kubectl apply -f k8s/frigate-016/configmap-onnx.yaml
KUBECONFIG=~/kubeconfig kubectl apply -f k8s/frigate-016/deployment.yaml
KUBECONFIG=~/kubeconfig kubectl apply -f k8s/frigate-016/service.yaml
KUBECONFIG=~/kubeconfig kubectl apply -f k8s/frigate-016/ingress.yaml

# Copy model to PVC (one-time setup)
POD=$(KUBECONFIG=~/kubeconfig kubectl get pod -n frigate -l app=frigate -o jsonpath='{.items[0].metadata.name}')
KUBECONFIG=~/kubeconfig kubectl cp k8s/frigate-016/models/yolov9-c-640.onnx frigate/$POD:/config/models/yolov9-c-640.onnx

# Monitor pod startup
KUBECONFIG=~/kubeconfig kubectl get pods -n frigate -w
```

### GitOps Deployment (After Verification)

Copy to gitops directory:
```bash
cp -r k8s/frigate-016/* gitops/clusters/homelab/apps/frigate/
```

## Verification

### Check Detector Status
```bash
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- \
  curl -s http://localhost:5000/api/stats | jq '.detectors'
```

**Expected inference speeds:**
- CPU detector: ~10ms (sufficient for 3 cameras)
- ONNX GPU detector: <5ms (better for scaling or higher fps)

### Check GPU Usage
```bash
KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate | grep -i "nvidia\|cuda\|onnx"

# Monitor GPU utilization inside pod
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- nvidia-smi

# Check ONNX GPU acceleration (if using ONNX detector)
KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate | grep -i "onnx.*cuda"
```

### Check Face Recognition
```bash
KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate | grep -i "face"
```

### Access UI

**Via Domain Name (Recommended):**
```bash
# Access via Traefik ingress
http://frigate.homelab
```

**DNS Configuration Required:**
- Add DNS override in OPNsense Unbound DNS:
  - Navigate: Services → Unbound DNS → Overrides
  - Add Host Override: `frigate.homelab` → `192.168.4.80` (Traefik LoadBalancer)

**Via Direct LoadBalancer IP:**
```bash
KUBECONFIG=~/kubeconfig kubectl get svc -n frigate
# Open http://<EXTERNAL-IP>:5000 (currently 192.168.4.83:5000)
```

## Detector Selection Guide

### CPU Detector (Default)
**Use when:**
- Running 3-5 cameras at 5 fps
- 10ms inference is acceptable
- Want to reserve GPU for face recognition and encoding only
- Simplicity over maximum performance

### ONNX GPU Detector
**Use when:**
- Need <5ms inference for faster detection
- Scaling to more cameras (6+) or higher fps
- Want GPU-accelerated object detection
- Have NVIDIA GPU available

**Trade-off**: GPU shared between detection, face recognition, and encoding

### Building ONNX Model
See `models/README.md` for complete instructions:
```bash
cd /Users/10381054/code/home/k8s/frigate-016/models
/Users/10381054/code/home/scripts/frigate/build-yolov9-onnx.sh c 640
```

## Adding Coral TPU (Optional)

If GPU load is too high, uncomment Coral TPU support:

1. Run `setup-coral-usb-passthrough.sh` on pumped-piglet host
2. Edit `configmap.yaml`: Change detector from `tensorrt` to `edgetpu`
3. Edit `deployment.yaml`: Uncomment USB volume mounts
4. Restart pod: `kubectl rollout restart deployment/frigate -n frigate`

## Troubleshooting

### ONNX GPU Detector Not Working
1. Check NVIDIA runtime: `kubectl describe pod -n frigate | grep -i runtime`
2. Verify GPU access: `kubectl exec -n frigate deployment/frigate -- nvidia-smi`
3. Check model exists: `kubectl exec -n frigate deployment/frigate -- ls -lh /config/models/`
4. Check Frigate logs: `kubectl logs -n frigate deployment/frigate | grep -i "onnx\|error"`
5. Verify CUDA support: `kubectl logs -n frigate deployment/frigate | grep -i cuda`

### Pod Not Scheduling
1. Check node selector: `kubectl get nodes -l nvidia.com/gpu.present=true`
2. Check GPU availability: `kubectl describe node | grep nvidia.com/gpu`
3. Check events: `kubectl get events -n frigate --sort-by='.lastTimestamp'`

### Face Recognition Not Working
- Face recognition requires Frigate 0.16.0+ with GPU
- Check model download: `kubectl logs -n frigate deployment/frigate | grep -i "face.*model"`

## Files

| File | Purpose |
|------|---------|
| namespace.yaml | Create frigate namespace |
| pvc.yaml | Config (1Gi) and media (200Gi) storage |
| configmap.yaml | Frigate configuration (CPU detector, default) |
| configmap-onnx.yaml | Frigate configuration (ONNX GPU detector) |
| deployment.yaml | Frigate pod with GPU access |
| service.yaml | LoadBalancer services |
| ingress.yaml | Traefik ingress for frigate.homelab domain |
| kustomization.yaml | Kustomize manifest (uses CPU detector) |
| setup-coral-usb-passthrough.sh | Optional: Coral USB setup script |
| models/README.md | ONNX model building instructions |
| models/.gitignore | Exclude large ONNX files from git |

## Home Assistant Integration

Update Frigate integration URL (choose one):
- **Recommended**: `http://frigate.homelab` (via ingress, requires DNS override)
- **Alternative**: `http://192.168.4.83:5000` (direct LoadBalancer IP)

## Architecture

```
pumped-piglet (Proxmox Host)
├── RTX 3070 GPU (VFIO passthrough)
└── k3s-vm-pumped-piglet-gpu (VMID 105)
    ├── GPU: passed through
    └── Frigate 0.16 Pod
        ├── Detection Options:
        │   ├── CPU: ~10ms (default, 3 cameras)
        │   └── ONNX GPU: <5ms (optional, YOLOv9)
        ├── NVDEC: Hardware video decoding
        ├── NVENC: Hardware video encoding (h264_nvenc)
        └── GPU: Face recognition (0.16+ feature)

Optional Future:
├── Coral USB TPU (from still-fawn)
└── USB passthrough for ~8ms detection
```

## References

- **YOLOv9 ONNX Build Guide**: https://ioritro.com/blog/2025-09-01-frigate-onnx-detection-model/
- **Ultralytics ONNX Export**: https://docs.ultralytics.com/integrations/onnx/
- **YOLOv9 Repository**: https://github.com/WongKinYiu/yolov9
- **Frigate 0.16 Docs**: https://docs.frigate.video/
