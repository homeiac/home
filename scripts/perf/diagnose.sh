#!/bin/bash
#
# diagnose.sh - Orchestrated Performance Diagnosis
#
# Follows the USE Method flowchart automatically:
#   1. USE Method (check all resources)
#   2a. Resource Deep Dive (if issues found)
#   2b. Application Logs (if USE clean)
#   3. Standard Tracing (if app logs point to external)
#
# Usage:
#   ./diagnose.sh --target proxmox-vm:116        # HAOS on chief-horse
#   ./diagnose.sh --target ssh:root@host.maas    # Direct SSH
#   ./diagnose.sh --target k8s-pod:ns/pod        # K8s pod
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_DIR="$SCRIPT_DIR/reports"
mkdir -p "$REPORT_DIR"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
TARGET=""
SERVICE_URL=""
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --target|-t) TARGET="$2"; shift 2 ;;
        --url|-u) SERVICE_URL="$2"; shift 2 ;;
        --verbose|-v) VERBOSE=true; shift ;;
        --help|-h)
            echo "Usage: $0 --target <target> [--url <service-url>]"
            echo ""
            echo "Targets:"
            echo "  proxmox-vm:<vmid>      Proxmox VM (e.g., proxmox-vm:116)"
            echo "  ssh:<user@host>        Direct SSH (e.g., ssh:root@host.maas)"
            echo "  k8s-pod:<ns/pod>       K8s pod (e.g., k8s-pod:frigate/frigate-xyz)"
            echo "  local                  Local machine"
            echo ""
            echo "Options:"
            echo "  --url <url>           Service URL for network timing"
            echo "  --verbose             Show detailed output"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

[[ -z "$TARGET" ]] && { echo "ERROR: --target required"; exit 1; }

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REPORT_FILE="$REPORT_DIR/diagnosis-$TIMESTAMP.json"

log() { echo -e "${BLUE}[DIAG]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }

# Initialize report
cat > "$REPORT_FILE" << EOF
{
  "timestamp": "$TIMESTAMP",
  "target": "$TARGET",
  "steps": []
}
EOF

add_step() {
    local step_name="$1"
    local status="$2"
    local findings="$3"

    # Append to report (simplified - would use jq in production)
    echo "  Step: $step_name -> $status" >> "$REPORT_FILE.log"
    echo "  Findings: $findings" >> "$REPORT_FILE.log"
}

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║        SRE PERFORMANCE DIAGNOSIS - USE METHOD FLOWCHART          ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  Target: $(printf '%-54s' "$TARGET") ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# STEP 1: USE METHOD - Check ALL Resources
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  STEP 1: USE METHOD - Checking All Resources                     │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

USE_RESULT=""
RESOURCE_ISSUES=()

case "$TARGET" in
    proxmox-vm:*)
        VMID="${TARGET#proxmox-vm:}"
        log "Running USE Method on Proxmox VM $VMID..."

        if [[ -x "$SCRIPT_DIR/run-on-proxmox-vm.sh" ]]; then
            USE_OUTPUT=$("$SCRIPT_DIR/run-on-proxmox-vm.sh" "$VMID" 2>&1) || true
            echo "$USE_OUTPUT"

            # Parse for issues
            if echo "$USE_OUTPUT" | grep -qi "INVESTIGATE\|✗\|ERROR"; then
                USE_RESULT="ISSUES_FOUND"
            else
                USE_RESULT="ALL_OK"
            fi

            # Check specific thresholds
            # Memory > 90%
            if echo "$USE_OUTPUT" | grep -E "Mem:.*[89][0-9]%|Mem:.*100%" >/dev/null 2>&1; then
                RESOURCE_ISSUES+=("MEMORY")
            fi
            # Check for available memory < 500MB
            if echo "$USE_OUTPUT" | grep -E "available.*[0-9]{1,3}$" >/dev/null 2>&1; then
                RESOURCE_ISSUES+=("MEMORY")
            fi
            # CPU load > nproc
            # Hardware errors
            if echo "$USE_OUTPUT" | grep -qi "Hardware error\|MCE\|mce"; then
                RESOURCE_ISSUES+=("CPU_ERROR")
            fi
            # OOM
            if echo "$USE_OUTPUT" | grep -qi "OOM\|killed process"; then
                RESOURCE_ISSUES+=("MEMORY_OOM")
            fi
        else
            error "run-on-proxmox-vm.sh not found"
            exit 1
        fi
        ;;

    ssh:*)
        HOST="${TARGET#ssh:}"
        log "Running USE Method via SSH to $HOST..."

        if [[ -x "$SCRIPT_DIR/use-checklist.sh" ]]; then
            USE_OUTPUT=$("$SCRIPT_DIR/use-checklist.sh" --context "ssh:$HOST" 2>&1) || true
            echo "$USE_OUTPUT"

            if echo "$USE_OUTPUT" | grep -qi "INVESTIGATE\|✗\|ERROR"; then
                USE_RESULT="ISSUES_FOUND"
            else
                USE_RESULT="ALL_OK"
            fi
        else
            error "use-checklist.sh not found"
            exit 1
        fi
        ;;

    k8s-pod:*)
        POD="${TARGET#k8s-pod:}"
        log "Running USE Method on K8s pod $POD..."
        # TODO: Implement k8s pod context
        warn "K8s pod context not yet implemented"
        USE_RESULT="SKIP"
        ;;

    local)
        log "Running USE Method locally..."
        if [[ -x "$SCRIPT_DIR/quick-triage.sh" ]]; then
            USE_OUTPUT=$("$SCRIPT_DIR/quick-triage.sh" 2>&1) || true
            echo "$USE_OUTPUT"
            USE_RESULT="ALL_OK"  # Parse output for issues
        fi
        ;;

    *)
        error "Unknown target type: $TARGET"
        exit 1
        ;;
esac

echo ""
add_step "USE_METHOD" "$USE_RESULT" "${RESOURCE_ISSUES[*]:-none}"

# ============================================================================
# DECISION POINT: Resource Issues Found?
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  DECISION POINT                                                  │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

if [[ ${#RESOURCE_ISSUES[@]} -gt 0 ]]; then
    warn "Resource issues detected: ${RESOURCE_ISSUES[*]}"
    echo ""
    echo "→ Taking path: STEP 2a (Resource Deep Dive)"
    NEXT_STEP="2a"
else
    success "All resources appear OK"
    echo ""
    echo "→ Taking path: STEP 2b (Application Layer)"
    NEXT_STEP="2b"
fi

echo ""

# ============================================================================
# STEP 2a: Resource Deep Dive (if issues found)
# ============================================================================

if [[ "$NEXT_STEP" == "2a" ]]; then
    echo "┌──────────────────────────────────────────────────────────────────┐"
    echo "│  STEP 2a: Resource Deep Dive                                     │"
    echo "└──────────────────────────────────────────────────────────────────┘"
    echo ""

    for issue in "${RESOURCE_ISSUES[@]}"; do
        case "$issue" in
            MEMORY|MEMORY_OOM)
                log "Running memory deep dive..."
                if [[ -x "$SCRIPT_DIR/memory-deep-dive.sh" ]]; then
                    "$SCRIPT_DIR/memory-deep-dive.sh" --target "$TARGET"
                else
                    warn "memory-deep-dive.sh not found - showing manual commands:"
                    echo "  free -m"
                    echo "  ps aux --sort=-%mem | head -20"
                    echo "  cat /proc/meminfo | grep -E 'MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapTotal|SwapFree'"
                    echo "  vmstat 1 5"
                fi
                ;;
            CPU_ERROR)
                log "CPU hardware error detected - checking dmesg..."
                warn "Hardware errors require physical investigation"
                echo "  Commands to run:"
                echo "  dmesg | grep -i 'mce\|hardware error'"
                echo "  mcelog --client  (if mcelog installed)"
                ;;
            CPU_HIGH)
                log "Running CPU deep dive..."
                if [[ -x "$SCRIPT_DIR/cpu-deep-dive.sh" ]]; then
                    "$SCRIPT_DIR/cpu-deep-dive.sh" --target "$TARGET"
                else
                    warn "cpu-deep-dive.sh not found - showing manual commands:"
                    echo "  mpstat -P ALL 1 5"
                    echo "  pidstat 1 5"
                    echo "  top -b -n 1 | head -20"
                fi
                ;;
            DISK_IO)
                log "Running disk deep dive..."
                if [[ -x "$SCRIPT_DIR/disk-deep-dive.sh" ]]; then
                    "$SCRIPT_DIR/disk-deep-dive.sh" --target "$TARGET"
                else
                    warn "disk-deep-dive.sh not found - showing manual commands:"
                    echo "  iostat -xz 1 5"
                    echo "  iotop -b -n 3"
                fi
                ;;
        esac
    done

    echo ""
    echo "┌──────────────────────────────────────────────────────────────────┐"
    echo "│  RESOURCE DEEP DIVE COMPLETE                                     │"
    echo "│                                                                  │"
    echo "│  Root cause likely in: ${RESOURCE_ISSUES[*]}"
    echo "│                                                                  │"
    echo "│  Recommended actions:                                            │"
    for issue in "${RESOURCE_ISSUES[@]}"; do
        case "$issue" in
            MEMORY) echo "│    - Investigate memory consumers, consider increasing RAM    │" ;;
            MEMORY_OOM) echo "│    - Check OOM killed processes, increase memory limits   │" ;;
            CPU_ERROR) echo "│    - Hardware error - check CPU/motherboard, run memtest   │" ;;
            CPU_HIGH) echo "│    - Identify CPU-heavy processes, optimize or add cores   │" ;;
            DISK_IO) echo "│    - Check disk health, consider SSD, optimize I/O patterns │" ;;
        esac
    done
    echo "└──────────────────────────────────────────────────────────────────┘"

    add_step "RESOURCE_DEEP_DIVE" "COMPLETE" "${RESOURCE_ISSUES[*]}"
fi

# ============================================================================
# STEP 2b: Application Layer (if USE clean)
# ============================================================================

if [[ "$NEXT_STEP" == "2b" ]]; then
    echo "┌──────────────────────────────────────────────────────────────────┐"
    echo "│  STEP 2b: Application Layer Analysis                             │"
    echo "└──────────────────────────────────────────────────────────────────┘"
    echo ""

    log "USE Method showed all resources OK - checking application layer..."

    if [[ -x "$SCRIPT_DIR/app-logs.sh" ]]; then
        "$SCRIPT_DIR/app-logs.sh" --target "$TARGET"
    else
        warn "app-logs.sh not found - showing manual approach:"
        echo ""
        echo "  Check application logs for timing info:"
        echo "    journalctl -u <service> --since '10 minutes ago'"
        echo "    kubectl logs <pod> --tail=100"
        echo "    docker logs <container> --tail=100"
        echo ""
        echo "  Look for:"
        echo "    - 'Request took X seconds'"
        echo "    - 'Timeout'"
        echo "    - 'Connection refused'"
        echo "    - External service latency"
    fi

    echo ""

    # If service URL provided, go to Step 3
    if [[ -n "$SERVICE_URL" ]]; then
        echo "→ Service URL provided, proceeding to STEP 3 (Standard Tracing)"
        NEXT_STEP="3"
    else
        echo ""
        echo "┌──────────────────────────────────────────────────────────────────┐"
        echo "│  APPLICATION LAYER ANALYSIS COMPLETE                             │"
        echo "│                                                                  │"
        echo "│  If logs reveal external service latency, re-run with:           │"
        echo "│    $0 --target $TARGET --url <service-url>"
        echo "└──────────────────────────────────────────────────────────────────┘"
    fi

    add_step "APPLICATION_LAYER" "COMPLETE" "Check logs manually"
fi

# ============================================================================
# STEP 3: Standard Tracing Tools
# ============================================================================

if [[ "$NEXT_STEP" == "3" && -n "$SERVICE_URL" ]]; then
    echo ""
    echo "┌──────────────────────────────────────────────────────────────────┐"
    echo "│  STEP 3: Standard Tracing Tools                                  │"
    echo "└──────────────────────────────────────────────────────────────────┘"
    echo ""

    # Network timing
    log "Running network timing analysis for: $SERVICE_URL"

    if [[ -x "$SCRIPT_DIR/network-timing.sh" ]]; then
        "$SCRIPT_DIR/network-timing.sh" "$SERVICE_URL"
    else
        warn "network-timing.sh not found - running inline..."
        echo ""
        echo "Network Timing Breakdown:"
        echo "─────────────────────────"
        curl -w "  DNS Lookup:    %{time_namelookup}s
  TCP Connect:   %{time_connect}s
  TLS Handshake: %{time_appconnect}s
  TTFB:          %{time_starttransfer}s
  Total:         %{time_total}s

  Size:          %{size_download} bytes
  HTTP Code:     %{http_code}
" -o /dev/null -s "$SERVICE_URL" 2>/dev/null || echo "  (curl failed)"
    fi

    echo ""
    echo "┌──────────────────────────────────────────────────────────────────┐"
    echo "│  NETWORK TIMING INTERPRETATION                                   │"
    echo "├──────────────────────────────────────────────────────────────────┤"
    echo "│  DNS slow (>100ms)?     → Check /etc/resolv.conf, DNS server    │"
    echo "│  TCP slow (>100ms)?     → Firewall, routing, network path       │"
    echo "│  TLS slow (>200ms)?     → Certificate issues, cipher overhead   │"
    echo "│  TTFB slow?             → Server processing time                │"
    echo "│  Total slow but OK?     → Large response, bandwidth limit       │"
    echo "└──────────────────────────────────────────────────────────────────┘"

    add_step "NETWORK_TIMING" "COMPLETE" "See timing breakdown above"

    # Additional tracing suggestions
    echo ""
    echo "Additional tracing (run on target host):"
    echo "  tcpconnect-bpfcc          # Watch new TCP connections"
    echo "  tcplife-bpfcc             # TCP session durations"
    echo "  gethostlatency-bpfcc      # DNS query latency"
    echo "  tcpdump -i any port 8123  # Packet capture"
fi

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                    DIAGNOSIS COMPLETE                            ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  Report: $REPORT_FILE"
echo "║  Log:    $REPORT_FILE.log"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
