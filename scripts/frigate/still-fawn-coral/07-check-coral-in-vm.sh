#!/bin/bash
set -euo pipefail

# Uses QEMU guest agent since direct SSH to K3s VMs is broken
VMID=108

echo "Checking for Coral USB inside still-fawn VM ${VMID}..."
OUTPUT=$(ssh root@still-fawn.maas "qm guest exec ${VMID} -- lsusb" 2>&1)

if echo "$OUTPUT" | grep -qE "18d1:9302|1a6e:089a"; then
    echo "Coral detected inside VM."
    echo "$OUTPUT" | grep -E "18d1:9302|1a6e:089a" || true
else
    echo "ERROR: Coral not visible in VM. Check USB passthrough config."
    echo "$OUTPUT"
    exit 1
fi
