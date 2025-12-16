#!/bin/bash
#
# Run USE Method checklist on a Proxmox VM
# Copies the script to the host, then executes inside the VM via qm guest exec
#
# Usage:
#   ./run-on-proxmox-vm.sh 116              # HAOS on chief-horse
#   ./run-on-proxmox-vm.sh 108              # K3s VM on still-fawn
#   ./run-on-proxmox-vm.sh 116 --quick      # Quick triage only
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VMID="${1:-116}"
MODE="${2:-full}"  # full or --quick

# Map VMID to Proxmox host
get_host() {
    case "$1" in
        116|109) echo "chief-horse.maas" ;;
        108) echo "still-fawn.maas" ;;
        105) echo "pumped-piglet.maas" ;;
        113) echo "fun-bedbug.maas" ;;  # LXC
        *) echo "chief-horse.maas" ;;
    esac
}

HOST=$(get_host "$VMID")
REMOTE_SCRIPT_DIR="/root/perf-scripts"

echo "=== USE Method Analysis for VM $VMID on $HOST ==="
echo ""

# Sync scripts to Proxmox host
echo "Syncing scripts to $HOST..."
ssh "root@$HOST" "mkdir -p $REMOTE_SCRIPT_DIR" 2>/dev/null
rsync -az --delete \
    "$SCRIPT_DIR/use-checklist.sh" \
    "$SCRIPT_DIR/quick-triage.sh" \
    "$SCRIPT_DIR/install-crisis-tools.sh" \
    "root@$HOST:$REMOTE_SCRIPT_DIR/" 2>/dev/null

# For VMs, copy script into VM and run
if [[ "$VMID" == "113" ]]; then
    # LXC container - use pct exec
    echo "Running on LXC $VMID..."
    ssh "root@$HOST" "pct push $VMID $REMOTE_SCRIPT_DIR/use-checklist.sh /tmp/use-checklist.sh"
    ssh "root@$HOST" "pct exec $VMID -- chmod +x /tmp/use-checklist.sh"
    if [[ "$MODE" == "--quick" ]]; then
        ssh "root@$HOST" "pct push $VMID $REMOTE_SCRIPT_DIR/quick-triage.sh /tmp/quick-triage.sh"
        ssh "root@$HOST" "pct exec $VMID -- chmod +x /tmp/quick-triage.sh"
        ssh "root@$HOST" "pct exec $VMID -- /tmp/quick-triage.sh"
    else
        ssh "root@$HOST" "pct exec $VMID -- /tmp/use-checklist.sh"
    fi
else
    # VM - use qm guest exec with file copy
    echo "Copying script to VM $VMID..."

    # Use qm guest exec to write script (base64 to avoid quoting issues)
    SCRIPT_B64=$(base64 < "$SCRIPT_DIR/use-checklist.sh")
    ssh "root@$HOST" "echo '$SCRIPT_B64' | base64 -d > /tmp/vm-${VMID}-script.sh"

    # Copy into VM using qm guest exec with cat
    ssh "root@$HOST" "qm guest exec $VMID -- mkdir -p /tmp" 2>/dev/null || true

    # For HAOS, we need to use a simpler approach - run commands directly
    echo ""
    echo "Running USE Method checks inside VM $VMID..."
    echo ""

    # Run simplified checks directly via qm guest exec
    run_vm_cmd() {
        local cmd="$1"
        local result=$(ssh "root@$HOST" "qm guest exec $VMID -- $cmd" 2>/dev/null)
        echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('out-data','N/A'))" 2>/dev/null || echo "N/A"
    }

    echo "═══════════════════════════════════════════════════════════"
    echo "  CPU - Errors, Utilization, Saturation"
    echo "═══════════════════════════════════════════════════════════"

    echo -n "  [E] Hardware errors (dmesg): "
    errors=$(run_vm_cmd "dmesg" | grep -ci 'mce\|hardware error' || echo "0")
    [[ "$errors" == "0" ]] && echo "0 ✓" || echo "$errors ✗ INVESTIGATE"

    echo -n "  [U] Load average: "
    run_vm_cmd "cat /proc/loadavg"

    echo -n "  [S] CPU count: "
    run_vm_cmd "nproc"

    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  MEMORY - Errors, Utilization, Saturation"
    echo "═══════════════════════════════════════════════════════════"

    echo -n "  [E] OOM kills: "
    ooms=$(run_vm_cmd "dmesg" | grep -ci 'killed process\|oom' || echo "0")
    [[ "$ooms" == "0" ]] && echo "0 ✓" || echo "$ooms ✗ INVESTIGATE"

    echo "  [U] Memory:"
    run_vm_cmd "free -m"

    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  TOP PROCESSES"
    echo "═══════════════════════════════════════════════════════════"
    run_vm_cmd "ps aux --sort=-%cpu" | head -15

    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  DISK"
    echo "═══════════════════════════════════════════════════════════"
    run_vm_cmd "df -h"
fi

echo ""
echo "=== HOST LAYER: $HOST ==="
echo ""
# Run USE checklist on the host itself
ssh "root@$HOST" "$REMOTE_SCRIPT_DIR/use-checklist.sh" 2>&1 || true
