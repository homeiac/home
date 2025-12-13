#!/bin/bash
set -euo pipefail

export KUBECONFIG=~/kubeconfig
echo "Labeling k3s-vm-still-fawn with coral.ai/tpu=usb..."
kubectl label node k3s-vm-still-fawn coral.ai/tpu=usb --overwrite
echo "Node labeled."
