#!/opt/homebrew/bin/bash
# Post-reboot health check for K3s cluster nodes
# Usage: ./post-reboot-check.sh [node-name]
# Example: ./post-reboot-check.sh k3s-vm-pumped-piglet-gpu
#
# Checks:
# 1. Node readiness
# 2. Stuck pods (UnexpectedAdmissionError, ContainerStatusUnknown)
# 3. GPU workloads scheduled
# 4. MetalLB speaker health
# 5. Disk SMART warnings (if run with SSH access to host)

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
export KUBECONFIG

NODE_FILTER="${1:-}"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
info() { echo -e "       $1"; }

echo "========================================="
echo " K3s Post-Reboot Health Check"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="
echo

# --- 1. Node Readiness ---
echo "--- Node Readiness ---"
NOT_READY=$(kubectl get nodes --no-headers 2>/dev/null | grep -v " Ready " || true)
if [[ -z "$NOT_READY" ]]; then
    pass "All nodes are Ready"
else
    fail "Some nodes are NotReady:"
    echo "$NOT_READY" | while read -r line; do
        info "  $line"
    done
fi
kubectl get nodes --no-headers 2>/dev/null | while read -r line; do
    info "  $line"
done
echo

# --- 2. Stuck Pods ---
echo "--- Stuck Pods ---"
STUCK_PODS=$(kubectl get pods --all-namespaces --no-headers 2>/dev/null | \
    grep -iE "UnexpectedAdmissionError|ContainerStatusUnknown|Unknown|Error" || true)
if [[ -z "$STUCK_PODS" ]]; then
    pass "No stuck pods found"
else
    fail "Found stuck pods that need cleanup:"
    echo "$STUCK_PODS" | while read -r line; do
        info "  $line"
    done
    echo
    info "To clean up, run:"
    echo "$STUCK_PODS" | awk '{print "  kubectl delete pod -n "$1" "$2" --grace-period=0 --force"}'
fi
echo

# --- 3. GPU Workloads ---
echo "--- GPU Workloads ---"
GPU_NAMESPACES="ollama stable-diffusion"
for ns in $GPU_NAMESPACES; do
    PODS=$(kubectl get pods -n "$ns" --no-headers 2>/dev/null || true)
    if [[ -z "$PODS" ]]; then
        warn "No pods in namespace '$ns'"
    else
        RUNNING=$(echo "$PODS" | grep -c "Running" || true)
        TOTAL=$(echo "$PODS" | wc -l | tr -d ' ')
        if [[ "$RUNNING" -eq "$TOTAL" ]]; then
            pass "$ns: $RUNNING/$TOTAL pods running"
        else
            warn "$ns: $RUNNING/$TOTAL pods running"
        fi
        echo "$PODS" | while read -r line; do
            info "  $line"
        done
    fi
done
echo

# --- 4. MetalLB Speaker Health ---
echo "--- MetalLB Speakers ---"
SPEAKERS=$(kubectl get pods -n metallb-system -l app.kubernetes.io/component=speaker --no-headers 2>/dev/null || true)
if [[ -z "$SPEAKERS" ]]; then
    warn "No MetalLB speakers found"
else
    NOT_RUNNING=$(echo "$SPEAKERS" | grep -v "Running" || true)
    if [[ -z "$NOT_RUNNING" ]]; then
        pass "All MetalLB speakers running"
    else
        fail "Some MetalLB speakers not running:"
        echo "$NOT_RUNNING" | while read -r line; do
            info "  $line"
        done
    fi

    # Check for excessive restarts (>100 in last period)
    while read -r name ready status restarts age; do
        restart_count=$(echo "$restarts" | grep -oE '^[0-9]+')
        if [[ "$restart_count" -gt 100 ]]; then
            warn "Speaker $name has $restart_count restarts"
        fi
    done <<< "$SPEAKERS"

    echo "$SPEAKERS" | while read -r line; do
        info "  $line"
    done
fi
echo

# --- 5. Disk SMART Warnings (requires SSH to Proxmox host) ---
echo "--- Disk SMART Warnings ---"
# Map K3s node names to Proxmox hosts
declare -A HOST_MAP=(
    ["k3s-vm-pumped-piglet-gpu"]="pumped-piglet.maas"
    ["k3s-vm-still-fawn"]="still-fawn.maas"
    ["k3s-vm-fun-bedbug"]="fun-bedbug.maas"
    ["k3s-vm-pve"]="pve.maas"
)

check_smart() {
    local host="$1"
    local result
    result=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "root@$host" \
        "smartctl --scan 2>/dev/null | awk '{print \$1}' | while read disk; do
            pending=\$(smartctl -A \"\$disk\" 2>/dev/null | grep -iE 'pending|uncorrect|reallocat' | grep -vE '  0$|  0 ' || true)
            if [[ -n \"\$pending\" ]]; then
                echo \"WARN \$disk: \$pending\"
            fi
        done" 2>/dev/null || echo "SSH_FAIL")

    if [[ "$result" == "SSH_FAIL" ]]; then
        warn "Cannot SSH to $host (check connectivity)"
    elif [[ -z "$result" ]]; then
        pass "$host: No SMART warnings"
    else
        fail "$host: SMART warnings detected"
        echo "$result" | while read -r line; do
            info "  $line"
        done
    fi
}

if [[ -n "$NODE_FILTER" ]]; then
    host="${HOST_MAP[$NODE_FILTER]:-}"
    if [[ -n "$host" ]]; then
        check_smart "$host"
    else
        check_smart "$NODE_FILTER"
    fi
else
    for node in "${!HOST_MAP[@]}"; do
        check_smart "${HOST_MAP[$node]}"
    done
fi
echo

# --- 6. Frigate Status ---
echo "--- Frigate ---"
FRIGATE_PODS=$(kubectl get pods -n frigate --no-headers 2>/dev/null | grep -v "health-checker" || true)
if [[ -z "$FRIGATE_PODS" ]]; then
    fail "No Frigate pods found"
else
    RUNNING=$(echo "$FRIGATE_PODS" | grep -c "Running" || true)
    if [[ "$RUNNING" -gt 0 ]]; then
        pass "Frigate is running"
    else
        fail "Frigate is not running"
    fi
    echo "$FRIGATE_PODS" | while read -r line; do
        info "  $line"
    done
fi
echo

echo "========================================="
echo " Check complete"
echo "========================================="
