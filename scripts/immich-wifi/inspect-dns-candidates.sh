#!/usr/bin/env bash
# Read-only checks of online Proxmox hosts listed in the canonical inventory.
# Find an independent, already-connected resolver location; never scan networks.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
awk '
  /^\[proxmox\]/{active=1;next}
  /^\[/{active=0}
  active && $3 ~ /^(pumped-piglet|still-fawn|fun-bedbug)$/ {print $1,$3}
' "$root/proxmox/inventory.txt" | while read -r address name; do
  echo "Resolver candidate: $name"
  ssh -n -o BatchMode=yes -o ConnectTimeout=5 "root@$address" 'ip -br -4 addr; ip -4 route' || true
done
