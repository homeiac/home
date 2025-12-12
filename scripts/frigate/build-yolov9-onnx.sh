#!/bin/bash
set -euo pipefail

# YOLOv9 ONNX Model Builder for Frigate 0.16+
# Based on: https://ioritro.com/blog/2025-09-01-frigate-onnx-detection-model/
#
# This script builds a YOLOv9 ONNX model using Docker multi-stage build.
# The model can be used with Frigate 0.16+ for GPU-accelerated object detection.
#
# Usage:
#   ./build-yolov9-onnx.sh [MODEL_SIZE] [IMG_SIZE]
#
# Arguments:
#   MODEL_SIZE: YOLOv9 model size (t=tiny, c=small-medium, e/m=large) [default: c]
#   IMG_SIZE: Input image size in pixels [default: 640]
#
# Output:
#   yolov9-{MODEL_SIZE}-{IMG_SIZE}.onnx in the current directory
#
# Requirements:
#   - Docker installed and running
#   - ~20-25 GB available disk space (SSD recommended)
#   - Internet connection to download YOLOv9 repository and weights
#
# Example:
#   ./build-yolov9-onnx.sh c 640  # Build YOLOv9-c with 640x640 input

# Configuration
MODEL_SIZE="${1:-c}"
IMG_SIZE="${2:-640}"
OUTPUT_FILE="yolov9-${MODEL_SIZE}-${IMG_SIZE}.onnx"

# Validate model size
case "$MODEL_SIZE" in
    t|c|e|m)
        echo "Building YOLOv9-${MODEL_SIZE} ONNX model with ${IMG_SIZE}x${IMG_SIZE} input size..."
        ;;
    *)
        echo "Error: Invalid MODEL_SIZE '${MODEL_SIZE}'"
        echo "Valid options: t (tiny), c (small-medium), e (large), m (large)"
        exit 1
        ;;
esac

# Validate image size
if ! [[ "$IMG_SIZE" =~ ^[0-9]+$ ]] || [ "$IMG_SIZE" -lt 320 ] || [ "$IMG_SIZE" -gt 1280 ]; then
    echo "Error: Invalid IMG_SIZE '${IMG_SIZE}'"
    echo "Valid range: 320-1280 pixels"
    exit 1
fi

# Check Docker is running
if ! docker info &>/dev/null; then
    echo "Error: Docker is not running or not accessible"
    echo "Please start Docker and try again"
    exit 1
fi

# Display disk space warning
echo ""
echo "WARNING: This build requires ~20-25 GB of disk space"
echo "         Build time: 5-15 minutes depending on your system"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Build cancelled"
    exit 0
fi

# Build the ONNX model using Docker multi-stage build
echo ""
echo "Starting Docker build..."
echo "This will:"
echo "  1. Pull Python 3.11 base image"
echo "  2. Clone YOLOv9 repository from GitHub"
echo "  3. Install PyTorch and ONNX dependencies"
echo "  4. Download YOLOv9-${MODEL_SIZE} pretrained weights"
echo "  5. Export model to ONNX format"
echo "  6. Simplify ONNX model for optimal inference"
echo ""

docker build . \
  --build-arg MODEL_SIZE="${MODEL_SIZE}" \
  --build-arg IMG_SIZE="${IMG_SIZE}" \
  --output . \
  -f- <<'EOF'
FROM python:3.11 AS build

# Install system dependencies
RUN apt-get update && \
    apt-get install --no-install-recommends -y git libgl1 && \
    rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package installer)
COPY --from=ghcr.io/astral-sh/uv:0.8.0 /uv /bin/

# Clone YOLOv9 repository
WORKDIR /yolov9
RUN git clone https://github.com/WongKinYiu/yolov9.git .

# Install Python dependencies
RUN uv pip install --system -r requirements.txt
RUN uv pip install --system onnx==1.18.0 onnxruntime onnx-simplifier>=0.4.1

# Download pretrained weights
ARG MODEL_SIZE
ARG IMG_SIZE
ADD https://github.com/WongKinYiu/yolov9/releases/download/v0.1/yolov9-${MODEL_SIZE}-converted.pt yolov9-${MODEL_SIZE}.pt

# Fix torch.load() for newer PyTorch versions (CVE-2024-5480 mitigation workaround)
# YOLOv9 models require weights_only=False due to custom classes in checkpoint
RUN sed -i "s/ckpt = torch.load(attempt_download(w), map_location='cpu')/ckpt = torch.load(attempt_download(w), map_location='cpu', weights_only=False)/g" models/experimental.py

# Export to ONNX with simplification
RUN python3 export.py \
    --weights ./yolov9-${MODEL_SIZE}.pt \
    --imgsz ${IMG_SIZE} \
    --simplify \
    --include onnx

# Extract model to output layer
FROM scratch
ARG MODEL_SIZE
ARG IMG_SIZE
COPY --from=build /yolov9/yolov9-${MODEL_SIZE}.onnx /yolov9-${MODEL_SIZE}-${IMG_SIZE}.onnx
EOF

# Verify output file exists
if [ -f "$OUTPUT_FILE" ]; then
    FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
    echo ""
    echo "✅ Build successful!"
    echo ""
    echo "Output file: $OUTPUT_FILE"
    echo "File size: $FILE_SIZE"
    echo ""
    echo "Next steps:"
    echo "  1. Copy model to Frigate models directory:"
    echo "     cp $OUTPUT_FILE /path/to/frigate/models/"
    echo ""
    echo "  2. Update Frigate config.yml:"
    echo "     detectors:"
    echo "       onnx:"
    echo "         type: onnx"
    echo ""
    echo "     model:"
    echo "       path: /config/models/$OUTPUT_FILE"
    echo "       input_tensor: nchw"
    echo "       input_pixel_format: rgb"
    echo "       width: $IMG_SIZE"
    echo "       height: $IMG_SIZE"
    echo "       model_type: yolo-generic"
    echo "       input_dtype: float"
    echo ""
    echo "  3. Restart Frigate to load the new model"
    echo ""
else
    echo ""
    echo "❌ Build failed - output file not found"
    echo "Check Docker logs above for errors"
    exit 1
fi
