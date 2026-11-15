#!/usr/bin/env bash
# Check NTP sync status across all Proxmox nodes
# Usage: ./check-ntp-sync.sh          # report
#        ./check-ntp-sync.sh --fix    # force chronyc makestep on nodes with issues
#
# Needs bash 4+ (assoc arrays) - /usr/bin/env picks up Homebrew bash on macOS.
#
# Alerts if:
# - Stratum is 0 (not syncing)
# - Time offset > 5 seconds
# - Nodes differ by > 30 seconds
# - Node clock differs from this workstation by > 5 seconds
#   (catches the whole cluster being wrong together, e.g. after a power cut
#   when MAAS NTP at 192.168.4.53 was down while hosts booted)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INVENTORY="$SCRIPT_DIR/../../proxmox/inventory.txt"

# Node IPs - update if inventory changes
# (rapid-civet 192.168.4.11 is intentionally offline - not checked)
declare -A NODES=(
    ["pve"]="192.168.4.122"
    ["chief-horse"]="192.168.4.19"
    ["still-fawn"]="192.168.4.17"
    ["pumped-piglet"]="192.168.4.175"
    ["fun-bedbug"]="192.168.4.172"
)

FIX=0
[[ "${1:-}" == "--fix" ]] && FIX=1

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=== Proxmox Cluster NTP Sync Check ==="
echo ""

declare -A TIMESTAMPS
ISSUES=0

for node in "${!NODES[@]}"; do
    ip="${NODES[$node]}"
    echo -n "Checking $node ($ip)... "

    # Get time and chrony status
    result=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@$ip "
        echo \"TIME:\$(date +%s)\"
        echo \"DATE:\$(date)\"
        chronyc tracking 2>/dev/null | grep -E '^(Stratum|System time)' || echo 'CHRONY:not running'
    " 2>/dev/null) || {
        echo -e "${RED}UNREACHABLE${NC}"
        ISSUES=$((ISSUES+1))
        continue
    }

    timestamp=$(echo "$result" | grep "^TIME:" | cut -d: -f2)
    date_str=$(echo "$result" | grep "^DATE:" | cut -d: -f2-)
    stratum=$(echo "$result" | grep "^Stratum" | awk '{print $3}')
    offset=$(echo "$result" | grep "^System time" | awk '{print $4}')

    TIMESTAMPS[$node]=$timestamp

    # Check for issues
    node_issues=""

    local_skew=$((timestamp - $(date +%s)))
    if (( ${local_skew#-} > 5 )); then
        node_issues+=" ${RED}Clock ${local_skew}s off vs workstation${NC}"
        ISSUES=$((ISSUES+1))
    fi

    if [[ "$stratum" == "0" ]]; then
        node_issues+=" ${RED}Stratum 0 (NOT SYNCING)${NC}"
        ISSUES=$((ISSUES+1))
    fi

    if [[ -n "$offset" ]]; then
        # Remove leading minus if present for comparison
        offset_abs=${offset#-}
        if (( $(echo "$offset_abs > 5" | bc -l 2>/dev/null || echo 0) )); then
            node_issues+=" ${YELLOW}Offset: ${offset}s${NC}"
            ISSUES=$((ISSUES+1))
        fi
    fi

    if [[ -z "$node_issues" ]]; then
        echo -e "${GREEN}OK${NC} - $date_str (Stratum: $stratum, offset: ${offset:-?}s)"
    else
        echo -e "$node_issues - $date_str"
        if (( FIX )); then
            echo "    -> chronyc makestep on $node"
            ssh -o ConnectTimeout=5 root@$ip "chronyc -a makestep >/dev/null && sleep 2 && date" | sed 's/^/       /'
        fi
    fi
done

echo ""

# Check time differences between nodes
echo "=== Time Drift Between Nodes ==="
nodes_array=(${!TIMESTAMPS[@]})
for ((i=0; i<${#nodes_array[@]}; i++)); do
    for ((j=i+1; j<${#nodes_array[@]}; j++)); do
        node1="${nodes_array[$i]}"
        node2="${nodes_array[$j]}"
        ts1="${TIMESTAMPS[$node1]}"
        ts2="${TIMESTAMPS[$node2]}"

        if [[ -n "$ts1" && -n "$ts2" ]]; then
            diff=$((ts1 - ts2))
            diff_abs=${diff#-}

            if (( diff_abs > 30 )); then
                echo -e "${RED}$node1 <-> $node2: ${diff}s drift - CRITICAL${NC}"
                ISSUES=$((ISSUES+1))
            elif (( diff_abs > 5 )); then
                echo -e "${YELLOW}$node1 <-> $node2: ${diff}s drift - WARNING${NC}"
            else
                echo -e "${GREEN}$node1 <-> $node2: ${diff}s - OK${NC}"
            fi
        fi
    done
done

echo ""

if (( ISSUES > 0 )); then
    echo -e "${RED}Found $ISSUES issue(s)${NC}"
    echo ""
    echo "To fix NTP on a node:"
    echo "  ssh root@<IP> \"grep -q 'pool.ntp.org' /etc/chrony/chrony.conf || echo 'pool pool.ntp.org iburst' >> /etc/chrony/chrony.conf\""
    echo "  ssh root@<IP> \"systemctl restart chronyd && chronyc makestep\""
    exit 1
else
    echo -e "${GREEN}All nodes synced${NC}"
    exit 0
fi
