#!/bin/bash
#
# voice-pe-timing.sh - Diagnose Voice PE TTS latency
#
# Checks the full Voice PE → HAOS → Voice PE flow:
#   1. TCP connectivity to Wyoming services
#   2. Wyoming protocol response time
#   3. Actual TTS synthesis timing (if possible)
#
# Usage:
#   ./voice-pe-timing.sh                    # Uses default homeassistant.maas
#   ./voice-pe-timing.sh --host <haos-ip>   # Custom HAOS host
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Defaults
HAOS_HOST="${HAOS_HOST:-homeassistant.maas}"
PIPER_PORT=10200
WHISPER_PORT=10300

while [[ $# -gt 0 ]]; do
    case $1 in
        --host|-h) HAOS_HOST="$2"; shift 2 ;;
        --help)
            echo "Usage: $0 [--host <haos-hostname>]"
            echo ""
            echo "Diagnoses Voice PE TTS latency by checking Wyoming services."
            echo ""
            echo "Default host: homeassistant.maas"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                   VOICE PE TTS TIMING ANALYSIS                   ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
printf "║  HAOS Host: %-52s ║\n" "$HAOS_HOST"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# Step 1: TCP Connectivity to Wyoming Services
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  STEP 1: TCP Connectivity to Wyoming Services                    │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

check_tcp() {
    local host="$1"
    local port="$2"
    local name="$3"

    local start=$(date +%s.%N)
    if nc -z -w5 "$host" "$port" 2>/dev/null; then
        local end=$(date +%s.%N)
        local ms=$(echo "($end - $start) * 1000" | bc 2>/dev/null || echo "?")
        printf "  %-20s %-15s ${GREEN}✓ reachable${NC} (%sms)\n" "$name" "$host:$port" "${ms%.*}"
        return 0
    else
        printf "  %-20s %-15s ${RED}✗ unreachable${NC}\n" "$name" "$host:$port"
        return 1
    fi
}

piper_ok=false
whisper_ok=false

check_tcp "$HAOS_HOST" "$PIPER_PORT" "Piper (TTS)" && piper_ok=true
check_tcp "$HAOS_HOST" "$WHISPER_PORT" "Whisper (STT)" && whisper_ok=true

echo ""

# ============================================================================
# Step 2: Wyoming Protocol Check
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  STEP 2: Wyoming Protocol Response                               │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

wyoming_describe() {
    local host="$1"
    local port="$2"
    local name="$3"

    echo "  Testing $name ($host:$port)..."

    # Wyoming protocol: send describe request, measure response time
    local start=$(date +%s.%N)
    local response=$(echo '{ "type": "describe" }' | timeout 5 nc -w2 "$host" "$port" 2>/dev/null | head -1)
    local end=$(date +%s.%N)

    if [[ -n "$response" ]]; then
        local ms=$(echo "($end - $start) * 1000" | bc 2>/dev/null || echo "?")
        printf "    Response time: ${GREEN}%sms${NC}\n" "${ms%.*}"

        # Parse response for service info
        if echo "$response" | grep -q "piper"; then
            echo "    Service: Wyoming Piper (TTS)"
        elif echo "$response" | grep -q "whisper"; then
            echo "    Service: Wyoming Whisper (STT)"
        fi
    else
        printf "    ${RED}No response - service may be down${NC}\n"
    fi
    echo ""
}

if [[ "$piper_ok" == "true" ]]; then
    wyoming_describe "$HAOS_HOST" "$PIPER_PORT" "Piper TTS"
fi

if [[ "$whisper_ok" == "true" ]]; then
    wyoming_describe "$HAOS_HOST" "$WHISPER_PORT" "Whisper STT"
fi

# ============================================================================
# Step 3: Network Path Analysis
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  STEP 3: Network Path to HAOS                                    │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

echo "  Ping latency (5 samples):"
ping -c 5 "$HAOS_HOST" 2>/dev/null | tail -1 | sed 's/^/    /' || echo "    (ping failed)"

echo ""

# Check if traceroute is available
if command -v traceroute &>/dev/null; then
    echo "  Route to HAOS:"
    traceroute -m 5 "$HAOS_HOST" 2>/dev/null | head -6 | sed 's/^/    /' || echo "    (traceroute failed)"
    echo ""
fi

# ============================================================================
# Step 4: Voice PE Device Check (if on network)
# ============================================================================

echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  STEP 4: Voice PE Device Status                                  │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo ""

# Common Voice PE hostnames/IPs
VOICE_PE_HOSTS=(
    "voice-pe.local"
    "voice-pe.homelab"
    "192.168.86.245"
)

found_voice_pe=false

for vpe_host in "${VOICE_PE_HOSTS[@]}"; do
    if ping -c 1 -W 1 "$vpe_host" &>/dev/null; then
        echo -e "  Voice PE found at: ${GREEN}$vpe_host${NC}"
        found_voice_pe=true

        # Check ESPHome web interface
        if curl -s -o /dev/null -w "%{http_code}" --max-time 2 "http://$vpe_host/" 2>/dev/null | grep -q "200"; then
            echo "    ESPHome web interface: ✓ accessible"
        fi
        break
    fi
done

if [[ "$found_voice_pe" == "false" ]]; then
    echo "  Voice PE device: not found on common addresses"
    echo "  (Check: voice-pe.local, voice-pe.homelab, or device's actual IP)"
fi

echo ""

# ============================================================================
# Summary
# ============================================================================

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                         ANALYSIS SUMMARY                         ║"
echo "╠══════════════════════════════════════════════════════════════════╣"

if [[ "$piper_ok" == "true" && "$whisper_ok" == "true" ]]; then
    echo "║  Wyoming Services: ✓ Both Piper and Whisper reachable          ║"
else
    echo "║  Wyoming Services: ⚠ One or more services unreachable          ║"
fi

echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  VOICE PE TTS LATENCY BREAKDOWN:                                 ║"
echo "║                                                                  ║"
echo "║    Voice PE → HAOS (network)     Check ping latency above        ║"
echo "║    HAOS → Whisper (STT)          Check Wyoming response time     ║"
echo "║    HAOS → Piper (TTS)            Check Wyoming response time     ║"
echo "║    HAOS → Voice PE (network)     Same as above (symmetric)       ║"
echo "║    Voice PE (audio playback)     Device-side, not measurable     ║"
echo "║                                                                  ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  NEXT STEPS:                                                     ║"
echo "║                                                                  ║"
echo "║  If Wyoming response slow → Check HAOS TTS addon resources       ║"
echo "║  If network latency high  → Check routing, DNS, firewall         ║"
echo "║  If all fast but TTS slow → Issue is in Voice PE or audio codec  ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
