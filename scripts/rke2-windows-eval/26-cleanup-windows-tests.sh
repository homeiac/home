#!/bin/bash
# Clean up Windows test workloads
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
LINUX_VM_IP="${LINUX_VM_IP:-192.168.4.202}"

KUBECTL="sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml"

run_kubectl() {
    ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} '${KUBECTL} $*'"
}

echo "=== Cleaning up Windows Test Workloads ==="

run_kubectl "delete pod windows-test --ignore-not-found" 2>/dev/null || true
run_kubectl "delete job windows-diskio-benchmark --ignore-not-found" 2>/dev/null || true

echo "Cleanup complete."
