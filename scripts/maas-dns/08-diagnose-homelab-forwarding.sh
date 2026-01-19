#!/bin/bash
# MAAS DNS Forwarding Diagnostic for .homelab
# Tests whether MAAS forwards .homelab queries to OPNsense or queries root servers
set -e

OPNSENSE_IP="192.168.4.1"
MAAS_IP="192.168.4.53"
MAAS_HOST="pve.maas"
MAAS_VMID="102"
TEST_HOSTNAME="${1:-reolink-vdb.homelab}"

# Helper to run commands in MAAS VM and extract just the output
maas_exec() {
    local result
    result=$(ssh root@${MAAS_HOST} "qm guest exec ${MAAS_VMID} -- bash -c '$1'" 2>/dev/null)
    # Extract out-data from JSON, decode if needed
    echo "$result" | jq -r '.["out-data"] // empty' 2>/dev/null || echo "$result"
}

echo "=== MAAS DNS Forwarding Diagnostic ==="
echo "Test hostname: $TEST_HOSTNAME"
echo ""

# [1] Test OPNsense direct
echo "[1] OPNsense direct query ($OPNSENSE_IP):"
OPNSENSE_RESULT=$(dig +short $TEST_HOSTNAME @$OPNSENSE_IP 2>/dev/null || echo "FAILED")
if [[ -n "$OPNSENSE_RESULT" && "$OPNSENSE_RESULT" != "FAILED" ]]; then
    echo "    $TEST_HOSTNAME -> $OPNSENSE_RESULT  [OK]"
else
    echo "    $TEST_HOSTNAME -> FAILED  [FAIL]"
fi
echo ""

# [2] Test MAAS direct
echo "[2] MAAS direct query ($MAAS_IP):"
MAAS_RESULT=$(dig +short $TEST_HOSTNAME @$MAAS_IP 2>/dev/null || echo "")
if [[ -n "$MAAS_RESULT" ]]; then
    echo "    $TEST_HOSTNAME -> $MAAS_RESULT  [OK]"
else
    echo "    $TEST_HOSTNAME -> NXDOMAIN  [FAIL]"
fi
echo ""

# [3] Check MAAS bind config
echo "[3] MAAS bind configuration:"

echo "    Forwarders:"
maas_exec "grep -A5 'forwarders' /var/snap/maas/current/bind/named.conf.options.inside.maas 2>/dev/null | head -8" | sed 's/^/        /'

echo "    Forward mode (forward only vs forward first):"
FORWARD_MODE=$(maas_exec "grep -E '^[[:space:]]*forward[[:space:]]' /var/snap/maas/current/bind/named.conf.options.inside.maas 2>/dev/null")
if [[ -z "$FORWARD_MODE" ]]; then
    echo "        NOT SET (default: forward first - falls back to recursion)"
else
    echo "        $FORWARD_MODE"
fi

echo "    DNSSEC setting:"
DNSSEC=$(maas_exec "grep dnssec-validation /var/snap/maas/current/bind/named.conf.options.inside.maas 2>/dev/null")
echo "        $DNSSEC"

echo "    Forward zone for .homelab:"
FORWARD_ZONE=$(maas_exec "grep -A3 'zone.*homelab' /var/snap/maas/current/bind/named.conf* 2>/dev/null")
if [[ -z "$FORWARD_ZONE" ]]; then
    echo "        NOT FOUND  [FAIL]"
else
    echo "$FORWARD_ZONE" | sed 's/^/        /'
fi

echo "    named.conf includes:"
INCLUDES=$(maas_exec "grep include /var/snap/maas/current/bind/named.conf 2>/dev/null")
echo "$INCLUDES" | sed 's/^/        /'

echo "    named.conf.local.maas exists:"
LOCAL_EXISTS=$(maas_exec "ls -la /var/snap/maas/current/bind/named.conf.local.maas 2>/dev/null" || echo "NOT FOUND")
echo "        $LOCAL_EXISTS"
echo ""

# [4] Check if named.conf.local.maas is included
echo "[4] Configuration loading check:"
INCLUDES_LOCAL=$(maas_exec "grep -i 'named.conf.local' /var/snap/maas/current/bind/named.conf 2>/dev/null")
if [[ -z "$INCLUDES_LOCAL" ]]; then
    echo "    [FAIL] named.conf does NOT include named.conf.local.maas!"
    echo "    This is why the forward zone is being ignored."
else
    echo "    [OK] named.conf includes: $INCLUDES_LOCAL"
fi
echo ""

# [5] Check full OPNsense response (not just +short)
echo "[5] Full OPNsense response:"
dig $TEST_HOSTNAME @$OPNSENSE_IP 2>/dev/null | grep -E "^;|status:|ANSWER|$TEST_HOSTNAME" | head -10 | sed 's/^/        /'
echo ""

# [6] Test with dig +trace to see where query goes
echo "[6] Query trace analysis:"
echo "    Running dig +trace (first 20 lines)..."
dig +trace $TEST_HOSTNAME @$MAAS_IP 2>/dev/null | head -20 | sed 's/^/        /'
echo ""

# [7] Diagnosis
echo "=== DIAGNOSIS ==="
if [[ -n "$MAAS_RESULT" ]]; then
    echo "[OK] MAAS is forwarding .homelab queries correctly"
else
    echo "[FAIL] MAAS is NOT forwarding .homelab queries"
    echo ""
    if [[ -z "$INCLUDES_LOCAL" ]]; then
        echo "ROOT CAUSE: named.conf.local.maas is NOT included in named.conf"
        echo "            The forward zone exists but bind doesn't load it!"
        echo ""
        echo "FIX: Add include statement to named.conf:"
        echo '     include "/var/snap/maas/current/bind/named.conf.local.maas";'
    elif [[ -z "$FORWARD_ZONE" ]]; then
        echo "ROOT CAUSE: No forward zone defined for .homelab"
        echo ""
        echo "FIX: Add forward zone to named.conf.local.maas"
        echo "     See: scripts/maas-dns/02-add-forward-zone.sh"
    else
        echo "Forward zone exists and config is included."
        echo "Possible causes:"
        echo "  1. Bind needs restart: snap restart maas.bind9"
        echo "  2. Cache has stale NXDOMAIN"
        echo "  3. Check bind logs for errors"
    fi
fi
