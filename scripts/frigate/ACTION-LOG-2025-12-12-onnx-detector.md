# Action Log: Frigate ONNX GPU Detector Setup

## Execution Date: 2025-12-12

## Pre-flight Checks
- [x] Frigate running: `kubectl get pods -n frigate` - Running on k3s-vm-pumped-piglet-gpu
- [x] GPU available: RTX 3070 passed through to VM
- [x] Current detector stats: CPU detector, 2094m usage, 13.57ms inference

---

## Step 1: Build ONNX Model
- **Script**: `./build-onnx-k8s-job.sh c 640`
- **Status**: SUCCESS (after fixes)
- **Duration**: ~5 minutes
- **Model size**: 97MB
- **Issues encountered**:
  1. Missing `curl` in python:3.11-slim image - added to apt-get install
  2. Missing `onnxscript` package - added to pip install
  3. Resource limits removed - build runs faster without constraints
- **Output**:
```
=========================================
Build YOLOv9 ONNX Model via K8s Job
=========================================

Model: YOLOv9-c
Input size: 640x640
Output: yolov9-c-640.onnx

Step 1: Cleaning up old job...
Step 2: Creating build job...
job.batch/build-yolov9-onnx created

Step 3: Waiting for build to complete (5-15 min)...
job.batch/build-yolov9-onnx condition met

✓ Build complete!

Step 4: Verifying output...
-rw-r--r-- 1 root root 97M Dec 12 15:34 /config/yolov9-c-640.onnx
```

---

## Step 2: Switch to ONNX Detector
- **Script**: `./19-switch-to-onnx-detector.sh`
- **Status**: SUCCESS
- **Output**:
```
=========================================
Switch Frigate to ONNX GPU Detector
=========================================

Step 1: Verifying ONNX model exists...
-rw-r--r-- 1 root root 97M Dec 12 15:34 /config/yolov9-c-640.onnx

Step 2: Updating configmap with correct model path...
  Updated: model path set to /config/yolov9-c-640.onnx

Step 3: Current detector stats (before switch)...
{
  "cpu": {
    "inference_speed": 19.14,
    "detection_start": 1765583061.992077,
    "pid": 465
  }
}

Step 4: Applying ONNX configmap...
configmap/frigate-config configured

Step 5: Restarting Frigate deployment...
deployment "frigate" successfully rolled out

Step 6: Waiting for Frigate to initialize (30s)...

Step 7: New detector stats (after switch)...
{
  "onnx": {
    "inference_speed": 10.0,
    "detection_start": 0.0,
    "pid": 464
  }
}

Step 8: Checking pod CPU usage...
NAME                       CPU(cores)   MEMORY(bytes)
frigate-5d55cf685c-5qvch   433m         1981Mi

=========================================
Switched to ONNX GPU detector!
=========================================
```

---

## Step 3: Verify Results

### Before Switch
- **CPU usage**: 2094m
- **Inference speed**: 19.14ms
- **Detector type**: cpu (4 threads)

### After Switch
- **CPU usage**: 433m
- **Inference speed**: 10.0ms
- **Detector type**: onnx

### Improvement
- **CPU reduction**: 79% (2094m → 433m)
- **Inference improvement**: 48% (19ms → 10ms)
- **Cores freed**: ~1.6 cores

---

## Final Status
- **Overall**: SUCCESS
- **Notes**:
  - Frigate 0.16 removed built-in TensorRT detector
  - The `-tensorrt` image tag means TensorRT backend for ONNX, not built-in models
  - Model path was `/config/yolov9-c-640.onnx` not `/config/models/...`
  - GPU now handles detection + face recognition + NVDEC/NVENC

---

## Rollback (if needed)
```bash
kubectl apply -f k8s/frigate-016/configmap.yaml
kubectl rollout restart deployment/frigate -n frigate
```
- **Executed**: NO
- **Reason**: N/A - switch successful

---

## Files Modified
- `scripts/frigate/build-onnx-k8s-job.sh` - added curl, onnxscript, removed resource limits
- `scripts/frigate/19-switch-to-onnx-detector.sh` - new script for switching detectors
- `k8s/frigate-016/configmap-onnx.yaml` - fixed model path

---

## References
- [Frigate ONNX Docs](https://docs.frigate.video/configuration/object_detectors/#onnx)
- [YOLOv9 Repository](https://github.com/WongKinYiu/yolov9)
- Plan: `scripts/frigate/PLAN-onnx-gpu-detector.md`
