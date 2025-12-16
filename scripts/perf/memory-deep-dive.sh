#!/bin/bash
#
# memory-deep-dive.sh - Deep memory analysis when USE Method finds memory issues
#
# Triggered by diagnose.sh when memory utilization/saturation/errors detected.
# Shows:
#   - Memory breakdown (used, buffers, cache, available)
#   - Top memory consumers
#   - Swap activity
#   - OOM history
#   - Page scanning (memory pressure indicators)
#
# Usage:
#   ./memory-deep-dive.sh --target proxmox-vm:116
#   ./memory-deep-dive.sh --target ssh:root@host.maas
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

TARGET=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --target|-t) TARGET="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 --target <target>"
            echo ""
            echo "Targets:"
            echo "  proxmox-vm:<vmid>   Proxmox VM via qm guest exec"
            echo "  ssh:<user@host>     Direct SSH"
            echo "  local               Local machine"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

[[ -z "$TARGET" ]] && TARGET="local"

# Execute command on target
run_cmd() {
    local cmd="$1"

    case "$TARGET" in
        proxmox-vm:*)
            VMID="${TARGET#proxmox-vm:}"
            # Determine host
            case "$VMID" in
                116|109) HOST="chief-horse.maas" ;;
                108) HOST="still-fawn.maas" ;;
                105) HOST="pumped-piglet.maas" ;;
                *) HOST="chief-horse.maas" ;;
            esac
            result=$(ssh "root@$HOST" "qm guest exec $VMID -- $cmd" 2>/dev/null) || echo "ERROR"
            echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('out-data','N/A'))" 2>/dev/null || echo "$result"
            ;;
        ssh:*)
            HOST="${TARGET#ssh:}"
            ssh "$HOST" "$cmd" 2>/dev/null || echo "ERROR"
            ;;
        local)
            eval "$cmd" 2>/dev/null || echo "ERROR"
            ;;
        *)
            echo "Unknown target: $TARGET"
            ;;
    esac
}

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                    MEMORY DEEP DIVE                              ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
printf "║  Target: %-54s ║\n" "$TARGET"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# Memory Overview
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  MEMORY OVERVIEW (free -m)                                       │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

run_cmd "free -m"

echo ""

# ============================================================================
# Detailed Memory Info
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  DETAILED MEMORY INFO (/proc/meminfo highlights)                 │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

meminfo=$(run_cmd "cat /proc/meminfo")

# Extract key values
extract_kb() {
    echo "$meminfo" | grep "^$1:" | awk '{print $2}'
}

mem_total=$(extract_kb "MemTotal")
mem_free=$(extract_kb "MemFree")
mem_available=$(extract_kb "MemAvailable")
buffers=$(extract_kb "Buffers")
cached=$(extract_kb "Cached")
swap_total=$(extract_kb "SwapTotal")
swap_free=$(extract_kb "SwapFree")
dirty=$(extract_kb "Dirty")
slab=$(extract_kb "Slab")

# Calculate percentages
if [[ -n "$mem_total" && "$mem_total" -gt 0 ]]; then
    avail_pct=$((100 * mem_available / mem_total))
    used_pct=$((100 - avail_pct))

    printf "  %-20s %10s KB (%3d%%)\n" "Total:" "$mem_total" "100"
    printf "  %-20s %10s KB (%3d%%)\n" "Available:" "$mem_available" "$avail_pct"
    printf "  %-20s %10s KB\n" "Buffers:" "$buffers"
    printf "  %-20s %10s KB\n" "Cached:" "$cached"
    printf "  %-20s %10s KB\n" "Slab:" "$slab"
    printf "  %-20s %10s KB\n" "Dirty:" "$dirty"

    echo ""

    if [[ -n "$swap_total" && "$swap_total" -gt 0 ]]; then
        swap_used=$((swap_total - swap_free))
        swap_pct=$((100 * swap_used / swap_total))
        printf "  %-20s %10s KB\n" "Swap Total:" "$swap_total"
        printf "  %-20s %10s KB (%3d%% used)\n" "Swap Used:" "$swap_used" "$swap_pct"
    fi

    # Warnings
    echo ""
    if [[ $avail_pct -lt 10 ]]; then
        echo -e "  ${RED}⚠️  CRITICAL: Only $avail_pct% memory available!${NC}"
    elif [[ $avail_pct -lt 20 ]]; then
        echo -e "  ${YELLOW}⚠️  WARNING: Only $avail_pct% memory available${NC}"
    else
        echo -e "  ${GREEN}✓ Memory availability OK ($avail_pct%)${NC}"
    fi
fi

echo ""

# ============================================================================
# Top Memory Consumers
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  TOP MEMORY CONSUMERS (top 15 by RSS)                            │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

run_cmd "ps aux --sort=-%mem | head -16"

echo ""

# ============================================================================
# Swap Activity (vmstat)
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  SWAP/PAGING ACTIVITY (vmstat 1 3)                               │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

run_cmd "vmstat 1 3"

vmstat_out=$(run_cmd "vmstat 1 2 | tail -1")
si=$(echo "$vmstat_out" | awk '{print $7}')
so=$(echo "$vmstat_out" | awk '{print $8}')

echo ""
if [[ "$si" -gt 0 || "$so" -gt 0 ]]; then
    echo -e "  ${YELLOW}⚠️  Active swapping detected (si=$si so=$so)${NC}"
    echo "     System is under memory pressure!"
else
    echo -e "  ${GREEN}✓ No active swapping${NC}"
fi

echo ""

# ============================================================================
# OOM Killer History
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  OOM KILLER HISTORY (dmesg)                                      │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

oom_output=$(run_cmd "dmesg 2>/dev/null | grep -i 'killed process\|oom' | tail -10")

if [[ -n "$oom_output" && "$oom_output" != "ERROR" && "$oom_output" != "N/A" ]]; then
    echo -e "${RED}$oom_output${NC}"
    echo ""
    echo -e "  ${RED}⚠️  OOM kills detected! System ran out of memory.${NC}"
else
    echo -e "  ${GREEN}✓ No OOM kills in dmesg${NC}"
fi

echo ""

# ============================================================================
# Memory Pressure Indicators
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  MEMORY PRESSURE INDICATORS                                      │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

# Check for page scanning activity (indicates memory pressure)
# Note: sar may not be available on all systems
sar_available=$(run_cmd "which sar 2>/dev/null || echo ''")

if [[ -n "$sar_available" && "$sar_available" != "ERROR" && "$sar_available" != "" ]]; then
    echo "Page scanning activity (sar -B):"
    run_cmd "sar -B 1 3" 2>/dev/null || echo "  (sar not available)"
else
    echo "  Note: sar not installed (sysstat package)"
    echo "  Alternative check via /proc/vmstat:"
    echo ""
    run_cmd "grep -E 'pgpgin|pgpgout|pswpin|pswpout|pgfault|pgmajfault' /proc/vmstat"
fi

echo ""

# ============================================================================
# Slab Cache (kernel memory)
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  SLAB CACHE (Top kernel memory consumers)                        │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

slabtop_available=$(run_cmd "which slabtop 2>/dev/null || echo ''")

if [[ -n "$slabtop_available" && "$slabtop_available" != "ERROR" && "$slabtop_available" != "" ]]; then
    run_cmd "slabtop -o | head -15"
else
    # Fallback to /proc/slabinfo
    echo "  Note: slabtop not available, using /proc/slabinfo:"
    echo ""
    run_cmd "cat /proc/slabinfo 2>/dev/null | head -15" || echo "  (slabinfo not readable)"
fi

echo ""

# ============================================================================
# Summary and Recommendations
# ============================================================================

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                    MEMORY ANALYSIS SUMMARY                       ║"
echo "╠══════════════════════════════════════════════════════════════════╣"

issues=""

if [[ -n "$avail_pct" && "$avail_pct" -lt 20 ]]; then
    issues="${issues}LOW_AVAILABLE "
    echo "║  ⚠️  Low available memory ($avail_pct%)                          "
fi

if [[ "$si" -gt 0 || "$so" -gt 0 ]]; then
    issues="${issues}SWAPPING "
    echo "║  ⚠️  Active swapping - memory pressure                         "
fi

if [[ -n "$oom_output" && "$oom_output" != "ERROR" && "$oom_output" != "N/A" && "$oom_output" =~ "killed" ]]; then
    issues="${issues}OOM "
    echo "║  ⚠️  OOM kills occurred - processes were killed                "
fi

if [[ -z "$issues" ]]; then
    echo "║  ✅ Memory appears healthy                                      "
fi

echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  RECOMMENDATIONS:                                                ║"

if [[ "$issues" == *"LOW_AVAILABLE"* ]]; then
    echo "║    - Identify memory-heavy processes above                     ║"
    echo "║    - Consider adding more RAM                                  ║"
    echo "║    - Check for memory leaks in applications                    ║"
fi

if [[ "$issues" == *"SWAPPING"* ]]; then
    echo "║    - Reduce memory usage or add RAM                            ║"
    echo "║    - Consider vm.swappiness tuning                             ║"
fi

if [[ "$issues" == *"OOM"* ]]; then
    echo "║    - Review killed processes and their memory patterns         ║"
    echo "║    - Consider cgroup memory limits                             ║"
    echo "║    - Increase available memory                                 ║"
fi

if [[ -z "$issues" ]]; then
    echo "║    - No immediate action required                              ║"
fi

echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
