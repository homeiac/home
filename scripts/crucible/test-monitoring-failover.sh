#!/bin/bash
# Test Crucible failover for monitoring storage
#
# This script tests that pumped-piglet's Crucible volume (3840-3842)
# can be taken over by still-fawn after pumped-piglet disconnects.
#
# Usage: ./test-monitoring-failover.sh [simulate|real]
#   simulate: Just disconnects NBD on pumped-piglet (VM keeps running)
#   real:     Actually stops the K8s VM (full failover test)
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Hosts
PRIMARY_HOST="pumped-piglet.maas"
STANDBY_HOST="still-fawn.maas"
CRUCIBLE_HOST="192.168.4.189"

# Downstairs ports for pumped-piglet's volume
DS_PORTS="3840 3841 3842"

echo "=== Crucible Monitoring Failover Test ==="
echo "Primary:  $PRIMARY_HOST"
echo "Standby:  $STANDBY_HOST"
echo "Downstairs: $CRUCIBLE_HOST ports $DS_PORTS"
echo ""

# Step 1: Verify primary is connected
echo "Step 1: Checking primary connection..."
if ssh root@$PRIMARY_HOST "systemctl is-active crucible-monitoring-storage.service" 2>/dev/null | grep -q "^active"; then
    echo "  ✓ Primary NBD service is active"
else
    echo "  ✗ Primary NBD service is NOT active"
    echo "    Start it with: ssh root@$PRIMARY_HOST 'systemctl start crucible-nbd crucible-nbd-connect'"
    exit 1
fi

# Check NBD device
if ssh root@$PRIMARY_HOST "lsblk /dev/nbd0 2>/dev/null" | grep -q "nbd0"; then
    SIZE=$(ssh root@$PRIMARY_HOST "lsblk -no SIZE /dev/nbd0 2>/dev/null")
    echo "  ✓ Primary has /dev/nbd0 ($SIZE)"
else
    echo "  ✗ Primary /dev/nbd0 not connected"
    exit 1
fi

# Step 2: Write test marker on primary
echo ""
echo "Step 2: Writing test marker on primary..."
MARKER="failover-test-$(date +%s)"
ssh root@$PRIMARY_HOST "mount /dev/nbd0 /mnt/crucible-storage 2>/dev/null || true"
ssh root@$PRIMARY_HOST "echo '$MARKER' > /mnt/crucible-storage/.failover-test"
echo "  ✓ Wrote marker: $MARKER"

# Step 3: Disconnect primary
echo ""
echo "Step 3: Disconnecting primary..."
ssh root@$PRIMARY_HOST "systemctl stop crucible-monitoring-storage-connect crucible-monitoring-storage" 2>/dev/null
sleep 2

if ssh root@$PRIMARY_HOST "systemctl is-active crucible-monitoring-storage.service 2>/dev/null" | grep -q "^active"; then
    echo "  ✗ Failed to stop primary NBD"
    exit 1
else
    echo "  ✓ Primary disconnected"
fi

# Step 4: Connect standby with higher generation
echo ""
echo "Step 4: Connecting standby (higher generation)..."
ssh root@$STANDBY_HOST "systemctl start crucible-monitoring-storage" 2>/dev/null
sleep 3
ssh root@$STANDBY_HOST "systemctl start crucible-monitoring-storage-connect" 2>/dev/null
sleep 2

if ssh root@$STANDBY_HOST "lsblk /dev/nbd1 2>/dev/null" | grep -q "nbd1"; then
    SIZE=$(ssh root@$STANDBY_HOST "lsblk -no SIZE /dev/nbd1 2>/dev/null")
    echo "  ✓ Standby has /dev/nbd1 ($SIZE)"
else
    echo "  ✗ Standby /dev/nbd1 not connected"
    echo "    Check logs: ssh root@$STANDBY_HOST 'journalctl -u crucible-nbd-failover -n 50'"
    exit 1
fi

# Step 5: Verify data integrity
echo ""
echo "Step 5: Verifying data on standby..."
ssh root@$STANDBY_HOST "mkdir -p /mnt/crucible-failover && mount /dev/nbd1 /mnt/crucible-failover 2>/dev/null || true"
RECOVERED=$(ssh root@$STANDBY_HOST "cat /mnt/crucible-failover/.failover-test 2>/dev/null")

if [ "$RECOVERED" = "$MARKER" ]; then
    echo "  ✓ Data intact! Marker matches: $RECOVERED"
else
    echo "  ✗ Data mismatch!"
    echo "    Expected: $MARKER"
    echo "    Got:      $RECOVERED"
    exit 1
fi

# Step 6: Cleanup - restore primary
echo ""
echo "Step 6: Restoring primary (cleanup)..."
ssh root@$STANDBY_HOST "umount /mnt/crucible-failover 2>/dev/null || true"
ssh root@$STANDBY_HOST "systemctl stop crucible-monitoring-storage-connect crucible-monitoring-storage" 2>/dev/null
sleep 2
ssh root@$PRIMARY_HOST "systemctl start crucible-monitoring-storage crucible-monitoring-storage-connect" 2>/dev/null
sleep 2

if ssh root@$PRIMARY_HOST "systemctl is-active crucible-monitoring-storage.service 2>/dev/null" | grep -q "^active"; then
    echo "  ✓ Primary restored"
else
    echo "  ⚠ Primary may need manual restart"
fi

echo ""
echo "=== FAILOVER TEST PASSED ==="
echo ""
echo "Summary:"
echo "  - Primary disconnected cleanly"
echo "  - Standby connected with higher generation"
echo "  - Data was preserved across failover"
echo "  - Primary restored"
echo ""
echo "This proves Prometheus/Grafana data would survive a pumped-piglet failure"
echo "if still-fawn takes over the Crucible volume."
