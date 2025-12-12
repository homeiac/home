# Frigate 0.16 ONNX Models

This directory contains ONNX models for GPU-accelerated object detection in Frigate 0.16+.

## YOLOv9 ONNX Model

Frigate 0.16 removed built-in TensorRT support and requires users to provide their own ONNX models for GPU detection.

### Building the Model

To build the YOLOv9-c ONNX model:

```bash
cd /Users/10381054/code/home/k8s/frigate-016/models
/Users/10381054/code/home/scripts/frigate/build-yolov9-onnx.sh c 640
```

This will create `yolov9-c-640.onnx` in the current directory.

**Requirements:**
- Docker installed and running
- ~20-25 GB available disk space
- 5-15 minutes build time

**Build arguments:**
- First argument: Model size (t=tiny, c=small-medium, e/m=large)
- Second argument: Input image size in pixels (320-1280)

### Model Details

**YOLOv9-c-640.onnx:**
- Model size: c (small-medium, balanced performance)
- Input size: 640x640 pixels
- Input format: RGB, NCHW tensor layout
- Data type: float32
- Use case: General object detection (person, car, etc.)

### Using the Model in Frigate

1. Ensure the model exists in this directory
2. Apply the ONNX configmap:
   ```bash
   kubectl apply -f /Users/10381054/code/home/k8s/frigate-016/configmap-onnx.yaml
   ```
3. Restart Frigate to load the new detector configuration

### Performance Comparison

**CPU Detector (current):**
- Inference time: ~10ms per frame
- Hardware: NVIDIA GPU not utilized for detection
- Sufficient for 3 cameras at 5 fps

**ONNX GPU Detector (optional):**
- Inference time: Expected <5ms per frame with CUDA
- Hardware: NVIDIA GPU utilized for detection
- Better for scaling to more cameras or higher fps

### References

- Build script: `/Users/10381054/code/home/scripts/frigate/build-yolov9-onnx.sh`
- Blog post: https://ioritro.com/blog/2025-09-01-frigate-onnx-detection-model/
- YOLOv9 repository: https://github.com/WongKinYiu/yolov9
- Ultralytics ONNX export: https://docs.ultralytics.com/integrations/onnx/

## Model Not Included

The ONNX model file is **not included in git** due to its large size (~50-100 MB).
You must build it locally using the script above before deploying the ONNX configuration.
