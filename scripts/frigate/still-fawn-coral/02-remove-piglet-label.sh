#!/bin/bash
set -euo pipefail

export KUBECONFIG=~/kubeconfig
echo "Removing coral.ai/tpu label from pumped-piglet node..."
kubectl label node k3s-vm-pumped-piglet-gpu coral.ai/tpu- || true
echo "Done."
