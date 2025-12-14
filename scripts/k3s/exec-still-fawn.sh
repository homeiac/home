#!/bin/bash
# Execute command on k3s-vm-still-fawn via qm guest exec
# SSH DOES NOT WORK to K3s VMs - use this instead
#
# Usage: ./exec-still-fawn.sh "uptime"
#        ./exec-still-fawn.sh "top -bn1 | head -20"

VMID=108
HOST="still-fawn.maas"
CMD="${1:-uptime}"

ssh root@$HOST "qm guest exec $VMID -- bash -c '$CMD'"
