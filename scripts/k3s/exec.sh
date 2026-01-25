#!/bin/bash
# Execute command on any K3s VM via qm guest exec
# Usage: ./exec.sh <node> <command>
#
# Nodes: still-fawn, pumped-piglet, chief-horse
# SSH DOES NOT WORK - this uses qm guest exec

set -e

NODE="${1:-}"
CMD="${2:-uptime}"

if [[ -z "$NODE" ]]; then
    echo "Usage: $0 <node> <command>"
    echo "Nodes: still-fawn, pumped-piglet, chief-horse, pve, fun-bedbug"
    exit 1
fi

case "$NODE" in
    still-fawn)
        VMID=108
        HOST="still-fawn.maas"
        ;;
    pumped-piglet)
        VMID=105
        HOST="pumped-piglet.maas"
        ;;
    chief-horse)
        VMID=109
        HOST="chief-horse.maas"
        ;;
    pve)
        VMID=107
        HOST="pve.maas"
        ;;
    fun-bedbug)
        VMID=114
        HOST="fun-bedbug.maas"
        ;;
    *)
        echo "Unknown node: $NODE"
        echo "Valid nodes: still-fawn, pumped-piglet, chief-horse, pve, fun-bedbug"
        exit 1
        ;;
esac

ssh root@$HOST "qm guest exec $VMID -- bash -c '$CMD'"
