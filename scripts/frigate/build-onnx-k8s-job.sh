#!/bin/bash
#
# build-onnx-k8s-job.sh
#
# Build YOLOv9 ONNX model using a K8s Job on the GPU node
# No local Docker required - runs entirely on the cluster
#

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
MODEL_SIZE="${1:-c}"
IMG_SIZE="${2:-640}"
OUTPUT_FILE="yolov9-${MODEL_SIZE}-${IMG_SIZE}.onnx"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Build YOLOv9 ONNX Model via K8s Job"
echo "========================================="
echo ""
echo "Model: YOLOv9-${MODEL_SIZE}"
echo "Input size: ${IMG_SIZE}x${IMG_SIZE}"
echo "Output: ${OUTPUT_FILE}"
echo ""

# Create the Job manifest
JOB_YAML=$(cat <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: build-yolov9-onnx
  namespace: frigate
spec:
  ttlSecondsAfterFinished: 300
  template:
    spec:
      restartPolicy: Never
      nodeSelector:
        nvidia.com/gpu.present: "true"
      containers:
        - name: builder
          image: python:3.11-slim
          command:
            - /bin/bash
            - -c
            - |
              set -e
              echo "=== Installing dependencies ==="
              apt-get update && apt-get install -y git libgl1 libglib2.0-0 curl
              pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
              pip install --no-cache-dir onnx onnxruntime onnx-simplifier opencv-python-headless onnxscript

              echo "=== Cloning YOLOv9 ==="
              git clone https://github.com/WongKinYiu/yolov9.git /yolov9
              cd /yolov9
              pip install --no-cache-dir -r requirements.txt

              echo "=== Downloading weights ==="
              curl -L -o yolov9-${MODEL_SIZE}.pt https://github.com/WongKinYiu/yolov9/releases/download/v0.1/yolov9-${MODEL_SIZE}-converted.pt

              echo "=== Fixing torch.load for newer PyTorch ==="
              sed -i "s/ckpt = torch.load(attempt_download(w), map_location='cpu')/ckpt = torch.load(attempt_download(w), map_location='cpu', weights_only=False)/g" models/experimental.py

              echo "=== Exporting to ONNX ==="
              python3 export.py --weights ./yolov9-${MODEL_SIZE}.pt --imgsz ${IMG_SIZE} --simplify --include onnx

              echo "=== Copying to output ==="
              cp yolov9-${MODEL_SIZE}.onnx /output/${OUTPUT_FILE}
              ls -lh /output/
              echo "=== Done ==="
          volumeMounts:
            - name: output
              mountPath: /output
      volumes:
        - name: output
          persistentVolumeClaim:
            claimName: frigate-config
EOF
)

# Delete existing job if present
echo "Step 1: Cleaning up old job..."
KUBECONFIG="$KUBECONFIG" kubectl delete job build-yolov9-onnx -n frigate 2>/dev/null || true
sleep 2

# Create the job
echo "Step 2: Creating build job..."
echo "$JOB_YAML" | KUBECONFIG="$KUBECONFIG" kubectl apply -f -
echo ""

# Wait for completion
echo "Step 3: Waiting for build to complete (5-15 min)..."
echo "   You can watch logs with: kubectl logs -n frigate -f job/build-yolov9-onnx"
echo ""

KUBECONFIG="$KUBECONFIG" kubectl wait --for=condition=complete job/build-yolov9-onnx -n frigate --timeout=900s || {
    echo -e "${YELLOW}Job may have failed. Check logs:${NC}"
    KUBECONFIG="$KUBECONFIG" kubectl logs -n frigate job/build-yolov9-onnx --tail=50
    exit 1
}

echo ""
echo -e "${GREEN}✓ Build complete!${NC}"
echo ""

# Verify output
echo "Step 4: Verifying output..."
KUBECONFIG="$KUBECONFIG" kubectl exec -n frigate deployment/frigate -- ls -lh /config/${OUTPUT_FILE} 2>/dev/null || {
    echo "Model file location may differ. Checking config directory..."
    KUBECONFIG="$KUBECONFIG" kubectl exec -n frigate deployment/frigate -- ls -lh /config/
}

echo ""
echo "========================================="
echo -e "${GREEN}YOLOv9 ONNX model built!${NC}"
echo "========================================="
echo ""
echo "Model available at: /config/${OUTPUT_FILE} (in Frigate pod)"
echo ""
echo "Next steps:"
echo "1. Apply ONNX configmap:"
echo "   kubectl apply -f k8s/frigate-016/configmap-onnx.yaml"
echo "2. Restart Frigate to load new detector"
