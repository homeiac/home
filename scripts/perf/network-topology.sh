#!/bin/bash
#
# network-topology.sh - Analyze network path between two endpoints
#
# Used when services are on different subnets and latency could be
# caused by routing, NAT, or firewall traversal.
#
# Usage:
#   ./network-topology.sh --from <source> --to <target>
#   ./network-topology.sh --from 192.168.86.245 --to 192.168.4.240
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

FROM=""
TO=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --from|-f) FROM="$2"; shift 2 ;;
        --to|-t) TO="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 --from <source-ip> --to <target-ip>"
            echo ""
            echo "Analyzes network topology between two endpoints."
            echo ""
            echo "Example:"
            echo "  $0 --from 192.168.86.245 --to 192.168.4.240"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

[[ -z "$FROM" ]] && { echo "ERROR: --from required"; exit 1; }
[[ -z "$TO" ]] && { echo "ERROR: --to required"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                  NETWORK TOPOLOGY ANALYSIS                       ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
printf "║  From: %-56s ║\n" "$FROM"
printf "║  To:   %-56s ║\n" "$TO"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# Extract subnet info
# ============================================================================

extract_subnet() {
    local ip="$1"
    echo "$ip" | cut -d. -f1-3
}

FROM_SUBNET=$(extract_subnet "$FROM")
TO_SUBNET=$(extract_subnet "$TO")

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  SUBNET ANALYSIS                                                 │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

printf "  Source subnet: %s.0/24\n" "$FROM_SUBNET"
printf "  Target subnet: %s.0/24\n" "$TO_SUBNET"
echo ""

if [[ "$FROM_SUBNET" == "$TO_SUBNET" ]]; then
    echo -e "  ${GREEN}✓ Same subnet - direct L2 communication${NC}"
    echo "    No routing required, minimal latency expected"
else
    echo -e "  ${YELLOW}⚠ Different subnets - requires routing${NC}"
    echo "    Traffic must traverse router/gateway"
    echo ""
    echo "    Potential latency sources:"
    echo "      - Router processing"
    echo "      - NAT translation (if applicable)"
    echo "      - Firewall inspection"
    echo "      - Inter-VLAN routing"
fi

echo ""

# ============================================================================
# Check route from this machine
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  ROUTE FROM THIS MACHINE                                         │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

echo "  Route to source ($FROM):"
if command -v route &>/dev/null; then
    route -n get "$FROM" 2>/dev/null | grep -E "gateway|interface" | sed 's/^/    /' || echo "    (route lookup failed)"
else
    ip route get "$FROM" 2>/dev/null | head -1 | sed 's/^/    /' || echo "    (route lookup failed)"
fi

echo ""
echo "  Route to target ($TO):"
if command -v route &>/dev/null; then
    route -n get "$TO" 2>/dev/null | grep -E "gateway|interface" | sed 's/^/    /' || echo "    (route lookup failed)"
else
    ip route get "$TO" 2>/dev/null | head -1 | sed 's/^/    /' || echo "    (route lookup failed)"
fi

echo ""

# ============================================================================
# Traceroute comparison
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  TRACEROUTE COMPARISON                                           │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

echo "  Path to source ($FROM):"
traceroute -m 10 -w 1 "$FROM" 2>/dev/null | head -12 | sed 's/^/    /' &
pid1=$!

echo ""
echo "  Path to target ($TO):"
traceroute -m 10 -w 1 "$TO" 2>/dev/null | head -12 | sed 's/^/    /' &
pid2=$!

wait $pid1 2>/dev/null || true
wait $pid2 2>/dev/null || true

echo ""

# ============================================================================
# Latency comparison
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  LATENCY COMPARISON (ping)                                       │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

echo "  Latency to source ($FROM):"
ping -c 5 "$FROM" 2>/dev/null | tail -1 | sed 's/^/    /' || echo "    (ping failed - host unreachable?)"

echo ""
echo "  Latency to target ($TO):"
ping -c 5 "$TO" 2>/dev/null | tail -1 | sed 's/^/    /' || echo "    (ping failed - host unreachable?)"

echo ""

# ============================================================================
# Subnet bridge detection
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  CROSS-SUBNET COMMUNICATION ANALYSIS                             │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

if [[ "$FROM_SUBNET" != "$TO_SUBNET" ]]; then
    echo "  For $FROM to reach $TO:"
    echo ""
    echo "    1. Packet leaves $FROM_SUBNET.0/24 network"
    echo "    2. Hits default gateway/router"
    echo "    3. Router makes forwarding decision"
    echo "    4. Packet enters $TO_SUBNET.0/24 network"
    echo "    5. Delivered to $TO"
    echo ""
    echo "  Each hop adds latency. Common issues:"
    echo ""
    echo "    - Consumer routers: Can add 1-5ms per hop"
    echo "    - NAT translation: Adds state lookup overhead"
    echo "    - Firewall rules: Deep inspection adds latency"
    echo "    - Wireless bridge: Can add 2-10ms+ jitter"
    echo ""

    # Check for common IoT subnet patterns
    if [[ "$FROM_SUBNET" == "192.168.86" ]]; then
        echo -e "  ${YELLOW}Note: 192.168.86.x is often a Google Nest/WiFi network${NC}"
        echo "    If Voice PE is on Google WiFi and HAOS is on main LAN,"
        echo "    traffic must traverse the Google WiFi router."
    fi

    if [[ "$TO_SUBNET" == "192.168.4" ]]; then
        echo -e "  ${BLUE}Note: 192.168.4.x appears to be main homelab network${NC}"
    fi
fi

echo ""

# ============================================================================
# Summary
# ============================================================================

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                         TOPOLOGY SUMMARY                         ║"
echo "╠══════════════════════════════════════════════════════════════════╣"

if [[ "$FROM_SUBNET" != "$TO_SUBNET" ]]; then
    echo "║  ⚠ CROSS-SUBNET COMMUNICATION DETECTED                         ║"
    echo "║                                                                ║"
    echo "║  Voice PE ($FROM) and HAOS ($TO) are on different networks."
    echo "║  Every request must traverse router(s).                        ║"
    echo "║                                                                ║"
    echo "║  POTENTIAL SOLUTIONS:                                          ║"
    echo "║    1. Move Voice PE to same subnet as HAOS                     ║"
    echo "║    2. Check router for latency/bottlenecks                     ║"
    echo "║    3. Ensure QoS prioritizes real-time traffic                 ║"
    echo "║    4. Consider dedicated VLAN for IoT with fast routing        ║"
else
    echo "║  ✓ Same subnet - no routing latency expected                   ║"
fi

echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
