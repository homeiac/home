#!/bin/bash
# Run command inside HAOS VM via qm guest exec
# Usage: ./guest-exec.sh "command to run"
#
# HAOS VM: 116 on chief-horse.maas
# NO SSH available - this is the only way to run commands inside

set -e

VMID=116
PROXMOX_HOST="chief-horse.maas"
CMD="${1:-echo 'No command provided'}"

echo "Running on HAOS VM $VMID via $PROXMOX_HOST..."
ssh root@$PROXMOX_HOST "qm guest exec $VMID -- $CMD"
