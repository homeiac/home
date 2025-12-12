# Switching Frigate 0.16 from CPU to GPU Detection (ONNX)

*December 12, 2025*

I noticed my Frigate pod was constantly using 2+ CPU cores just for object detection. With an RTX 3070 sitting right there doing nothing but video decoding, that seemed wasteful. Here's how I switched to GPU-accelerated detection and freed up 1.6 cores.

## The Problem

Frigate 0.16 was running with CPU detection:

```
CPU usage: 2094m (2.1 cores)
Inference: 19ms per frame
Detector: cpu (4 threads)
```

For 3 cameras at 5 fps, that's 15 inferences per second eating 21% of the pod's available CPU. Meanwhile, the RTX 3070 was only handling NVDEC (video decoding) and face recognition.

## The Confusion: TensorRT Image Doesn't Mean Built-in Detection

I was using `ghcr.io/blakeblackshear/frigate:0.16.0-tensorrt` and assumed GPU detection was automatic. Wrong.

**Frigate 0.16 removed built-in TensorRT detector models.** The `-tensorrt` tag means:
- TensorRT is the *backend* that accelerates ONNX model inference
- You still need to *provide your own ONNX model*

From the [Frigate docs](https://docs.frigate.video/configuration/object_detectors/):

> "The TensorRT detector has been removed for Nvidia GPUs, the ONNX detector should be used instead."

## The Solution: Build YOLOv9 ONNX Model via K8s Job

Since my Mac is ARM and the model needs x86_64, I built it on the cluster using a K8s Job.

### Script: build-onnx-k8s-job.sh

```bash
#!/bin/bash
# Creates a K8s Job that:
# 1. Pulls python:3.11-slim
# 2. Clones YOLOv9 repo
# 3. Downloads pretrained weights
# 4. Exports to ONNX format
# 5. Writes to frigate-config PVC

./scripts/frigate/build-onnx-k8s-job.sh c 640
```

The job runs on the GPU node (via `nodeSelector: nvidia.com/gpu.present`) and writes directly to the PVC. No file transfers needed.

**Gotchas I hit:**
1. `python:3.11-slim` doesn't have `curl` - added to apt-get
2. PyTorch ONNX export needs `onnxscript` - added to pip install
3. Model is 97MB, not 50MB as expected

### Script: 19-switch-to-onnx-detector.sh

```bash
#!/bin/bash
# 1. Verifies model exists at /config/yolov9-c-640.onnx
# 2. Fixes configmap path (was /config/models/..., should be /config/...)
# 3. Applies ONNX configmap
# 4. Restarts Frigate
# 5. Shows before/after stats
```

## The Results

| Metric | Before (CPU) | After (ONNX GPU) |
|--------|--------------|------------------|
| **CPU usage** | 2094m | 433m |
| **Inference** | 19ms | 10ms |
| **Cores freed** | - | ~1.6 |

**79% CPU reduction.** The GPU now handles detection alongside face recognition and video encoding.

## Configuration

The ONNX configmap (`configmap-onnx.yaml`):

```yaml
detectors:
  onnx:
    type: onnx

model:
  path: /config/yolov9-c-640.onnx
  input_tensor: nchw
  input_pixel_format: rgb
  width: 640
  height: 640
  model_type: yolo-generic
  input_dtype: float
```

Key detail: the model path is `/config/yolov9-c-640.onnx`, not `/config/models/...`. The K8s Job writes directly to `/config/` on the PVC.

## Rollback

If ONNX detection causes issues:

```bash
kubectl apply -f k8s/frigate-016/configmap.yaml
kubectl rollout restart deployment/frigate -n frigate
```

This switches back to CPU detection.

## When to Use This

**Do this if:**
- You have an NVIDIA GPU passed through to K8s
- CPU detection is using significant resources (>1 core)
- You want faster inference times

**Skip this if:**
- CPU detection is fine for your camera count
- You don't have GPU passthrough set up
- 10ms vs 19ms inference doesn't matter for your use case

## The Scripts

| Script | Purpose |
|--------|---------|
| `scripts/frigate/build-onnx-k8s-job.sh` | Build YOLOv9 ONNX model via K8s Job |
| `scripts/frigate/19-switch-to-onnx-detector.sh` | Switch from CPU to ONNX detector |
| `k8s/frigate-016/configmap-onnx.yaml` | ONNX detector configuration |

## Key Takeaways

1. **Frigate 0.16 requires your own ONNX models** - the `-tensorrt` image is just the runtime, not built-in models

2. **Build on the cluster, not locally** - K8s Jobs are perfect for ARM Mac users who need x86_64 artifacts

3. **Model writes to PVC directly** - no kubectl cp or file transfer gymnastics needed

4. **Path matters** - the Job writes to `/config/`, not `/config/models/`

5. **GPU can do it all** - detection, face recognition, NVDEC, NVENC all on one RTX 3070 without breaking a sweat

---

*Scripts: [github.com/homeiac/home/scripts/frigate](https://github.com/homeiac/home/tree/master/scripts/frigate)*
