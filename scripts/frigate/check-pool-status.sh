#!/bin/bash
# Check current status of 3TB pool on both hosts

set -euo pipefail

echo "=== Checking 3TB pool status on both hosts ==="
echo

echo "--- still-fawn status ---"
ssh root@still-fawn.maas "zpool list | grep -E '(NAME|3TB)' || echo 'No 3TB pool active'"
echo

echo "--- pumped-piglet status ---"
ssh root@pumped-piglet.maas "zpool list | grep -E '(NAME|3TB)' || echo 'No 3TB pool active'"
echo

echo "--- pumped-piglet available imports ---"
ssh root@pumped-piglet.maas "zpool import 2>/dev/null | grep -A 5 '3TB' || echo 'Pool not available for import'"
echo

echo "=== Status check complete ==="
