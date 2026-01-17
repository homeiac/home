#!/bin/bash
# Deploy K3s cloud-init snippets to Proxmox hosts
#
# Usage: ./deploy-snippets.sh [HOST...]
#
# If no hosts specified, deploys to all known Proxmox hosts.
# Snippets are copied to /var/lib/vz/snippets/ on each host.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNIPPETS_DIR="$SCRIPT_DIR/snippets"

# Default hosts if none specified
DEFAULT_HOSTS=(
    "fun-bedbug.maas"
    "pumped-piglet.maas"
    "still-fawn.maas"
    "chief-horse.maas"
)

if [[ $# -gt 0 ]]; then
    HOSTS=("$@")
else
    HOSTS=("${DEFAULT_HOSTS[@]}")
fi

echo "=== Deploying K3s Cloud-Init Snippets ==="
echo "Source: $SNIPPETS_DIR"
echo "Hosts: ${HOSTS[*]}"
echo ""

for host in "${HOSTS[@]}"; do
    echo "Deploying to $host..."

    # Ensure snippets directory exists
    ssh -o StrictHostKeyChecking=no "root@$host" "mkdir -p /var/lib/vz/snippets" 2>/dev/null || {
        echo "  WARNING: Could not connect to $host, skipping"
        continue
    }

    # Copy all snippets
    for snippet in "$SNIPPETS_DIR"/*.yaml; do
        if [[ -f "$snippet" ]]; then
            filename=$(basename "$snippet")
            scp -o StrictHostKeyChecking=no "$snippet" "root@$host:/var/lib/vz/snippets/$filename"
            echo "  Copied $filename"
        fi
    done

    echo "  Done"
done

echo ""
echo "Snippets deployed successfully"
echo ""
echo "To use in a VM:"
echo "  qm set <VMID> --cicustom 'user=local:snippets/k3s-vm-prep.yaml'"
