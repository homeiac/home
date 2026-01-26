#!/bin/bash
# Attach Crucible volumes to all Proxmox hosts
#
# Usage: ./attach-volumes-to-proxmox.sh [CRUCIBLE_IP]
#
# Deploys crucible-nbd-server and setup script to each Proxmox host,
# configuring NBD connections to Crucible downstairs processes.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRUCIBLE_IP="${1:-192.168.4.189}"
SETUP_SCRIPT="${SCRIPT_DIR}/setup-nbd-client.sh"

# Host:ports mapping - each host gets dedicated downstairs ports
declare -A HOSTS=(
    ["pve"]="3820 3821 3822"
    ["still-fawn"]="3830 3831 3832"
    ["pumped-piglet"]="3840 3841 3842"
    ["chief-horse"]="3850 3851 3852"
    ["fun-bedbug"]="3860 3861 3862"
)

# Resolve SSH hostname (pve is special - no .maas suffix)
resolve_ssh_host() {
    local host="$1"
    if [[ "$host" == "pve" ]]; then
        echo "pve"
    else
        echo "${host}.maas"
    fi
}

# Deploy to a single host
deploy_to_host() {
    local host="$1"
    local ports="$2"
    local ssh_host
    ssh_host=$(resolve_ssh_host "$host")

    read -ra port_array <<< "$ports"
    echo ""
    echo "=== $host (ports ${port_array[*]}) ==="

    # Copy binary (force overwrite)
    ssh "root@${ssh_host}" "rm -f /usr/local/bin/crucible-nbd-server"
    scp /tmp/crucible-nbd-server "root@${ssh_host}:/usr/local/bin/"

    # Copy and run setup script
    scp "$SETUP_SCRIPT" "root@${ssh_host}:/tmp/"
    ssh "root@${ssh_host}" "chmod +x /tmp/setup-nbd-client.sh && /tmp/setup-nbd-client.sh ${CRUCIBLE_IP} ${port_array[0]} ${port_array[1]} ${port_array[2]}"
}

# Validate setup script exists
if [[ ! -f "$SETUP_SCRIPT" ]]; then
    echo "ERROR: Setup script not found: $SETUP_SCRIPT" >&2
    exit 1
fi

# Fetch binary from Crucible host
echo "=== Fetching crucible-nbd-server from ${CRUCIBLE_IP} ==="
scp "ubuntu@${CRUCIBLE_IP}:/home/ubuntu/crucible-nbd-server" /tmp/crucible-nbd-server

# Deploy to all hosts
for host in "${!HOSTS[@]}"; do
    deploy_to_host "$host" "${HOSTS[$host]}"
done

echo ""
echo "=== Done ==="
