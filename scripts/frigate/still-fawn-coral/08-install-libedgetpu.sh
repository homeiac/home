#!/bin/bash
set -euo pipefail

# Uses QEMU guest agent since direct SSH to K3s VMs is broken
VMID=108

echo "Checking libedgetpu installation in VM ${VMID}..."
OUTPUT=$(ssh root@still-fawn.maas "qm guest exec ${VMID} -- dpkg -l libedgetpu1-std" 2>&1)

if echo "$OUTPUT" | grep -q "libedgetpu"; then
    echo "libedgetpu already installed."
    exit 0
fi

echo "ERROR: libedgetpu not installed. Manual installation required via Proxmox console."
echo "Run inside VM: sudo apt install libedgetpu1-std"
exit 1
