#!/bin/bash
# 06-label-k8s-node.sh - Add Coral TPU label to K8s node

set -e

NODE="k3s-vm-pumped-piglet-gpu"

echo "========================================="
echo "Step 6: Label K8s Node for Coral TPU"
echo "========================================="
echo ""

echo "Current labels on $NODE:"
KUBECONFIG=~/kubeconfig kubectl get node $NODE --show-labels | grep -oE 'coral[^,]*' || echo "No coral label"
echo ""

echo "Adding coral.ai/tpu=usb label..."
KUBECONFIG=~/kubeconfig kubectl label node $NODE coral.ai/tpu=usb --overwrite
echo ""

echo "Verifying label..."
KUBECONFIG=~/kubeconfig kubectl get node $NODE --show-labels | grep -oE 'coral[^,]*'
echo ""

echo "========================================="
echo "Node labeled. Next: Update K8s manifests and deploy"
echo "========================================="
