#!/usr/bin/env bash
# apply-exporters.sh  [--group GROUP]  [inventory-file]
#   --group GROUP   Run only on that section (e.g. "proxmox")
#   no --group      Run on *every* host in every section.
# inventory-file    Defaults to ./inventory.txt
#
# Idempotent: re-applying causes no state drift.

set -euo pipefail
GROUP_FILTER=""
[[ ${1:-} == --group ]] && { GROUP_FILTER=$2; shift 2; }

INV=${1:-inventory.txt}
SCRIPT=exporter-desired.sh
[[ -f $SCRIPT ]] || { echo "Missing $SCRIPT"; exit 1; }

current_group=""
while IFS= read -r line || [[ -n $line ]]; do
  line_trim=$(echo "$line" | sed 's/[[:space:]]*$//')
  [[ -z $line_trim || $line_trim == \#* ]] && continue

  if [[ $line_trim =~ ^\[(.+)\]$ ]]; then
    current_group="${BASH_REMATCH[1]}"
    continue
  fi

  # honour --group filter
  [[ -n $GROUP_FILTER && $current_group != "$GROUP_FILTER" ]] && continue

  host=$(echo "$line_trim" | cut -d' ' -f1)
  echo "=== [$current_group]  $host ==="
  scp -q "$SCRIPT" "root@$host:/tmp/"
  ssh -tt "root@$host" "bash /tmp/$(basename "$SCRIPT")"
done <"$INV"

