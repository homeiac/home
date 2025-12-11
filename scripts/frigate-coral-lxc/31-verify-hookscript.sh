#!/bin/bash
# Frigate Coral LXC - Verify Hookscript
# GitHub Issue: #168
# Checks that the hookscript executed successfully

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== Frigate Coral LXC - Verify Hookscript ==="
echo "Target host: $PVE_HOST_NAME ($PVE_HOST)"
echo ""

if [[ -z "$VMID" ]]; then
    echo "❌ ERROR: VMID not set in config.env"
    exit 1
fi

LOG_TAG="coral-hook-$VMID"

echo "Container VMID: $VMID"
echo "Log tag: $LOG_TAG"
echo ""

echo "1. Checking syslog for hookscript entries..."
LOGS=$(ssh root@"$PVE_HOST" "journalctl -t $LOG_TAG --no-pager -n 30 2>/dev/null || grep '$LOG_TAG' /var/log/syslog 2>/dev/null | tail -30 || echo 'NO_LOGS'")

if [[ "$LOGS" == "NO_LOGS" ]] || [[ -z "$LOGS" ]]; then
    echo "   ⚠️  No hookscript logs found"
    echo "   This may mean:"
    echo "   - Hookscript hasn't run yet"
    echo "   - Hookscript is not attached"
    echo "   - Container was started before hookscript was added"
else
    echo "   ✅ Hookscript logs found:"
    echo ""
    echo "$LOGS" | sed 's/^/   /'
fi

echo ""
echo "2. Checking for USB reset evidence..."
if echo "$LOGS" | grep -q "Resetting USB device"; then
    echo "   ✅ USB reset was performed"
else
    echo "   ⚠️  No USB reset logged (may have been skipped)"
fi

echo ""
echo "3. Checking for config update..."
if echo "$LOGS" | grep -q "LXC config updated"; then
    echo "   ✅ LXC config was updated"
else
    echo "   ⚠️  No config update logged"
fi

echo ""
echo "=== Hookscript Verification Complete ==="
echo ""
echo "NEXT: Run 32-verify-frigate-api.sh to check Frigate"
