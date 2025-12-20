#!/bin/bash
# Generate Crossplane YAML for an existing LXC container
# Usage: ./import-lxc.sh <VMID> [hostname]
#
# Example:
#   ./import-lxc.sh 113 > frigate-nvr.yaml
set -e

VMID="$1"
HOSTNAME="${2:-}"

if [[ -z "$VMID" ]]; then
    echo "Usage: $0 <VMID> [hostname]" >&2
    echo "Example: $0 113 fun-bedbug" >&2
    exit 1
fi

# Find which node has this LXC
find_node() {
    local vmid="$1"
    for node in pumped-piglet still-fawn fun-bedbug chief-horse; do
        if ssh root@${node}.maas "pct status $vmid" 2>/dev/null | grep -q "status:"; then
            echo "$node"
            return 0
        fi
    done
    echo "ERROR: LXC $vmid not found on any node" >&2
    return 1
}

if [[ -z "$HOSTNAME" ]]; then
    HOSTNAME=$(find_node "$VMID")
fi

echo "# Fetching LXC $VMID config from $HOSTNAME..." >&2

# Get LXC config
CONFIG=$(ssh root@${HOSTNAME}.maas "pct config $VMID")

# Parse values
NAME=$(echo "$CONFIG" | grep "^hostname:" | cut -d' ' -f2)
CORES=$(echo "$CONFIG" | grep "^cores:" | cut -d' ' -f2)
MEMORY=$(echo "$CONFIG" | grep "^memory:" | cut -d' ' -f2)
DESCRIPTION=$(echo "$CONFIG" | grep "^description:" | cut -d' ' -f2-)
OSTYPE=$(echo "$CONFIG" | grep "^ostype:" | cut -d' ' -f2)

# Parse rootfs (format: storage:subvol-VMID-disk-0,size=32G)
ROOTFS=$(echo "$CONFIG" | grep "^rootfs:")
STORAGE=$(echo "$ROOTFS" | sed 's/.*: //' | cut -d':' -f1)
SIZE=$(echo "$ROOTFS" | grep -o 'size=[0-9]*' | cut -d'=' -f2)

# Parse network (format: name=eth0,bridge=vmbr0,...)
NET0=$(echo "$CONFIG" | grep "^net0:")
BRIDGE=$(echo "$NET0" | grep -o 'bridge=[^,]*' | cut -d'=' -f2)

# Check for USB passthrough
USB_DEVICES=""
if echo "$CONFIG" | grep -q "^usb"; then
    USB_DEVICES=$(echo "$CONFIG" | grep "^usb" | while read line; do
        host=$(echo "$line" | grep -o 'host=[^,]*' | cut -d'=' -f2)
        echo "      - host: \"$host\""
    done)
fi

# Check for nesting
NESTING=$(echo "$CONFIG" | grep -o 'nesting=[01]' | cut -d'=' -f2)

# Generate YAML
cat <<EOF
# Adopted LXC container - imported from existing $HOSTNAME LXC $VMID
# Generated: $(date -Iseconds)
# Original config: ssh root@${HOSTNAME}.maas "pct config $VMID"
---
apiVersion: virtualenvironment.proxmox.crossplane.io/v1alpha1
kind: EnvironmentContainer
metadata:
  name: ${NAME:-lxc-$VMID}
  annotations:
    # CRITICAL: This tells Crossplane to adopt existing container instead of creating new
    crossplane.io/external-name: "$VMID"
  labels:
    imported-from: $HOSTNAME
    managed-by: crossplane
spec:
  forProvider:
    nodeName: $HOSTNAME
    vmid: $VMID
    hostname: ${NAME:-lxc-$VMID}
    description: "${DESCRIPTION:-Imported from $HOSTNAME}"
    osType: ${OSTYPE:-debian}

    cores: ${CORES:-2}
    memory: ${MEMORY:-2048}

    rootfs:
      storage: ${STORAGE:-local-zfs}
      size: ${SIZE:-32}

    network:
      - name: eth0
        bridge: ${BRIDGE:-vmbr0}

    features:
      nesting: $([[ "$NESTING" == "1" ]] && echo "true" || echo "false")
EOF

# Add USB devices if present
if [[ -n "$USB_DEVICES" ]]; then
    cat <<EOF

    # USB passthrough devices
    usb:
$USB_DEVICES
EOF
fi

cat <<EOF

  # CRITICAL: Orphan policy prevents deletion of existing container
  # If this CR is deleted from Git, the container stays in Proxmox
  deletionPolicy: Orphan

  providerConfigRef:
    name: default
EOF

echo "" >&2
echo "Generated! Review and add to gitops/clusters/homelab/instances/" >&2
