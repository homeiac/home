#!/bin/bash
# Read a file from HAOS VM via Proxmox qm guest exec
# Usage: read-from-ha.sh <ha_path>
#
# Example:
#   ./read-from-ha.sh /mnt/data/supervisor/homeassistant/automations.yaml
set -e

PROXMOX_HOST="${PROXMOX_HOST:-root@chief-horse.maas}"
VMID="${VMID:-116}"

HA_PATH="${1:?Usage: $0 <ha_path>}"

ssh "$PROXMOX_HOST" "qm guest exec $VMID -- cat '$HA_PATH'" 2>/dev/null | jq -r '.["out-data"] // "ERROR: File not found or empty"'
