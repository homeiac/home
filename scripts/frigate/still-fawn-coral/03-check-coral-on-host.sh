#!/bin/bash
set -euo pipefail

echo "Checking for Coral USB on still-fawn host..."
ssh root@still-fawn.maas "lsusb | grep -E '1a6e:089a|18d1:9302'" || {
    echo "ERROR: Coral not detected. Please verify USB connection."
    exit 1
}
echo "Coral detected on host."
