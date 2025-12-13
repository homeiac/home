#!/bin/bash
set -euo pipefail

VMID=108
echo "Adding USB passthrough to still-fawn VM ${VMID}..."
ssh root@still-fawn.maas "qm set ${VMID} --usb0 host=1a6e:089a,usb3=1 --usb1 host=18d1:9302,usb3=1"
echo "USB passthrough configured. VM reboot required."
