#!/usr/bin/env bash
# Read-only ML provider, resource pressure and shared GPU diagnostics.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
kubectl -n immich-pilot exec deployment/immich-machine-learning -- python -c 'import onnxruntime as ort; print("ORT providers:", ort.get_available_providers())'
kubectl -n immich-pilot logs deployment/immich-machine-learning --tail=200 | rg -i 'provider|ocr|error|cuda' | tail -20
kubectl -n ollama exec deployment/ollama-gpu -- nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu --format=csv
kubectl -n ollama exec deployment/ollama-gpu -- nvidia-smi --query-compute-apps=process_name,used_gpu_memory --format=csv
kubectl -n immich-pilot exec deployment/immich-machine-learning -- sh -c 'for p in /proc/pressure/cpu /proc/pressure/memory /proc/pressure/io /sys/fs/cgroup/cpu.stat /sys/fs/cgroup/memory.events; do echo "$p"; cat "$p"; done; df -h /cache'
kubectl get node k3s-vm-pumped-piglet-gpu -o jsonpath='{.status.allocatable.nvidia\.com/gpu}{" GPU scheduling shares\n"}{.status.conditions[?(@.type=="MemoryPressure")].status}{" MemoryPressure\n"}{.status.conditions[?(@.type=="DiskPressure")].status}{" DiskPressure\n"}'
