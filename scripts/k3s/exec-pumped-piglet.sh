#!/bin/bash
# Execute command on k3s-vm-pumped-piglet via qm guest exec
# SSH DOES NOT WORK to K3s VMs - use this instead
#
# Usage: ./exec-pumped-piglet.sh "uptime"
#        ./exec-pumped-piglet.sh "nvidia-smi"

VMID=105
HOST="pumped-piglet.maas"
CMD="${1:-uptime}"

ssh root@$HOST "qm guest exec $VMID -- bash -c '$CMD'"
