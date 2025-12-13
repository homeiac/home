#!/bin/bash
set -euo pipefail

echo "Removing USB passthrough from pumped-piglet VM 105..."
ssh root@pumped-piglet.maas "qm set 105 --delete usb0 --delete usb1"
echo "Done. USB passthrough removed."
