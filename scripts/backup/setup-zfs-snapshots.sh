#!/bin/bash
# Setup ZFS automatic snapshots on Proxmox hosts
# Uses sanoid for snapshot management with configurable retention
#
# Targets:
#   - pumped-piglet.maas: local-20TB-zfs pool
#   - fun-bedbug.maas: local-3TB-backup pool
#
# Retention: 24 hourly, 7 daily, 4 weekly, 3 monthly

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
HOSTS=("pumped-piglet.maas" "fun-bedbug.maas")
SANOID_CONF="/etc/sanoid/sanoid.conf"

echo "========================================="
echo "ZFS Automatic Snapshot Setup"
echo "========================================="
echo ""

# Sanoid configuration template
generate_sanoid_config() {
    local pool=$1
    cat << EOF
[$pool]
    use_template = production
    recursive = yes

[template_production]
    hourly = 24
    daily = 7
    weekly = 4
    monthly = 3
    autosnap = yes
    autoprune = yes
EOF
}

setup_host() {
    local host=$1
    echo "=== Setting up $host ==="

    # Check SSH connectivity
    if ! ssh -o ConnectTimeout=5 -o BatchMode=yes root@$host "echo 'SSH OK'" 2>/dev/null; then
        echo "  ERROR: Cannot SSH to $host"
        echo "  Run: ssh-copy-id root@$host"
        return 1
    fi

    # Get ZFS pools
    echo "  Checking ZFS pools..."
    local pools=$(ssh root@$host "zpool list -H -o name" 2>/dev/null)
    echo "  Found pools: $pools"

    # Install sanoid if not present
    echo "  Checking sanoid installation..."
    if ! ssh root@$host "command -v sanoid" &>/dev/null; then
        echo "  Installing sanoid..."
        ssh root@$host "apt-get update -qq && apt-get install -y -qq sanoid" || {
            echo "  ERROR: Failed to install sanoid on $host"
            return 1
        }
    fi
    echo "  sanoid installed: $(ssh root@$host 'sanoid --version' 2>/dev/null || echo 'unknown')"

    # Create sanoid config directory
    ssh root@$host "mkdir -p /etc/sanoid"

    # Generate and deploy config for each pool
    echo "  Configuring sanoid..."
    local config=""
    for pool in $pools; do
        # Skip rpool (system pool) - only backup data pools
        if [[ "$pool" == "rpool" ]]; then
            continue
        fi
        echo "    Adding pool: $pool"
        config+="[$pool]
    use_template = production
    recursive = yes

"
    done

    # Add template
    config+="[template_production]
    hourly = 24
    daily = 7
    weekly = 4
    monthly = 3
    autosnap = yes
    autoprune = yes
"

    # Deploy config
    echo "$config" | ssh root@$host "cat > $SANOID_CONF"
    echo "  Config written to $SANOID_CONF"

    # Enable and start sanoid timer
    echo "  Enabling sanoid timer..."
    ssh root@$host "systemctl enable sanoid.timer && systemctl start sanoid.timer"

    # Run initial snapshot
    echo "  Creating initial snapshots..."
    ssh root@$host "sanoid --take-snapshots --verbose" 2>&1 | head -20

    # Show current snapshots
    echo "  Current snapshots:"
    ssh root@$host "zfs list -t snapshot -o name,creation -s creation | tail -10"

    echo "  ✓ $host configured successfully"
    echo ""
}

# Main
echo "This script will configure ZFS automatic snapshots on:"
for host in "${HOSTS[@]}"; do
    echo "  - $host"
done
echo ""
echo "Retention policy: 24 hourly, 7 daily, 4 weekly, 3 monthly"
echo ""

read -p "Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

for host in "${HOSTS[@]}"; do
    setup_host "$host" || echo "WARNING: Failed to setup $host"
done

echo "========================================="
echo "Setup Complete"
echo "========================================="
echo ""
echo "Verify with:"
echo "  ssh root@pumped-piglet.maas 'zfs list -t snapshot'"
echo "  ssh root@fun-bedbug.maas 'zfs list -t snapshot'"
echo ""
echo "Sanoid runs hourly via systemd timer."
echo "Check status: ssh root@HOST 'systemctl status sanoid.timer'"
