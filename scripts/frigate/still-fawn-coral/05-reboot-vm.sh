#!/bin/bash
set -euo pipefail

VMID=108
echo "Rebooting still-fawn VM ${VMID}..."
ssh root@still-fawn.maas "qm reboot ${VMID}"
echo "Reboot initiated."
