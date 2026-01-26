#!/bin/bash
# Attach Crucible volumes to all Proxmox hosts
set -e

CRUCIBLE_IP="192.168.4.189"

# Copy binary once
echo "=== Copying crucible-nbd-server binary ==="
scp ubuntu@${CRUCIBLE_IP}:/home/ubuntu/crucible-nbd-server /tmp/crucible-nbd-server

# Host:ports mapping
declare -A HOSTS=(
    ["pve"]="3820 3821 3822"
    ["still-fawn"]="3830 3831 3832"
    ["pumped-piglet"]="3840 3841 3842"
    ["chief-horse"]="3850 3851 3852"
)

for host in "${!HOSTS[@]}"; do
    ports=(${HOSTS[$host]})
    echo ""
    echo "=== $host (ports ${ports[*]}) ==="

    # pve doesn't need .maas suffix
    if [ "$host" == "pve" ]; then
        ssh_host="pve"
    else
        ssh_host="${host}.maas"
    fi

    # Copy binary (force overwrite)
    ssh root@${ssh_host} "rm -f /usr/local/bin/crucible-nbd-server"
    scp /tmp/crucible-nbd-server root@${ssh_host}:/usr/local/bin/

    # Copy setup script
    scp scripts/crucible/setup-nbd-client.sh root@${ssh_host}:/tmp/

    # Run it
    ssh root@${ssh_host} "chmod +x /tmp/setup-nbd-client.sh && /tmp/setup-nbd-client.sh ${CRUCIBLE_IP} ${ports[0]} ${ports[1]} ${ports[2]}"
done

echo ""
echo "=== Done ==="
