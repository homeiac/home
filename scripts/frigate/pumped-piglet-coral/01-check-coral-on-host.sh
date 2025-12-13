#!/bin/bash
# 01-check-coral-on-host.sh - Verify Coral USB on pumped-piglet host
#
# Run this AFTER physically connecting Coral USB to pumped-piglet

set -e

HOST="pumped-piglet.maas"

echo "========================================="
echo "Step 1: Check Coral USB on Host"
echo "========================================="
echo ""

echo "Checking for Coral USB device on $HOST..."
ssh root@$HOST "for d in /sys/bus/usb/devices/*/; do
  v=\$(cat \$d/idVendor 2>/dev/null)
  p=\$(cat \$d/idProduct 2>/dev/null)
  s=\$(cat \$d/speed 2>/dev/null)
  if [ \"\$v\" = '18d1' ] || [ \"\$v\" = '1a6e' ]; then
    echo \"Found Coral: \$v:\$p at \$d\"
    echo \"USB Speed: \$s Mbps\"
    if [ \"\$s\" = '5000' ]; then
      echo \"USB 3.0: YES\"
    else
      echo \"WARNING: Not USB 3.0! Move to a blue USB port.\"
    fi
  fi
done"

echo ""
echo "========================================="
echo "Done. Coral should show 1a6e:089a (bootloader) or 18d1:9302 (initialized)"
echo "========================================="
