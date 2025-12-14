#!/bin/bash
# Diagnose CPU consumption on K3s VM
# Usage: ./diagnose-cpu.sh still-fawn|pumped-piglet|chief-horse

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE="${1:-still-fawn}"

# Validate node
case "$NODE" in
    still-fawn|pumped-piglet|chief-horse)
        ;;
    *)
        echo "Usage: $0 [still-fawn|pumped-piglet|chief-horse]"
        exit 1
        ;;
esac

echo "=== CPU diagnostics for k3s-vm-$NODE ==="
echo ""

echo "--- Uptime & Load ---"
"$SCRIPT_DIR/exec.sh" "$NODE" "uptime"

echo ""
echo "--- Top 10 CPU consumers ---"
"$SCRIPT_DIR/exec.sh" "$NODE" "ps aux --sort=-%cpu | head -11"

echo ""
echo "--- Memory ---"
"$SCRIPT_DIR/exec.sh" "$NODE" "free -h"

echo ""
echo "--- Disk I/O (if iotop available) ---"
"$SCRIPT_DIR/exec.sh" "$NODE" "which iotop && iotop -bon1 | head -15 || echo iotop not installed"
