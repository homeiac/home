#!/bin/bash
#
# app-logs.sh - Application layer log analysis
#
# Used in Step 2b of the diagnosis flowchart when USE Method shows
# all resources OK. Looks for timing info, errors, and external
# service latency in application logs.
#
# Usage:
#   ./app-logs.sh --target proxmox-vm:116 --service homeassistant
#   ./app-logs.sh --target k8s-pod:frigate/frigate-xyz
#   ./app-logs.sh --target ssh:root@host.maas --service nginx
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
SERVICE=""
SINCE="10 minutes ago"
LINES=100

while [[ $# -gt 0 ]]; do
    case $1 in
        --target|-t) TARGET="$2"; shift 2 ;;
        --service|-s) SERVICE="$2"; shift 2 ;;
        --since) SINCE="$2"; shift 2 ;;
        --lines|-n) LINES="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 --target <target> [--service <name>]"
            echo ""
            echo "Targets:"
            echo "  proxmox-vm:<vmid>    Proxmox VM"
            echo "  k8s-pod:<ns/pod>     Kubernetes pod"
            echo "  docker:<container>   Docker container"
            echo "  ssh:<user@host>      Direct SSH (requires --service)"
            echo "  local                Local systemd service"
            echo ""
            echo "Options:"
            echo "  --service <name>     Service/container name"
            echo "  --since <time>       Time range (default: '10 minutes ago')"
            echo "  --lines <n>          Number of lines (default: 100)"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

[[ -z "$TARGET" ]] && { echo "ERROR: --target required"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                APPLICATION LOG ANALYSIS                          ║"
echo "║    (Step 2b: USE Method clean → check application layer)         ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
printf "║  Target:  %-54s ║\n" "$TARGET"
printf "║  Service: %-54s ║\n" "${SERVICE:-auto-detect}"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# Patterns to search for in logs
TIMING_PATTERNS="took [0-9]+|duration|latency|elapsed|response time|ms$|seconds"
ERROR_PATTERNS="error|exception|failed|timeout|refused|unreachable"
EXTERNAL_PATTERNS="request to|calling|connecting to|waiting for"

highlight_patterns() {
    # Highlight timing, errors, and external calls
    sed -E \
        -e "s/($ERROR_PATTERNS)/${RED}\1${NC}/gi" \
        -e "s/([0-9]+\s*(ms|seconds|s)\b)/${YELLOW}\1${NC}/gi" \
        -e "s/(timeout|timed out)/${RED}\1${NC}/gi"
}

# ============================================================================
# Fetch logs based on target type
# ============================================================================

fetch_logs() {
    case "$TARGET" in
        proxmox-vm:*)
            VMID="${TARGET#proxmox-vm:}"
            # Map VMID to host
            case "$VMID" in
                116|109) HOST="chief-horse.maas" ;;
                108) HOST="still-fawn.maas" ;;
                105) HOST="pumped-piglet.maas" ;;
                *) HOST="chief-horse.maas" ;;
            esac

            echo "Fetching logs from Proxmox VM $VMID on $HOST..."
            echo ""

            # For HAOS (VM 116), check specific log locations
            if [[ "$VMID" == "116" ]]; then
                echo "┌──────────────────────────────────────────────────────────────────┐"
                echo "│  HOME ASSISTANT OS (HAOS) LOGS                                   │"
                echo "└──────────────────────────────────────────────────────────────────┘"
                echo ""
                echo "Note: HAOS has limited shell access. Check logs via:"
                echo ""
                echo "  1. HA Web UI → Settings → System → Logs"
                echo "  2. HA API:"
                echo "     curl -H 'Authorization: Bearer \$HA_TOKEN' \\"
                echo "          http://homeassistant.maas:8123/api/error_log"
                echo ""
                echo "  3. Supervisor logs (if SSH addon installed):"
                echo "     ha core logs"
                echo "     ha supervisor logs"
                echo ""

                # Try to fetch via API if HA_TOKEN is available
                if [[ -f "$SCRIPT_DIR/../../proxmox/homelab/.env" ]]; then
                    HA_TOKEN=$(grep "^HA_TOKEN=" "$SCRIPT_DIR/../../proxmox/homelab/.env" 2>/dev/null | cut -d'=' -f2- | tr -d '"' || echo "")
                    if [[ -n "$HA_TOKEN" ]]; then
                        echo "Attempting to fetch HA error log via API..."
                        echo ""
                        curl -s -H "Authorization: Bearer $HA_TOKEN" \
                            "http://homeassistant.maas:8123/api/error_log" 2>/dev/null | \
                            tail -$LINES | highlight_patterns || echo "(API fetch failed)"
                    fi
                fi
            else
                # Generic VM - try journalctl
                ssh "root@$HOST" "qm guest exec $VMID -- journalctl --since '$SINCE' -n $LINES" 2>/dev/null | \
                    python3 -c "import sys,json; print(json.load(sys.stdin).get('out-data',''))" 2>/dev/null | \
                    highlight_patterns || echo "(Could not fetch logs)"
            fi
            ;;

        k8s-pod:*)
            POD="${TARGET#k8s-pod:}"
            NS="${POD%/*}"
            PODNAME="${POD#*/}"

            echo "Fetching logs from K8s pod $PODNAME in namespace $NS..."
            echo ""

            echo "┌──────────────────────────────────────────────────────────────────┐"
            echo "│  KUBERNETES POD LOGS                                             │"
            echo "└──────────────────────────────────────────────────────────────────┘"
            echo ""

            KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
            kubectl --kubeconfig="$KUBECONFIG" logs -n "$NS" "$PODNAME" --tail="$LINES" 2>/dev/null | \
                highlight_patterns || echo "(Could not fetch pod logs)"
            ;;

        docker:*)
            CONTAINER="${TARGET#docker:}"

            echo "Fetching logs from Docker container $CONTAINER..."
            echo ""

            echo "┌──────────────────────────────────────────────────────────────────┐"
            echo "│  DOCKER CONTAINER LOGS                                           │"
            echo "└──────────────────────────────────────────────────────────────────┘"
            echo ""

            docker logs "$CONTAINER" --tail="$LINES" 2>&1 | \
                highlight_patterns || echo "(Could not fetch container logs)"
            ;;

        ssh:*)
            HOST="${TARGET#ssh:}"

            if [[ -z "$SERVICE" ]]; then
                echo "ERROR: --service required for SSH target"
                echo "       e.g., --service nginx"
                return 1
            fi

            echo "Fetching logs for $SERVICE on $HOST..."
            echo ""

            echo "┌──────────────────────────────────────────────────────────────────┐"
            echo "│  SYSTEMD SERVICE LOGS                                            │"
            echo "└──────────────────────────────────────────────────────────────────┘"
            echo ""

            ssh "$HOST" "journalctl -u $SERVICE --since '$SINCE' -n $LINES" 2>/dev/null | \
                highlight_patterns || echo "(Could not fetch service logs)"
            ;;

        local)
            if [[ -z "$SERVICE" ]]; then
                echo "ERROR: --service required for local target"
                return 1
            fi

            echo "┌──────────────────────────────────────────────────────────────────┐"
            echo "│  LOCAL SYSTEMD SERVICE LOGS                                      │"
            echo "└──────────────────────────────────────────────────────────────────┘"
            echo ""

            journalctl -u "$SERVICE" --since "$SINCE" -n "$LINES" 2>/dev/null | \
                highlight_patterns || echo "(Could not fetch service logs)"
            ;;

        *)
            echo "Unknown target type: $TARGET"
            return 1
            ;;
    esac
}

# Run log fetch
fetch_logs

echo ""

# ============================================================================
# Analysis guidance
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  WHAT TO LOOK FOR                                                │"
echo "├──────────────────────────────────────────────────────────────────┤"
echo "│                                                                  │"
echo "│  TIMING INFORMATION:                                             │"
echo "│    - 'Request took X seconds'                                    │"
echo "│    - 'duration: 500ms'                                           │"
echo "│    - Slow response times (>1s usually indicates issue)           │"
echo "│                                                                  │"
echo "│  ERROR PATTERNS:                                                 │"
echo "│    - 'timeout' or 'timed out'                                    │"
echo "│    - 'connection refused'                                        │"
echo "│    - 'error' or 'exception'                                      │"
echo "│                                                                  │"
echo "│  EXTERNAL SERVICE LATENCY:                                       │"
echo "│    - 'Calling <service>...'                                      │"
echo "│    - 'Waiting for response from...'                              │"
echo "│    - Database query times                                        │"
echo "│    - API call durations                                          │"
echo "│                                                                  │"
echo "├──────────────────────────────────────────────────────────────────┤"
echo "│  NEXT STEPS:                                                     │"
echo "│                                                                  │"
echo "│  If logs show external service latency → Use network-timing.sh:  │"
echo "│    ./network-timing.sh http://<external-service>/                │"
echo "│                                                                  │"
echo "│  If logs show internal processing time → Profile application:    │"
echo "│    - Add more detailed timing logs                               │"
echo "│    - Use application-specific profiling tools                    │"
echo "│                                                                  │"
echo "│  If no timing info in logs → Add instrumentation                 │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""
