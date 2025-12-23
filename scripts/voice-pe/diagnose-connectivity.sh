#!/bin/bash
# Voice PE Connectivity Diagnosis
# Quickly identifies why Voice PE isn't connecting to Home Assistant
#
# Usage: ./diagnose-connectivity.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

# Load HA token
if [[ -f "$ENV_FILE" ]]; then
    HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
fi

# Config
HA_URL="${HA_URL:-http://192.168.1.122:8123}"
VOICE_PE_HOSTNAME="home-assistant-voice-09f5a3"
EXPECTED_IP="192.168.86.10"  # Static IP configured in ESPHome

echo "╔════════════════════════════════════════════════════════════╗"
echo "║          Voice PE Connectivity Diagnosis                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│                    CONNECTION FLOW                          │"
echo "├─────────────────────────────────────────────────────────────┤"
echo "│                                                             │"
echo "│  BOOT:                                                      │"
echo "│  1. Voice PE boots, starts API server on :6053              │"
echo "│  2. HA ESPHome integration connects TO Voice PE (HA→PE)     │"
echo "│                                                             │"
echo "│  VOICE INTERACTION:                                         │"
echo "│  3. Wake word → Audio streamed to HA via API :6053          │"
echo "│  4. HA: STT → Intent → TTS → Returns audio URL              │"
echo "│  5. Voice PE fetches audio FROM HA :8123 (PE→HA via socat)  │"
echo "│                                                             │"
echo "│  TWO PATHS MUST WORK:                                       │"
echo "│  ┌────────────┐        :6053         ┌────────────┐         │"
echo "│  │  Voice PE  │◀════════════════════ │     HA     │ PATH A  │"
echo "│  │  (86.10)   │                      │  (4.240)   │ ESPHome │"
echo "│  │            │ ════════════════════▶│            │ PATH B  │"
echo "│  └────────────┘   :8123 via socat    └────────────┘ TTS     │"
echo "│                                                             │"
echo "│  PATH A: HA VM (86.22) → vmbr2 → Flint3 → Voice PE :6053    │"
echo "│  PATH B: Voice PE → Google WiFi → ISP → pve socat → HA      │"
echo "│                                                             │"
echo "└─────────────────────────────────────────────────────────────┘"
echo ""

# Track issues
ISSUES=()

#─────────────────────────────────────────────────────────────────────
# 1. USB Connection Check
#─────────────────────────────────────────────────────────────────────
echo "┌─ 1. USB Connection ─────────────────────────────────────────┐"
USB_DEVICE=$(ls /dev/cu.usbmodem* 2>/dev/null | head -1)
if [[ -n "$USB_DEVICE" ]]; then
    echo "│ ✓ USB device found: $USB_DEVICE"
else
    echo "│ ✗ No USB device found"
    ISSUES+=("USB: Device not connected or not recognized")
fi
echo "└────────────────────────────────────────────────────────────┘"
echo ""

#─────────────────────────────────────────────────────────────────────
# 2. Network Discovery (mDNS)
#─────────────────────────────────────────────────────────────────────
echo "┌─ 2. Network Discovery (mDNS) ───────────────────────────────┐"
MDNS_IP=$(dns-sd -G v4 "${VOICE_PE_HOSTNAME}.local" 2>/dev/null | grep -oE '192\.[0-9]+\.[0-9]+\.[0-9]+' | head -1 &
    sleep 2
    kill %1 2>/dev/null
) || true

# Fallback to ping
if [[ -z "$MDNS_IP" ]]; then
    MDNS_IP=$(ping -c 1 -t 2 "${VOICE_PE_HOSTNAME}.local" 2>/dev/null | grep -oE '192\.[0-9]+\.[0-9]+\.[0-9]+' | head -1) || true
fi

if [[ -n "$MDNS_IP" ]]; then
    echo "│ ✓ mDNS resolved: ${VOICE_PE_HOSTNAME}.local → $MDNS_IP"
    CURRENT_IP="$MDNS_IP"
    if [[ "$MDNS_IP" != "$EXPECTED_IP" ]]; then
        echo "│ ⚠ IP differs from expected ($EXPECTED_IP)"
        ISSUES+=("IP_MISMATCH: Device at $MDNS_IP, expected $EXPECTED_IP")
    fi
else
    echo "│ ✗ mDNS resolution failed"
    ISSUES+=("MDNS: Cannot resolve ${VOICE_PE_HOSTNAME}.local")
fi
echo "└────────────────────────────────────────────────────────────┘"
echo ""

#─────────────────────────────────────────────────────────────────────
# 3. Direct IP Connectivity
#─────────────────────────────────────────────────────────────────────
echo "┌─ 3. Network Connectivity ───────────────────────────────────┐"
TEST_IP="${CURRENT_IP:-$EXPECTED_IP}"
if ping -c 1 -t 2 "$TEST_IP" &>/dev/null; then
    echo "│ ✓ Ping to $TEST_IP successful"
else
    echo "│ ✗ Ping to $TEST_IP failed"
    ISSUES+=("NETWORK: Cannot ping $TEST_IP")
fi

# Check API port (6053)
if nc -z -w 2 "$TEST_IP" 6053 2>/dev/null; then
    echo "│ ✓ API port 6053 open on $TEST_IP"
else
    echo "│ ✗ API port 6053 not reachable on $TEST_IP"
    ISSUES+=("API_PORT: Port 6053 not open on $TEST_IP")
fi
echo "└────────────────────────────────────────────────────────────┘"
echo ""

#─────────────────────────────────────────────────────────────────────
# 4. PATH B: socat Proxy (Voice PE → HA for TTS audio)
#─────────────────────────────────────────────────────────────────────
echo "┌─ 4. PATH B: socat Proxy (TTS audio fetch) ──────────────────┐"
# Check if socat proxy is reachable (this is what Voice PE uses)
if curl -s --max-time 3 -o /dev/null -w "%{http_code}" "http://192.168.1.122:8123/" 2>/dev/null | grep -q "200\|401"; then
    echo "│ ✓ socat proxy reachable at 192.168.1.122:8123"
else
    echo "│ ✗ socat proxy NOT reachable at 192.168.1.122:8123"
    ISSUES+=("SOCAT_PROXY: Cannot reach pve socat proxy - TTS will fail")
fi

# Check if we can reach HA through the proxy (use token if available to avoid auth warnings)
if [[ -n "$HA_TOKEN" ]]; then
    HA_STATUS=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $HA_TOKEN" "http://192.168.1.122:8123/api/" 2>/dev/null || echo "000")
else
    HA_STATUS=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" "http://192.168.1.122:8123/api/" 2>/dev/null || echo "000")
fi
if [[ "$HA_STATUS" == "401" || "$HA_STATUS" == "200" || "$HA_STATUS" == "201" ]]; then
    echo "│ ✓ HA API accessible via proxy (HTTP $HA_STATUS)"
else
    echo "│ ✗ HA API not accessible via proxy (HTTP $HA_STATUS)"
    ISSUES+=("HA_VIA_PROXY: HA not reachable through socat proxy")
fi
echo "└────────────────────────────────────────────────────────────┘"
echo ""

#─────────────────────────────────────────────────────────────────────
# 5. PATH A: HA → Voice PE (ESPHome API)
#─────────────────────────────────────────────────────────────────────
echo "┌─ 5. PATH A: HA ESPHome Integration ─────────────────────────┐"
if [[ -z "$HA_TOKEN" ]]; then
    echo "│ ⚠ HA_TOKEN not set, skipping HA checks"
else
    # Check if ESPHome integration exists
    ESPHOME_ENTITIES=$(curl -s --max-time 10 \
        -H "Authorization: Bearer $HA_TOKEN" \
        "$HA_URL/api/states" 2>/dev/null | \
        jq -r '.[] | select(.entity_id | contains("voice_assistant") or contains("09f5a3")) | .entity_id' 2>/dev/null | head -5)

    if [[ -n "$ESPHOME_ENTITIES" ]]; then
        echo "│ ✓ Found Voice PE entities in HA:"
        echo "$ESPHOME_ENTITIES" | while read -r ent; do
            echo "│   - $ent"
        done
    else
        echo "│ ✗ No Voice PE entities found in HA"
        ISSUES+=("HA_ENTITIES: Voice PE not registered in Home Assistant")
    fi

    # Check ESPHome integration config entries
    CONFIG_ENTRIES=$(curl -s --max-time 10 \
        -H "Authorization: Bearer $HA_TOKEN" \
        "$HA_URL/api/config/config_entries/entry" 2>/dev/null | \
        jq -r '.[] | select(.domain == "esphome") | "\(.title) - \(.state)"' 2>/dev/null)

    if [[ -n "$CONFIG_ENTRIES" ]]; then
        echo "│"
        echo "│ ESPHome config entries:"
        echo "$CONFIG_ENTRIES" | while read -r entry; do
            if [[ "$entry" == *"loaded"* ]]; then
                echo "│   ✓ $entry"
            else
                echo "│   ✗ $entry"
            fi
        done
    fi
fi
echo "└────────────────────────────────────────────────────────────┘"
echo ""

#─────────────────────────────────────────────────────────────────────
# 6. Serial Boot Log Quick Check (if USB connected)
#─────────────────────────────────────────────────────────────────────
if [[ -n "$USB_DEVICE" ]]; then
    echo "┌─ 6. Recent Serial Output (5s sample) ───────────────────────┐"
    # Quick 5-second capture without reset
    timeout 5 cat "$USB_DEVICE" 2>/dev/null | head -20 | while read -r line; do
        # Strip ANSI codes and show relevant lines
        clean=$(echo "$line" | sed 's/\x1b\[[0-9;]*m//g')
        if [[ "$clean" =~ (error|warn|fail|connect|api|client|wifi) ]]; then
            echo "│ $clean"
        fi
    done || true
    echo "└────────────────────────────────────────────────────────────┘"
    echo ""
fi

#─────────────────────────────────────────────────────────────────────
# Summary
#─────────────────────────────────────────────────────────────────────
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                      DIAGNOSIS SUMMARY                     ║"
echo "╚════════════════════════════════════════════════════════════╝"

if [[ ${#ISSUES[@]} -eq 0 ]]; then
    echo "✓ No obvious issues detected"
    echo ""
    echo "If Voice PE still not working, check:"
    echo "  1. HA logs: scripts/haos/get-logs.sh core | grep -i esphome"
    echo "  2. Full boot log: scripts/voice-pe/serial-monitor-timeout.sh"
    echo "  3. ESPHome dashboard in HA for device status"
else
    echo "Found ${#ISSUES[@]} issue(s):"
    echo ""
    for issue in "${ISSUES[@]}"; do
        CODE="${issue%%:*}"
        DESC="${issue#*: }"
        echo "  ✗ [$CODE] $DESC"

        # Remediation hints
        case "$CODE" in
            USB)
                echo "    → Check USB cable, try different port"
                echo "    → Run: ls /dev/cu.usb*"
                ;;
            MDNS)
                echo "    → Device may not be on network yet"
                echo "    → Check serial logs: scripts/voice-pe/serial-monitor-timeout.sh"
                ;;
            IP_MISMATCH)
                echo "    → DHCP assigned new IP - HA has old IP cached"
                echo "    → FIX: Set static IP in ESPHome config"
                echo "    → Or: Remove/re-add ESPHome integration in HA"
                ;;
            NETWORK)
                echo "    → Device not responding on network"
                echo "    → Check WiFi credentials in ESPHome config"
                ;;
            API_PORT)
                echo "    → ESPHome API not running or blocked"
                echo "    → Check serial logs for errors"
                ;;
            HA_ENTITIES)
                echo "    → Re-add device in ESPHome integration"
                echo "    → Check HA → Settings → Devices → ESPHome"
                ;;
            SOCAT_PROXY)
                echo "    → PATH B broken: Voice PE can't fetch TTS audio"
                echo "    → Check socat service: ssh root@pve.maas 'systemctl status ha-proxy'"
                echo "    → Restart if needed: ssh root@pve.maas 'systemctl restart ha-proxy'"
                ;;
            HA_VIA_PROXY)
                echo "    → socat running but HA not reachable behind it"
                echo "    → Check HA is running: ssh root@chief-horse.maas 'qm status 116'"
                echo "    → Check HA IP: should be 192.168.4.240"
                ;;
        esac
        echo ""
    done
fi

echo "─────────────────────────────────────────────────────────────"
echo "Runbook: docs/runbooks/voice-pe-connectivity.md"
echo "─────────────────────────────────────────────────────────────"
