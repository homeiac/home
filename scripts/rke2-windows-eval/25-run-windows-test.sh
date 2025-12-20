#!/bin/bash
# Run Windows test workloads on the RKE2 cluster
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/.env" 2>/dev/null || true

PROXMOX_HOST="${PROXMOX_HOST:-pumped-piglet.maas}"
LINUX_VM_IP="${LINUX_VM_IP:-192.168.4.202}"

KUBECTL="sudo /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml"

run_kubectl() {
    ssh root@${PROXMOX_HOST} "ssh ubuntu@${LINUX_VM_IP} '${KUBECTL} $*'"
}

echo "=== Running Windows Test Workloads ==="
echo ""

# Copy manifests to Linux control plane
echo "Copying manifests to control plane..."
scp -o StrictHostKeyChecking=no -r "${SCRIPT_DIR}/manifests" root@${PROXMOX_HOST}:/tmp/

ssh root@${PROXMOX_HOST} "scp -o StrictHostKeyChecking=no -r /tmp/manifests ubuntu@${LINUX_VM_IP}:/tmp/"

# Test 1: Simple Windows pod
echo ""
echo "--- Test 1: Simple Windows Pod ---"
run_kubectl "apply -f /tmp/manifests/windows-test-pod.yaml"

echo "Waiting for pod to be ready (this may take a few minutes for image pull)..."
for i in {1..60}; do
    STATUS=$(run_kubectl "get pod windows-test -o jsonpath='{.status.phase}'" 2>/dev/null || echo "Pending")
    if [[ "$STATUS" == "'Running'" ]]; then
        echo "Pod is Running!"
        break
    fi
    echo "  Attempt $i/60: Status=$STATUS"
    sleep 10
done

run_kubectl "logs windows-test" 2>/dev/null || echo "Logs not yet available"

# Test 2: Disk I/O Benchmark
echo ""
echo "--- Test 2: Disk I/O Benchmark Job ---"
run_kubectl "apply -f /tmp/manifests/windows-diskio-benchmark.yaml"

echo "Waiting for benchmark job to complete..."
for i in {1..60}; do
    STATUS=$(run_kubectl "get job windows-diskio-benchmark -o jsonpath='{.status.succeeded}'" 2>/dev/null || echo "0")
    FAILED=$(run_kubectl "get job windows-diskio-benchmark -o jsonpath='{.status.failed}'" 2>/dev/null || echo "0")
    if [[ "$STATUS" == "'1'" ]]; then
        echo "Benchmark completed!"
        break
    fi
    if [[ "$FAILED" == "'1'" ]]; then
        echo "Benchmark failed!"
        break
    fi
    POD_STATUS=$(run_kubectl "get pods -l job-name=windows-diskio-benchmark -o jsonpath='{.items[0].status.phase}'" 2>/dev/null || echo "Unknown")
    echo "  Attempt $i/60: Job status pending, Pod=$POD_STATUS"
    sleep 10
done

echo ""
echo "=== Benchmark Results ==="
run_kubectl "logs job/windows-diskio-benchmark" 2>/dev/null || echo "Logs not yet available"

echo ""
echo "=== Cleanup ==="
echo "To clean up test workloads, run:"
echo "  ./26-cleanup-windows-tests.sh"
