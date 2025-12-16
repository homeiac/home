#!/bin/bash
#
# USE Method Performance Checklist
# Based on Brendan Gregg's methodology: https://www.brendangregg.com/usemethod.html
#
# For every resource, check:
#   U - Utilization (% time busy)
#   S - Saturation (queue length / work waiting)
#   E - Errors (error counts)
#
# Usage:
#   use-checklist.sh                           # Local system
#   use-checklist.sh --context k8s-pod:ns/pod  # K8s pod + node
#   use-checklist.sh --context proxmox-vm:108  # Proxmox VM + host
#   use-checklist.sh --context lxc:113         # LXC container + host
#   use-checklist.sh --save                    # Save JSON report
#   use-checklist.sh --compare <file.json>     # Compare to baseline
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORTS_DIR="${SCRIPT_DIR}/reports"
TIMESTAMP=$(date +%Y-%m-%d-%H-%M-%S)

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Thresholds
CPU_UTIL_WARN=70
MEM_UTIL_WARN=80
DISK_UTIL_WARN=70
SATURATION_WARN=1

# Parse arguments
CONTEXT=""
SAVE_REPORT=false
COMPARE_FILE=""
QUIET=false
JSON_OUTPUT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --context)
            CONTEXT="$2"
            shift 2
            ;;
        --save)
            SAVE_REPORT=true
            shift
            ;;
        --compare)
            COMPARE_FILE="$2"
            shift 2
            ;;
        --quiet|-q)
            QUIET=true
            shift
            ;;
        --help|-h)
            echo "USE Method Performance Checklist"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --context TYPE:TARGET  Execution context (see below)"
            echo "  --save                 Save JSON report to reports/"
            echo "  --compare FILE         Compare to baseline JSON file"
            echo "  --quiet, -q            Minimal output"
            echo ""
            echo "Contexts:"
            echo "  k8s-pod:namespace/pod  Check pod + node"
            echo "  proxmox-vm:VMID        Check VM + Proxmox host"
            echo "  lxc:VMID               Check LXC + host"
            echo "  ssh:hostname           Check remote host via SSH"
            echo "  (none)                 Check local system"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Helper: Print section header
print_header() {
    local title="$1"
    echo ""
    echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${BLUE}  $title${NC}"
    echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════════${NC}"
}

# Helper: Print metric with status
print_metric() {
    local resource="$1"
    local type="$2"  # U, S, or E
    local metric="$3"
    local value="$4"
    local status="$5"  # ok, warn, error

    local color=$GREEN
    local symbol="✓"
    case $status in
        warn)
            color=$YELLOW
            symbol="⚠"
            ;;
        error)
            color=$RED
            symbol="✗"
            ;;
    esac

    printf "  ${CYAN}%-8s${NC} [%s] %-20s: ${color}%s %s${NC}\n" "$resource" "$type" "$metric" "$value" "$symbol"
}

# Helper: Execute command in context
exec_in_context() {
    local cmd="$1"
    local context_type=""
    local context_target=""

    if [[ -n "$CONTEXT" ]]; then
        context_type="${CONTEXT%%:*}"
        context_target="${CONTEXT#*:}"
    fi

    case "$context_type" in
        "k8s-pod")
            local ns="${context_target%%/*}"
            local pod="${context_target#*/}"
            kubectl exec -n "$ns" "$pod" -- bash -c "$cmd" 2>/dev/null || echo "N/A"
            ;;
        "proxmox-vm")
            # Execute via qm guest exec - returns JSON, need to parse out-data
            local vmid="$context_target"
            # HAOS 116 is on chief-horse, K3s VMs on their respective hosts
            local host=""
            case "$vmid" in
                116) host="chief-horse.maas" ;;
                108) host="still-fawn.maas" ;;
                105) host="pumped-piglet.maas" ;;
                109) host="chief-horse.maas" ;;
                *) host="chief-horse.maas" ;;  # default
            esac
            # Run simple commands in VM, do parsing locally to avoid quoting hell
            local simple_cmd=$(echo "$cmd" | sed 's/|.*//')  # Remove pipes, run raw command
            local json_out=$(ssh -o ConnectTimeout=10 "root@$host" "qm guest exec $vmid -- $simple_cmd" 2>/dev/null)
            if [[ -n "$json_out" ]] && echo "$json_out" | grep -q "out-data"; then
                # Extract out-data using python (handles escaped newlines properly)
                local raw_out=$(echo "$json_out" | python3 -c "import sys,json; print(json.load(sys.stdin).get('out-data','N/A'))" 2>/dev/null)
                # Apply any remaining pipeline locally
                if [[ "$cmd" == *"|"* ]]; then
                    local pipeline=$(echo "$cmd" | sed 's/^[^|]*|//')
                    echo "$raw_out" | eval "$pipeline" 2>/dev/null || echo "N/A"
                else
                    echo "$raw_out"
                fi
            else
                echo "N/A"
            fi
            ;;
        "lxc")
            local vmid="$context_target"
            ssh root@fun-bedbug.maas "pct exec $vmid -- bash -c '$cmd'" 2>/dev/null || echo "N/A"
            ;;
        "ssh")
            ssh "$context_target" "$cmd" 2>/dev/null || echo "N/A"
            ;;
        *)
            # Local execution
            eval "$cmd" 2>/dev/null || echo "N/A"
            ;;
    esac
}

# Helper: Get host for layered analysis
get_host_context() {
    local context_type="${CONTEXT%%:*}"
    local context_target="${CONTEXT#*:}"

    case "$context_type" in
        "k8s-pod")
            # Get node name from pod
            local ns="${context_target%%/*}"
            local pod="${context_target#*/}"
            local node=$(kubectl get pod -n "$ns" "$pod" -o jsonpath='{.spec.nodeName}' 2>/dev/null)
            echo "k8s-node:$node"
            ;;
        "proxmox-vm")
            # VM host is where we SSH to run qm commands
            echo "proxmox-host"
            ;;
        "lxc")
            echo "lxc-host:fun-bedbug.maas"
            ;;
        *)
            echo ""
            ;;
    esac
}

# ============================================================================
# CPU CHECKS (Order: Errors → Utilization → Saturation per USE flowchart)
# ============================================================================
check_cpu() {
    print_header "CPU - Errors, Utilization, Saturation"

    # --- ERRORS FIRST (quickest signal) ---
    local mce_errors=$(exec_in_context "dmesg 2>/dev/null | grep -ci 'mce\\|machine check\\|hardware error' || echo 0" | tail -1 | tr -d '[:space:]')
    local status="ok"
    [[ "$mce_errors" != "0" && "$mce_errors" != "N/A" ]] && status="error"
    print_metric "CPU" "E" "Hardware errors (MCE)" "$mce_errors" "$status"
    JSON_OUTPUT+=",\"cpu_errors\": $mce_errors"

    # If errors found, flag for investigation
    [[ "$status" == "error" ]] && echo -e "  ${RED}>>> INVESTIGATE: Hardware errors detected!${NC}"

    # --- UTILIZATION ---
    # Get CPU utilization from vmstat (averaged over 3 samples)
    local cpu_idle=$(exec_in_context "vmstat 1 3 | tail -1 | awk '{print \$15}'" | tr -d '[:space:]')
    if [[ "$cpu_idle" != "N/A" && -n "$cpu_idle" ]]; then
        local cpu_util=$((100 - cpu_idle))
        local status="ok"
        [[ $cpu_util -ge $CPU_UTIL_WARN ]] && status="warn"
        [[ $cpu_util -ge 95 ]] && status="error"
        print_metric "CPU" "U" "System utilization" "${cpu_util}%" "$status"
        JSON_OUTPUT+=",\"cpu_util\": $cpu_util"

        # If high utilization, flag for investigation
        [[ "$status" != "ok" ]] && echo -e "  ${YELLOW}>>> INVESTIGATE: High CPU utilization${NC}"
    else
        print_metric "CPU" "U" "System utilization" "N/A" "warn"
    fi

    # Get per-CPU utilization if mpstat available
    local per_cpu=$(exec_in_context "command -v mpstat >/dev/null && mpstat -P ALL 1 1 2>/dev/null | tail -n +4 | head -4 | awk '{print \$3\": \"100-\$NF\"%\"}'" | tr '\n' ' ')
    if [[ -n "$per_cpu" && "$per_cpu" != "N/A" ]]; then
        echo -e "           Per-core: $per_cpu"
    fi

    # --- SATURATION ---
    # Run queue (r column in vmstat) - saturated if r > CPU count
    local run_queue=$(exec_in_context "vmstat 1 1 | tail -1 | awk '{print \$1}'" | tr -d '[:space:]')
    local cpu_count=$(exec_in_context "nproc" | tr -d '[:space:]')
    if [[ "$run_queue" != "N/A" && -n "$run_queue" && "$cpu_count" != "N/A" && -n "$cpu_count" ]]; then
        local status="ok"
        [[ $run_queue -gt $cpu_count ]] && status="warn"
        [[ $run_queue -gt $((cpu_count * 2)) ]] && status="error"
        print_metric "CPU" "S" "Run queue" "$run_queue (CPUs: $cpu_count)" "$status"
        JSON_OUTPUT+=",\"cpu_runq\": $run_queue, \"cpu_count\": $cpu_count"

        # If saturated, flag for investigation
        [[ "$status" != "ok" ]] && echo -e "  ${YELLOW}>>> INVESTIGATE: CPU saturation (run queue > CPU count)${NC}"
    else
        print_metric "CPU" "S" "Run queue" "N/A" "warn"
    fi

    # Load average (additional context)
    local loadavg=$(exec_in_context "cat /proc/loadavg | awk '{print \$1, \$2, \$3}'" | tr -d '\n')
    if [[ -n "$loadavg" && "$loadavg" != "N/A" ]]; then
        echo -e "           Load avg (1/5/15m): $loadavg"
    fi
}

# ============================================================================
# MEMORY CHECKS (Order: Errors → Utilization → Saturation per USE flowchart)
# ============================================================================
check_memory() {
    print_header "MEMORY - Errors, Utilization, Saturation"

    # --- ERRORS FIRST ---
    local oom_kills=$(exec_in_context "dmesg 2>/dev/null | grep -ci 'killed process\\|oom' || echo 0" | tail -1 | tr -d '[:space:]')
    local status="ok"
    [[ "$oom_kills" != "0" && "$oom_kills" != "N/A" ]] && status="error"
    print_metric "Memory" "E" "OOM kills (dmesg)" "$oom_kills" "$status"
    JSON_OUTPUT+=",\"mem_oom_kills\": $oom_kills"
    [[ "$status" == "error" ]] && echo -e "  ${RED}>>> INVESTIGATE: OOM kills detected!${NC}"

    local alloc_fail=$(exec_in_context "dmesg 2>/dev/null | grep -ci 'page allocation failure' || echo 0" | tail -1 | tr -d '[:space:]')
    status="ok"
    [[ "$alloc_fail" != "0" && "$alloc_fail" != "N/A" ]] && status="error"
    print_metric "Memory" "E" "Allocation failures" "$alloc_fail" "$status"
    [[ "$status" == "error" ]] && echo -e "  ${RED}>>> INVESTIGATE: Page allocation failures!${NC}"

    # --- UTILIZATION ---
    local mem_info=$(exec_in_context "free -m | awk '/^Mem:/ {printf \"%d %d %d\", \$2, \$3, \$7}'")
    if [[ "$mem_info" != "N/A" && -n "$mem_info" ]]; then
        local mem_total=$(echo "$mem_info" | awk '{print $1}')
        local mem_used=$(echo "$mem_info" | awk '{print $2}')
        local mem_avail=$(echo "$mem_info" | awk '{print $3}')
        local mem_util=$((mem_used * 100 / mem_total))
        local status="ok"
        [[ $mem_util -ge $MEM_UTIL_WARN ]] && status="warn"
        [[ $mem_util -ge 95 ]] && status="error"
        print_metric "Memory" "U" "Utilization" "${mem_util}% (${mem_used}MB/${mem_total}MB)" "$status"
        echo -e "           Available: ${mem_avail}MB"
        JSON_OUTPUT+=",\"mem_util\": $mem_util, \"mem_total_mb\": $mem_total, \"mem_avail_mb\": $mem_avail"
        [[ "$status" != "ok" ]] && echo -e "  ${YELLOW}>>> INVESTIGATE: High memory utilization${NC}"
    else
        print_metric "Memory" "U" "Utilization" "N/A" "warn"
    fi

    # --- SATURATION ---
    # Swap activity (si/so in vmstat)
    local swap_activity=$(exec_in_context "vmstat 1 2 | tail -1 | awk '{print \$7, \$8}'")
    if [[ "$swap_activity" != "N/A" && -n "$swap_activity" ]]; then
        local si=$(echo "$swap_activity" | awk '{print $1}')
        local so=$(echo "$swap_activity" | awk '{print $2}')
        local status="ok"
        [[ "$si" != "0" || "$so" != "0" ]] && status="warn"
        print_metric "Memory" "S" "Swap in/out" "si=$si so=$so" "$status"
        JSON_OUTPUT+=",\"mem_swap_in\": $si, \"mem_swap_out\": $so"
        [[ "$status" != "ok" ]] && echo -e "  ${YELLOW}>>> INVESTIGATE: Active swapping indicates memory pressure${NC}"
    else
        print_metric "Memory" "S" "Swap activity" "N/A" "warn"
    fi
}

# ============================================================================
# DISK I/O CHECKS (Order: Errors → Utilization → Saturation per USE flowchart)
# ============================================================================
check_disk() {
    print_header "DISK I/O - Errors, Utilization, Saturation"

    # --- ERRORS FIRST ---
    local io_errors=$(exec_in_context "dmesg 2>/dev/null | grep -ci 'i/o error\\|medium error\\|sense key' || echo 0" | tail -1 | tr -d '[:space:]')
    local status="ok"
    [[ "$io_errors" != "0" && "$io_errors" != "N/A" ]] && status="error"
    print_metric "Disk" "E" "I/O errors (dmesg)" "$io_errors" "$status"
    JSON_OUTPUT+=",\"disk_io_errors\": $io_errors"
    [[ "$status" == "error" ]] && echo -e "  ${RED}>>> INVESTIGATE: Disk I/O errors detected!${NC}"

    # SMART errors if smartctl available
    local smart_check=$(exec_in_context "command -v smartctl >/dev/null && echo yes || echo no")
    if [[ "$smart_check" == "yes" ]]; then
        local smart_errors=$(exec_in_context "smartctl --scan 2>/dev/null | head -1 | awk '{print \$1}' | xargs -I {} smartctl -H {} 2>/dev/null | grep -c 'FAILED' || echo 0" | tail -1 | tr -d '[:space:]')
        status="ok"
        [[ "$smart_errors" != "0" && "$smart_errors" != "N/A" ]] && status="error"
        print_metric "Disk" "E" "SMART health" "$smart_errors failures" "$status"
        [[ "$status" == "error" ]] && echo -e "  ${RED}>>> INVESTIGATE: SMART failures - disk may be failing!${NC}"
    fi

    # --- UTILIZATION & SATURATION (iostat provides both) ---
    local iostat_check=$(exec_in_context "command -v iostat >/dev/null && echo yes || echo no")

    if [[ "$iostat_check" == "yes" ]]; then
        # Get iostat data for all devices
        local iostat_data=$(exec_in_context "iostat -xz 1 2 | tail -n +7 | head -10")

        if [[ -n "$iostat_data" && "$iostat_data" != "N/A" ]]; then
            echo "$iostat_data" | while read -r line; do
                [[ -z "$line" ]] && continue
                local device=$(echo "$line" | awk '{print $1}')
                local util=$(echo "$line" | awk '{print $NF}' | cut -d. -f1)
                local await=$(echo "$line" | awk '{print $(NF-4)}' | cut -d. -f1)
                local avgqu=$(echo "$line" | awk '{print $(NF-2)}' | cut -d. -f1)

                [[ -z "$device" || "$device" == "Device" ]] && continue

                # Utilization
                local status="ok"
                [[ -n "$util" && "$util" =~ ^[0-9]+$ && $util -ge $DISK_UTIL_WARN ]] && status="warn"
                [[ -n "$util" && "$util" =~ ^[0-9]+$ && $util -ge 95 ]] && status="error"
                print_metric "$device" "U" "Utilization" "${util:-0}%" "$status"
                [[ "$status" != "ok" ]] && echo -e "  ${YELLOW}>>> INVESTIGATE: High disk utilization on $device${NC}"

                # Saturation (queue depth)
                status="ok"
                [[ -n "$avgqu" && "$avgqu" =~ ^[0-9]+$ && $avgqu -gt $SATURATION_WARN ]] && status="warn"
                print_metric "$device" "S" "Queue depth" "${avgqu:-0}" "$status"
                [[ "$status" != "ok" ]] && echo -e "  ${YELLOW}>>> INVESTIGATE: Disk queue saturation on $device${NC}"

                # Wait time (additional saturation indicator)
                status="ok"
                [[ -n "$await" && "$await" =~ ^[0-9]+$ && $await -gt 10 ]] && status="warn"
                [[ -n "$await" && "$await" =~ ^[0-9]+$ && $await -gt 50 ]] && status="error"
                echo -e "           Await: ${await:-0}ms"
            done
        fi
    else
        print_metric "Disk" "U" "iostat" "Not installed (run install-crisis-tools.sh)" "warn"
    fi

    # Filesystem capacity (Utilization of storage capacity)
    echo ""
    echo -e "  ${CYAN}Filesystem capacity:${NC}"
    exec_in_context "df -h 2>/dev/null | grep -E '^/dev' | head -5" | while read -r line; do
        local use_pct=$(echo "$line" | awk '{print $5}' | tr -d '%')
        local mount=$(echo "$line" | awk '{print $6}')
        local status="ok"
        [[ -n "$use_pct" && "$use_pct" =~ ^[0-9]+$ && $use_pct -ge 80 ]] && status="warn"
        [[ -n "$use_pct" && "$use_pct" =~ ^[0-9]+$ && $use_pct -ge 95 ]] && status="error"
        local color=$GREEN
        [[ "$status" == "warn" ]] && color=$YELLOW
        [[ "$status" == "error" ]] && color=$RED
        printf "    ${color}%-20s %s%%${NC}\n" "$mount" "$use_pct"
    done
}

# ============================================================================
# NETWORK CHECKS (Order: Errors → Utilization → Saturation per USE flowchart)
# ============================================================================
check_network() {
    print_header "NETWORK - Errors, Utilization, Saturation"

    # Get network interface stats
    local interfaces=$(exec_in_context "ip -s link 2>/dev/null | grep -E '^[0-9]+:' | awk -F': ' '{print \$2}' | grep -v lo | head -5")

    if [[ -n "$interfaces" && "$interfaces" != "N/A" ]]; then
        for iface in $interfaces; do
            iface=$(echo "$iface" | tr -d '@' | cut -d'@' -f1)  # Handle veth@xxx format

            # --- ERRORS FIRST ---
            local errors=$(exec_in_context "cat /sys/class/net/$iface/statistics/rx_errors /sys/class/net/$iface/statistics/tx_errors 2>/dev/null" | tr '\n' ' ')
            if [[ -n "$errors" ]]; then
                local rx_err=$(echo "$errors" | awk '{print $1}')
                local tx_err=$(echo "$errors" | awk '{print $2}')
                local status="ok"
                [[ "$rx_err" != "0" || "$tx_err" != "0" ]] && status="error"
                print_metric "$iface" "E" "RX/TX errors" "$rx_err / $tx_err" "$status"
                [[ "$status" == "error" ]] && echo -e "  ${RED}>>> INVESTIGATE: Network errors on $iface${NC}"
            fi

            # --- UTILIZATION ---
            local stats=$(exec_in_context "cat /sys/class/net/$iface/statistics/rx_bytes /sys/class/net/$iface/statistics/tx_bytes 2>/dev/null" | tr '\n' ' ')
            if [[ -n "$stats" ]]; then
                local rx_bytes=$(echo "$stats" | awk '{print $1}')
                local tx_bytes=$(echo "$stats" | awk '{print $2}')
                local rx_mb=$((rx_bytes / 1024 / 1024))
                local tx_mb=$((tx_bytes / 1024 / 1024))
                print_metric "$iface" "U" "RX/TX total" "${rx_mb}MB / ${tx_mb}MB" "ok"
            fi

            # --- SATURATION ---
            local drops=$(exec_in_context "cat /sys/class/net/$iface/statistics/rx_dropped /sys/class/net/$iface/statistics/tx_dropped 2>/dev/null" | tr '\n' ' ')
            if [[ -n "$drops" ]]; then
                local rx_drop=$(echo "$drops" | awk '{print $1}')
                local tx_drop=$(echo "$drops" | awk '{print $2}')
                local status="ok"
                [[ "$rx_drop" != "0" || "$tx_drop" != "0" ]] && status="warn"
                print_metric "$iface" "S" "RX/TX dropped" "$rx_drop / $tx_drop" "$status"
                [[ "$status" != "ok" ]] && echo -e "  ${YELLOW}>>> INVESTIGATE: Packet drops on $iface (saturation)${NC}"
            fi

            local overruns=$(exec_in_context "cat /sys/class/net/$iface/statistics/rx_over_errors 2>/dev/null || echo 0" | tr -d '[:space:]')
            if [[ "$overruns" != "0" && "$overruns" != "N/A" ]]; then
                print_metric "$iface" "S" "RX overruns" "$overruns" "warn"
                echo -e "  ${YELLOW}>>> INVESTIGATE: Buffer overruns indicate NIC saturation${NC}"
            fi
        done
    else
        print_metric "Network" "U" "Interfaces" "No data" "warn"
    fi

    # TCP retransmits (saturation indicator)
    local retrans=$(exec_in_context "netstat -s 2>/dev/null | grep -i 'segments retransmit' | awk '{print \$1}' || echo 0" | tr -d '[:space:]')
    if [[ -n "$retrans" && "$retrans" != "N/A" ]]; then
        local status="ok"
        # High retransmit count is concerning (would need baseline to properly evaluate)
        print_metric "TCP" "S" "Retransmits (total)" "$retrans" "$status"
        JSON_OUTPUT+=",\"net_tcp_retrans\": $retrans"
    fi
}

# ============================================================================
# GPU CHECKS (Order: Errors → Utilization → Saturation per USE flowchart)
# ============================================================================
check_gpu() {
    # Check if nvidia-smi exists
    local has_gpu=$(exec_in_context "command -v nvidia-smi >/dev/null && echo yes || echo no")

    if [[ "$has_gpu" == "yes" ]]; then
        print_header "GPU (NVIDIA) - Errors, Utilization, Saturation"

        # --- ERRORS FIRST ---
        local xid_errors=$(exec_in_context "dmesg 2>/dev/null | grep -ci 'nvrm\\|xid' || echo 0" | tail -1 | tr -d '[:space:]')
        local status="ok"
        [[ "$xid_errors" != "0" && "$xid_errors" != "N/A" ]] && status="error"
        print_metric "GPU" "E" "XID errors (dmesg)" "$xid_errors" "$status"
        JSON_OUTPUT+=",\"gpu_xid_errors\": $xid_errors"
        [[ "$status" == "error" ]] && echo -e "  ${RED}>>> INVESTIGATE: GPU XID errors indicate driver/hardware issues${NC}"

        # ECC errors (if supported)
        local ecc_errors=$(exec_in_context "nvidia-smi --query-gpu=ecc.errors.corrected.volatile.total --format=csv,noheader,nounits 2>/dev/null | head -1" | tr -d '[:space:]')
        if [[ -n "$ecc_errors" && "$ecc_errors" != "N/A" && "$ecc_errors" != "[N/A]" && "$ecc_errors" != "0" ]]; then
            print_metric "GPU" "E" "ECC errors" "$ecc_errors" "warn"
            echo -e "  ${YELLOW}>>> INVESTIGATE: ECC errors may indicate memory issues${NC}"
        fi

        # --- UTILIZATION ---
        local gpu_util=$(exec_in_context "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1" | tr -d '[:space:]')
        if [[ -n "$gpu_util" && "$gpu_util" != "N/A" ]]; then
            local status="ok"
            [[ "$gpu_util" =~ ^[0-9]+$ && $gpu_util -ge 90 ]] && status="warn"
            print_metric "GPU" "U" "Compute" "${gpu_util}%" "$status"
            JSON_OUTPUT+=",\"gpu_util\": $gpu_util"
            [[ "$status" != "ok" ]] && echo -e "  ${YELLOW}>>> INVESTIGATE: High GPU compute utilization${NC}"
        fi

        # Memory utilization
        local gpu_mem=$(exec_in_context "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1")
        if [[ -n "$gpu_mem" && "$gpu_mem" != "N/A" ]]; then
            local mem_used=$(echo "$gpu_mem" | cut -d',' -f1 | tr -d ' ')
            local mem_total=$(echo "$gpu_mem" | cut -d',' -f2 | tr -d ' ')
            local mem_pct=$((mem_used * 100 / mem_total))
            local status="ok"
            [[ $mem_pct -ge 90 ]] && status="warn"
            [[ $mem_pct -ge 98 ]] && status="error"
            print_metric "GPU" "U" "VRAM" "${mem_used}MB/${mem_total}MB (${mem_pct}%)" "$status"
            JSON_OUTPUT+=",\"gpu_mem_used_mb\": $mem_used, \"gpu_mem_total_mb\": $mem_total"
            [[ "$status" != "ok" ]] && echo -e "  ${YELLOW}>>> INVESTIGATE: High GPU memory usage${NC}"
        fi

        # Temperature (thermal throttling indicator)
        local gpu_temp=$(exec_in_context "nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -1" | tr -d '[:space:]')
        if [[ -n "$gpu_temp" && "$gpu_temp" != "N/A" ]]; then
            local status="ok"
            [[ "$gpu_temp" =~ ^[0-9]+$ && $gpu_temp -ge 80 ]] && status="warn"
            [[ "$gpu_temp" =~ ^[0-9]+$ && $gpu_temp -ge 90 ]] && status="error"
            local color=$GREEN
            [[ "$status" == "warn" ]] && color=$YELLOW
            [[ "$status" == "error" ]] && color=$RED
            echo -e "           ${color}Temperature: ${gpu_temp}°C${NC}"
            [[ "$status" == "error" ]] && echo -e "  ${RED}>>> INVESTIGATE: GPU thermal throttling likely!${NC}"
        fi

        # --- SATURATION ---
        # PCIe bandwidth utilization (indicates potential bottleneck)
        local pcie_rx=$(exec_in_context "nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.width.current --format=csv,noheader,nounits 2>/dev/null | head -1")
        if [[ -n "$pcie_rx" && "$pcie_rx" != "N/A" ]]; then
            echo -e "           PCIe: $pcie_rx"
        fi
    fi
}

# ============================================================================
# CGROUP CHECKS (for containers)
# ============================================================================
check_cgroups() {
    # Only run if we're in a container context
    local context_type="${CONTEXT%%:*}"
    [[ "$context_type" != "k8s-pod" && "$context_type" != "lxc" ]] && return

    print_header "CGROUP LIMITS (Container-Specific)"

    # CPU limits (cgroups v1)
    local cpu_quota=$(exec_in_context "cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null || cat /sys/fs/cgroup/cpu.max 2>/dev/null | awk '{print \$1}' || echo N/A")
    local cpu_period=$(exec_in_context "cat /sys/fs/cgroup/cpu/cpu.cfs_period_us 2>/dev/null || cat /sys/fs/cgroup/cpu.max 2>/dev/null | awk '{print \$2}' || echo 100000")

    if [[ "$cpu_quota" != "-1" && "$cpu_quota" != "max" && "$cpu_quota" != "N/A" ]]; then
        local cpu_limit=$(echo "scale=2; $cpu_quota / $cpu_period" | bc 2>/dev/null || echo "N/A")
        print_metric "Cgroup" "L" "CPU limit" "${cpu_limit} cores" "ok"
    else
        print_metric "Cgroup" "L" "CPU limit" "unlimited" "ok"
    fi

    # CPU throttling
    local throttled=$(exec_in_context "cat /sys/fs/cgroup/cpu/cpu.stat 2>/dev/null | grep nr_throttled | awk '{print \$2}' || echo 0")
    local status="ok"
    [[ "$throttled" != "0" && "$throttled" != "N/A" ]] && status="warn"
    print_metric "Cgroup" "S" "CPU throttled count" "$throttled" "$status"
    JSON_OUTPUT+=",\"cgroup_cpu_throttled\": $throttled"

    # Memory limit
    local mem_limit=$(exec_in_context "cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || cat /sys/fs/cgroup/memory.max 2>/dev/null || echo N/A")
    if [[ "$mem_limit" != "N/A" && "$mem_limit" != "max" ]]; then
        local mem_limit_mb=$((mem_limit / 1024 / 1024))
        # Check if it's a huge number (effectively unlimited)
        if [[ $mem_limit_mb -lt 100000 ]]; then
            print_metric "Cgroup" "L" "Memory limit" "${mem_limit_mb}MB" "ok"
        else
            print_metric "Cgroup" "L" "Memory limit" "unlimited" "ok"
        fi
    fi

    # Memory usage
    local mem_usage=$(exec_in_context "cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null || cat /sys/fs/cgroup/memory.current 2>/dev/null || echo 0")
    if [[ "$mem_usage" != "N/A" && -n "$mem_usage" ]]; then
        local mem_usage_mb=$((mem_usage / 1024 / 1024))
        print_metric "Cgroup" "U" "Memory usage" "${mem_usage_mb}MB" "ok"
    fi
}

# ============================================================================
# LAYERED ANALYSIS
# ============================================================================
run_layered_analysis() {
    local host_context=$(get_host_context)

    if [[ -n "$host_context" && -n "$CONTEXT" ]]; then
        echo ""
        echo -e "${BOLD}${YELLOW}══════════════════════════════════════════════════════════════${NC}"
        echo -e "${BOLD}${YELLOW}  WORKLOAD LAYER: ${CONTEXT}${NC}"
        echo -e "${BOLD}${YELLOW}══════════════════════════════════════════════════════════════${NC}"

        check_cpu
        check_memory
        check_disk
        check_network
        check_gpu
        check_cgroups

        # Now check host layer
        echo ""
        echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════════════════${NC}"
        echo -e "${BOLD}${GREEN}  HOST LAYER: $(echo $host_context | cut -d: -f2)${NC}"
        echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════════════════${NC}"

        # Temporarily switch context to host
        local old_context="$CONTEXT"
        case "$host_context" in
            "k8s-node:"*)
                local node="${host_context#*:}"
                # For K8s node, we need to use kubectl debug or SSH
                # For now, try to get node stats via kubectl
                echo -e "  ${CYAN}Node metrics via kubectl:${NC}"
                kubectl top node "$node" 2>/dev/null || echo "  kubectl top not available"
                ;;
            "proxmox-host")
                # Run checks directly on Proxmox host
                CONTEXT=""  # Local to Proxmox host via existing SSH
                local vmid="${old_context#*:}"
                # Find which host has this VM
                for host in still-fawn.maas pumped-piglet.maas chief-horse.maas; do
                    if ssh "root@$host" "qm list | grep -q ' $vmid '" 2>/dev/null; then
                        CONTEXT="ssh:root@$host"
                        echo -e "  ${CYAN}Proxmox host: $host${NC}"
                        check_cpu
                        check_memory
                        check_disk
                        break
                    fi
                done
                ;;
            "lxc-host:"*)
                local host="${host_context#*:}"
                CONTEXT="ssh:root@$host"
                echo -e "  ${CYAN}LXC host: $host${NC}"
                check_cpu
                check_memory
                check_disk
                ;;
        esac
        CONTEXT="$old_context"

        # Print comparison summary
        echo ""
        echo -e "${BOLD}══════════════════════════════════════════════════════════════${NC}"
        echo -e "${BOLD}  LAYER COMPARISON SUMMARY${NC}"
        echo -e "${BOLD}══════════════════════════════════════════════════════════════${NC}"
        echo -e "  Compare workload vs host metrics above."
        echo -e "  If workload is saturated but host is idle → check limits/quotas"
        echo -e "  If both are saturated → actual resource shortage"
    else
        # Single layer analysis
        check_cpu
        check_memory
        check_disk
        check_network
        check_gpu
    fi
}

# ============================================================================
# MAIN
# ============================================================================
main() {
    echo -e "${BOLD}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║  USE Method Performance Checklist                             ║"
    echo "║  U=Utilization  S=Saturation  E=Errors                        ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    if [[ -n "$CONTEXT" ]]; then
        echo -e "Target: ${CYAN}$CONTEXT${NC}"
    else
        echo -e "Target: ${CYAN}localhost${NC}"
    fi
    echo -e "Time:   ${CYAN}$(date)${NC}"

    JSON_OUTPUT="{\"timestamp\": \"$TIMESTAMP\", \"context\": \"${CONTEXT:-localhost}\""

    run_layered_analysis

    JSON_OUTPUT+="}"

    # Save report if requested
    if [[ "$SAVE_REPORT" == "true" ]]; then
        mkdir -p "$REPORTS_DIR"
        local report_file="${REPORTS_DIR}/${TIMESTAMP}.json"
        echo "$JSON_OUTPUT" | python3 -m json.tool > "$report_file" 2>/dev/null || echo "$JSON_OUTPUT" > "$report_file"
        echo ""
        echo -e "${GREEN}Report saved: $report_file${NC}"
    fi

    # Compare if requested
    if [[ -n "$COMPARE_FILE" ]]; then
        echo ""
        echo -e "${BOLD}Comparison with baseline:${NC}"
        if [[ -f "$COMPARE_FILE" ]]; then
            echo "TODO: Implement comparison logic"
        else
            echo -e "${RED}Baseline file not found: $COMPARE_FILE${NC}"
        fi
    fi

    echo ""
    echo -e "${BOLD}Legend:${NC} [U]=Utilization [S]=Saturation [E]=Errors [L]=Limit"
    echo -e "        ${GREEN}✓${NC}=OK ${YELLOW}⚠${NC}=Warning ${RED}✗${NC}=Error"
}

main "$@"
