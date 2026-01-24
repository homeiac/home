#!/bin/bash
# Disable Proxmox enterprise repos and enable no-subscription repos
# Run on a fresh Proxmox node to avoid subscription nag warnings
#
# Usage: ./disable-enterprise-repos.sh [hostname]
#        ./disable-enterprise-repos.sh                  # runs locally
#        ./disable-enterprise-repos.sh still-fawn.maas  # runs via SSH

set -e

run_cmd() {
    if [[ -n "$REMOTE_HOST" ]]; then
        ssh "root@$REMOTE_HOST" "$1"
    else
        eval "$1"
    fi
}

REMOTE_HOST="${1:-}"

echo "Disabling enterprise repos${REMOTE_HOST:+ on $REMOTE_HOST}..."

# Disable PVE enterprise repo
run_cmd "sed -i 's/^deb/#deb/' /etc/apt/sources.list.d/pve-enterprise.list 2>/dev/null || true"

# Disable Ceph enterprise repo if present
run_cmd "sed -i 's/^deb/#deb/' /etc/apt/sources.list.d/ceph.list 2>/dev/null || true"

# Add no-subscription repo if not present
run_cmd "
if ! grep -q 'pve-no-subscription' /etc/apt/sources.list.d/*.list 2>/dev/null; then
    echo 'deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription' > /etc/apt/sources.list.d/pve-no-subscription.list
    echo 'Added pve-no-subscription repo'
else
    echo 'pve-no-subscription repo already configured'
fi
"

echo "Done. Repo status:"
run_cmd "grep -h '^deb\|^#deb' /etc/apt/sources.list.d/pve-*.list /etc/apt/sources.list.d/ceph.list 2>/dev/null || true"
