# Switch Frigate Detection from CPU to GPU (ONNX)

## Status: COMPLETED (2025-12-12)

## Problem Statement

Frigate K8s deployment is using **CPU detection** which consumes ~2.1 cores (21% of pod) constantly. This can be offloaded to GPU using ONNX detector, reducing CPU usage to ~2% while maintaining or improving inference speed.

## Current State Investigation

### Resource Usage (Before)
| Metric | Value |
|--------|-------|
| Pod CPU | 2094m (2.1 cores) |
| Available vCPUs | 10 |
| CPU % of pod | ~21% constant |
| Inference speed | 13.57ms |
| Detector type | CPU (4 threads) |

### Hardware Available
- **GPU**: NVIDIA RTX 3070 (already passed through to K3s VM)
- **Current GPU usage**: NVDEC (decode), NVENC (encode), face recognition
- **Coral TPU**: Not plugged in anywhere (would require physical action)

### Existing Infrastructure
| Item | Path | Status |
|------|------|--------|
| K8s Job build script | `scripts/frigate/build-onnx-k8s-job.sh` | EXISTS |
| ONNX configmap | `k8s/frigate-016/configmap-onnx.yaml` | EXISTS |
| ONNX model | `/config/yolov9-c-640.onnx` | BUILT |

## Solution: Use Existing K8s Job to Build ONNX Model

The infrastructure is already in place. Just need to:
1. Run the K8s Job to build the model on the GPU node
2. Apply the ONNX configmap
3. Restart Frigate

### Why K8s Job (not local Docker)
- Mac is ARM, model needs x86_64
- GPU node has the compute resources
- Model writes directly to frigate-config PVC
- No file transfer needed

---

## Implementation Plan

### Phase 1: Build ONNX Model via K8s Job
**Script**: `scripts/frigate/build-onnx-k8s-job.sh`

```bash
./scripts/frigate/build-onnx-k8s-job.sh c 640
```

This will:
1. Create K8s Job `build-yolov9-onnx` in frigate namespace
2. Run on GPU node (nodeSelector: nvidia.com/gpu.present)
3. Clone YOLOv9 repo, download weights, export to ONNX
4. Write `yolov9-c-640.onnx` to frigate-config PVC at `/config/`
5. Auto-cleanup after 300s (ttlSecondsAfterFinished)

**Duration**: 5-15 minutes
**Output**: `/config/yolov9-c-640.onnx` (97MB)

### Phase 1.5: Fix Path Mismatch

**Issue**: configmap-onnx.yaml expects `/config/models/yolov9-c-640.onnx` but Job writes to `/config/yolov9-c-640.onnx`

**Fix**: Update configmap model path to `/config/yolov9-c-640.onnx`

**Implemented in**: `19-switch-to-onnx-detector.sh` (uses sed to fix path)

### Phase 2: Switch to ONNX Detector

**Script**: `scripts/frigate/19-switch-to-onnx-detector.sh`

This will:
1. Verify model exists
2. Fix configmap model path
3. Apply ONNX configmap
4. Restart Frigate
5. Show before/after stats

### Phase 3: Verify GPU Detection

1. **Check detector stats**:
   ```bash
   KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- \
     curl -s http://localhost:5000/api/stats | jq '.detectors'
   ```
   Expected: `type: onnx`, inference_speed < 10ms

2. **Check CPU usage**:
   ```bash
   KUBECONFIG=~/kubeconfig kubectl top pod -n frigate
   ```
   Expected: ~500m instead of ~2100m

---

## Actual Results

| Metric | Before (CPU) | After (ONNX GPU) | Improvement |
|--------|--------------|------------------|-------------|
| CPU usage | 2094m | 433m | 79% reduction |
| Inference | 19.14ms | 10.0ms | 48% faster |
| Detector | cpu (4 threads) | onnx (CUDA) | GPU offload |
| Cores freed | - | ~1.6 | - |

---

## Critical Files

| File | Purpose |
|------|---------|
| `scripts/frigate/build-onnx-k8s-job.sh` | K8s Job to build ONNX model |
| `scripts/frigate/19-switch-to-onnx-detector.sh` | Switch from CPU to ONNX detector |
| `k8s/frigate-016/configmap-onnx.yaml` | ONNX detector configuration |
| `k8s/frigate-016/configmap.yaml` | CPU detector (for rollback) |

---

## Rollback Plan

If ONNX detection fails:
```bash
# Revert to CPU detector
KUBECONFIG=~/kubeconfig kubectl apply -f k8s/frigate-016/configmap.yaml
KUBECONFIG=~/kubeconfig kubectl rollout restart deployment/frigate -n frigate
```

---

## Lessons Learned

1. **Frigate 0.16 removed built-in TensorRT**: The `-tensorrt` image tag means TensorRT backend for ONNX, not built-in detector models
2. **python:3.11-slim missing curl**: Need to install curl for downloading weights
3. **onnxscript required**: PyTorch ONNX export requires onnxscript package
4. **Model path matters**: Job writes to `/config/` not `/config/models/`
5. **K8s Jobs for ARM Macs**: Build on cluster, not locally

---

## References
- [YOLOv9 Repository](https://github.com/WongKinYiu/yolov9)
- [Frigate ONNX Docs](https://docs.frigate.video/configuration/object_detectors/#onnx)
- Action Log: `scripts/frigate/ACTION-LOG-2025-12-12-onnx-detector.md`
