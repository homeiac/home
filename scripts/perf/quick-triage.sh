#!/bin/bash
#
# Quick Triage - 60-Second Linux Performance Analysis
# Based on Brendan Gregg's methodology
# https://netflixtechblog.com/linux-performance-analysis-in-60-000-milliseconds-accc10403c55
#
# Run these 10 commands first to get a high-level view before diving deeper.
# Order follows USE method: look for Errors first, then Utilization/Saturation.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Parse arguments
CONTEXT=""
TARGET_CMD=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --context)
            CONTEXT="$2"
            shift 2
            ;;
        --help|-h)
            echo "Quick Triage - 60-Second Linux Performance Analysis"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --context TYPE:TARGET  Execution context"
            echo ""
            echo "Contexts:"
            echo "  ssh:hostname           Remote host via SSH"
            echo "  k8s-pod:namespace/pod  K8s pod"
            echo "  (none)                 Local system"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Build target command prefix
if [[ -n "$CONTEXT" ]]; then
    context_type="${CONTEXT%%:*}"
    context_target="${CONTEXT#*:}"
    case "$context_type" in
        "ssh")
            TARGET_CMD="ssh $context_target"
            ;;
        "k8s-pod")
            ns="${context_target%%/*}"
            pod="${context_target#*/}"
            TARGET_CMD="kubectl exec -n $ns $pod --"
            ;;
        *)
            TARGET_CMD=""
            ;;
    esac
fi

run_cmd() {
    if [[ -n "$TARGET_CMD" ]]; then
        $TARGET_CMD bash -c "$1" 2>/dev/null || echo "N/A"
    else
        eval "$1" 2>/dev/null || echo "N/A"
    fi
}

print_section() {
    echo ""
    echo -e "${BOLD}${BLUE}━━━ $1 ━━━${NC}"
}

echo -e "${BOLD}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  60-Second Linux Performance Triage                           ║"
echo "║  Based on Brendan Gregg's methodology                         ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

if [[ -n "$CONTEXT" ]]; then
    echo -e "Target: ${CYAN}$CONTEXT${NC}"
else
    echo -e "Target: ${CYAN}localhost${NC}"
fi
echo -e "Time:   ${CYAN}$(date)${NC}"

# ============================================================================
# 1. uptime - Load averages (quick saturation indicator)
# ============================================================================
print_section "1. UPTIME - Load averages"
echo -e "${CYAN}What to look for:${NC} Load > CPU count = saturation"
run_cmd "uptime"

# ============================================================================
# 2. dmesg - Kernel errors (ERRORS FIRST per USE method)
# ============================================================================
print_section "2. DMESG - Recent kernel messages (ERRORS)"
echo -e "${CYAN}What to look for:${NC} oom-killer, I/O errors, hardware errors"
result=$(run_cmd "dmesg -T 2>/dev/null | tail -15 || dmesg | tail -15")
# Highlight errors
echo "$result" | while read -r line; do
    if echo "$line" | grep -qiE "error|fail|oom|kill|warn"; then
        echo -e "${RED}$line${NC}"
    else
        echo "$line"
    fi
done

# ============================================================================
# 3. vmstat - CPU, memory, swap overview
# ============================================================================
print_section "3. VMSTAT - CPU, memory, swap (1 sec intervals)"
echo -e "${CYAN}Columns:${NC} r=run queue, b=blocked, si/so=swap, us/sy/id=CPU"
echo -e "${CYAN}What to look for:${NC} r > CPU count, si/so > 0, high us+sy"
run_cmd "vmstat 1 5"

# ============================================================================
# 4. mpstat - Per-CPU utilization
# ============================================================================
print_section "4. MPSTAT - Per-CPU breakdown"
echo -e "${CYAN}What to look for:${NC} Imbalanced CPUs, high %sys, high %iowait"
result=$(run_cmd "command -v mpstat >/dev/null && mpstat -P ALL 1 2 || echo 'mpstat not installed'")
echo "$result"

# ============================================================================
# 5. pidstat - Per-process CPU
# ============================================================================
print_section "5. PIDSTAT - Top CPU consumers"
echo -e "${CYAN}What to look for:${NC} Which processes are consuming CPU"
result=$(run_cmd "command -v pidstat >/dev/null && pidstat 1 3 || echo 'pidstat not installed (sysstat package)'")
echo "$result" | head -20

# ============================================================================
# 6. iostat - Disk I/O
# ============================================================================
print_section "6. IOSTAT - Disk I/O utilization"
echo -e "${CYAN}Columns:${NC} %util=busy, await=latency(ms), avgqu-sz=queue"
echo -e "${CYAN}What to look for:${NC} %util > 70%, await > 10ms, avgqu-sz > 1"
result=$(run_cmd "command -v iostat >/dev/null && iostat -xz 1 2 || echo 'iostat not installed (sysstat package)'")
echo "$result"

# ============================================================================
# 7. free - Memory state
# ============================================================================
print_section "7. FREE - Memory utilization"
echo -e "${CYAN}What to look for:${NC} Low 'available', high 'used'"
run_cmd "free -m"

# ============================================================================
# 8. sar -n DEV - Network throughput
# ============================================================================
print_section "8. SAR - Network device throughput"
echo -e "${CYAN}What to look for:${NC} High rxkB/s or txkB/s near link capacity"
result=$(run_cmd "command -v sar >/dev/null && sar -n DEV 1 2 || echo 'sar not installed (sysstat package)'")
echo "$result" | grep -v "^$" | head -15

# ============================================================================
# 9. sar -n TCP - TCP stats
# ============================================================================
print_section "9. SAR - TCP statistics"
echo -e "${CYAN}What to look for:${NC} retrans/s > 0 = network congestion"
result=$(run_cmd "command -v sar >/dev/null && sar -n TCP,ETCP 1 2 || echo 'sar not installed'")
echo "$result" | grep -v "^$" | head -10

# ============================================================================
# 10. top - Process overview
# ============================================================================
print_section "10. TOP - Process snapshot"
echo -e "${CYAN}What to look for:${NC} Top consumers of CPU/memory"
result=$(run_cmd "top -b -n 1 2>/dev/null || ps aux --sort=-%cpu | head -15")
echo "$result" | head -20

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${BOLD}${GREEN}━━━ QUICK TRIAGE COMPLETE ━━━${NC}"
echo ""
echo "Next steps based on findings:"
echo "  - High CPU?      → Run: cpu-deep-dive.sh"
echo "  - Memory issues? → Run: memory-deep-dive.sh"
echo "  - Disk I/O?      → Run: disk-deep-dive.sh"
echo "  - Network?       → Run: network-deep-dive.sh"
echo ""
echo "  - Full USE Method sweep: use-checklist.sh"
echo ""
