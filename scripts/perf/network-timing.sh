#!/bin/bash
#
# network-timing.sh - Network timing breakdown using curl
#
# Shows where time is spent in network requests:
#   - DNS lookup
#   - TCP connect
#   - TLS handshake
#   - Time to first byte (TTFB)
#   - Total time
#
# Usage:
#   ./network-timing.sh http://service.homelab:8123/api/
#   ./network-timing.sh --repeat 5 http://service.homelab:8123/api/
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
REPEAT=1
URL=""
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --repeat|-r) REPEAT="$2"; shift 2 ;;
        --verbose|-v) VERBOSE=true; shift ;;
        --help|-h)
            echo "Usage: $0 [options] <url>"
            echo ""
            echo "Options:"
            echo "  --repeat N    Run N times and show stats (default: 1)"
            echo "  --verbose     Show detailed output"
            echo ""
            echo "Example:"
            echo "  $0 http://homeassistant.maas:8123/api/"
            echo "  $0 --repeat 5 http://frigate.homelab/api/stats"
            exit 0
            ;;
        http://*|https://*) URL="$1"; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

[[ -z "$URL" ]] && { echo "ERROR: URL required"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                    NETWORK TIMING ANALYSIS                       ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
printf "║  URL: %-58s ║\n" "${URL:0:58}"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# curl format string
CURL_FORMAT='
{
  "dns_lookup": %{time_namelookup},
  "tcp_connect": %{time_connect},
  "tls_handshake": %{time_appconnect},
  "ttfb": %{time_starttransfer},
  "total": %{time_total},
  "http_code": %{http_code},
  "size_download": %{size_download},
  "speed_download": %{speed_download},
  "num_connects": %{num_connects},
  "num_redirects": %{num_redirects}
}'

run_timing() {
    curl -w "$CURL_FORMAT" -o /dev/null -s "$URL" 2>/dev/null || echo '{"error": true}'
}

# Thresholds (in seconds)
DNS_WARN=0.1
TCP_WARN=0.1
TLS_WARN=0.2
TTFB_WARN=0.5
TOTAL_WARN=1.0

format_time() {
    local time="$1"
    local threshold="$2"
    local name="$3"

    # Convert to milliseconds for display
    local ms=$(echo "$time * 1000" | bc 2>/dev/null || echo "0")

    if (( $(echo "$time > $threshold" | bc -l 2>/dev/null || echo 0) )); then
        printf "${YELLOW}%s${NC}" "${ms%.*}ms"
    else
        printf "${GREEN}%s${NC}" "${ms%.*}ms"
    fi
}

if [[ $REPEAT -eq 1 ]]; then
    # Single run - detailed output
    echo "Running single timing request..."
    echo ""

    result=$(run_timing)

    if echo "$result" | grep -q '"error"'; then
        echo -e "${RED}ERROR: Could not connect to $URL${NC}"
        exit 1
    fi

    # Parse JSON (simple grep, would use jq in production)
    dns=$(echo "$result" | grep -o '"dns_lookup": [0-9.]*' | cut -d' ' -f2)
    tcp=$(echo "$result" | grep -o '"tcp_connect": [0-9.]*' | cut -d' ' -f2)
    tls=$(echo "$result" | grep -o '"tls_handshake": [0-9.]*' | cut -d' ' -f2)
    ttfb=$(echo "$result" | grep -o '"ttfb": [0-9.]*' | cut -d' ' -f2)
    total=$(echo "$result" | grep -o '"total": [0-9.]*' | cut -d' ' -f2)
    code=$(echo "$result" | grep -o '"http_code": [0-9]*' | cut -d' ' -f2)
    size=$(echo "$result" | grep -o '"size_download": [0-9]*' | cut -d' ' -f2)

    # Calculate deltas (time spent in each phase)
    tcp_delta=$(echo "$tcp - $dns" | bc 2>/dev/null || echo "0")
    tls_delta=$(echo "$tls - $tcp" | bc 2>/dev/null || echo "0")
    ttfb_delta=$(echo "$ttfb - $tls" | bc 2>/dev/null || echo "0")
    transfer_delta=$(echo "$total - $ttfb" | bc 2>/dev/null || echo "0")

    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  TIMING BREAKDOWN (cumulative)                              │"
    echo "├─────────────────────────────────────────────────────────────┤"
    printf "│  DNS Lookup:     %10s  (resolve hostname)             │\n" "$(format_time "$dns" "$DNS_WARN" "DNS")"
    printf "│  TCP Connect:    %10s  (establish connection)         │\n" "$(format_time "$tcp" "$TCP_WARN" "TCP")"

    if [[ "$URL" == https://* ]]; then
        printf "│  TLS Handshake:  %10s  (SSL/TLS negotiation)          │\n" "$(format_time "$tls" "$TLS_WARN" "TLS")"
    fi

    printf "│  TTFB:           %10s  (wait for first byte)          │\n" "$(format_time "$ttfb" "$TTFB_WARN" "TTFB")"
    printf "│  Total:          %10s  (complete request)             │\n" "$(format_time "$total" "$TOTAL_WARN" "Total")"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│  HTTP Code: $code    Size: ${size} bytes"
    echo "└─────────────────────────────────────────────────────────────┘"

    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  TIME SPENT IN EACH PHASE                                   │"
    echo "├─────────────────────────────────────────────────────────────┤"

    # Visual bar chart
    scale=50  # characters wide

    show_bar() {
        local name="$1"
        local delta="$2"
        local total_time="$3"

        local pct=$(echo "scale=0; $delta / $total_time * 100" | bc 2>/dev/null || echo "0")
        local bar_len=$(echo "scale=0; $delta / $total_time * $scale" | bc 2>/dev/null || echo "0")

        printf "│  %-12s " "$name"
        for ((i=0; i<bar_len && i<50; i++)); do printf "█"; done
        for ((i=bar_len; i<50; i++)); do printf " "; done
        printf " │\n"
    }

    show_bar "DNS" "$dns" "$total"
    show_bar "TCP" "$tcp_delta" "$total"
    if [[ "$URL" == https://* ]]; then
        show_bar "TLS" "$tls_delta" "$total"
    fi
    show_bar "Server" "$ttfb_delta" "$total"
    show_bar "Transfer" "$transfer_delta" "$total"

    echo "└─────────────────────────────────────────────────────────────┘"

    # Interpretation
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  INTERPRETATION                                             │"
    echo "├─────────────────────────────────────────────────────────────┤"

    issues_found=false

    if (( $(echo "$dns > $DNS_WARN" | bc -l 2>/dev/null || echo 0) )); then
        echo "│  ⚠️  DNS slow - check /etc/resolv.conf, DNS server         │"
        issues_found=true
    fi

    if (( $(echo "$tcp_delta > $TCP_WARN" | bc -l 2>/dev/null || echo 0) )); then
        echo "│  ⚠️  TCP slow - check firewall, routing, network path      │"
        issues_found=true
    fi

    if [[ "$URL" == https://* ]] && (( $(echo "$tls_delta > $TLS_WARN" | bc -l 2>/dev/null || echo 0) )); then
        echo "│  ⚠️  TLS slow - certificate issues, cipher overhead        │"
        issues_found=true
    fi

    if (( $(echo "$ttfb_delta > $TTFB_WARN" | bc -l 2>/dev/null || echo 0) )); then
        echo "│  ⚠️  TTFB slow - server processing time is the bottleneck  │"
        issues_found=true
    fi

    if [[ "$issues_found" == "false" ]]; then
        echo "│  ✅ All timing metrics within normal range                 │"
    fi

    echo "└─────────────────────────────────────────────────────────────┘"

else
    # Multiple runs - statistical output
    echo "Running $REPEAT timing requests..."
    echo ""

    declare -a dns_times tcp_times tls_times ttfb_times total_times

    for ((i=1; i<=REPEAT; i++)); do
        printf "  Request %d/%d..." "$i" "$REPEAT"
        result=$(run_timing)

        if echo "$result" | grep -q '"error"'; then
            echo " ERROR"
            continue
        fi

        dns=$(echo "$result" | grep -o '"dns_lookup": [0-9.]*' | cut -d' ' -f2)
        total=$(echo "$result" | grep -o '"total": [0-9.]*' | cut -d' ' -f2)

        dns_times+=("$dns")
        total_times+=("$total")

        echo " ${total}s"
        sleep 0.5
    done

    echo ""

    # Calculate stats (simplified - would use proper stats in production)
    calc_avg() {
        local arr=("$@")
        local sum=0
        for v in "${arr[@]}"; do
            sum=$(echo "$sum + $v" | bc)
        done
        echo "scale=3; $sum / ${#arr[@]}" | bc
    }

    calc_min() {
        local arr=("$@")
        local min="${arr[0]}"
        for v in "${arr[@]}"; do
            if (( $(echo "$v < $min" | bc -l) )); then
                min="$v"
            fi
        done
        echo "$min"
    }

    calc_max() {
        local arr=("$@")
        local max="${arr[0]}"
        for v in "${arr[@]}"; do
            if (( $(echo "$v > $max" | bc -l) )); then
                max="$v"
            fi
        done
        echo "$max"
    }

    avg_total=$(calc_avg "${total_times[@]}")
    min_total=$(calc_min "${total_times[@]}")
    max_total=$(calc_max "${total_times[@]}")

    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  STATISTICS ($REPEAT requests)                              "
    echo "├─────────────────────────────────────────────────────────────┤"
    printf "│  Average:  %8ss                                        │\n" "$avg_total"
    printf "│  Min:      %8ss                                        │\n" "$min_total"
    printf "│  Max:      %8ss                                        │\n" "$max_total"
    echo "└─────────────────────────────────────────────────────────────┘"
fi

echo ""
