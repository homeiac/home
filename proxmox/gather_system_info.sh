#!/bin/bash
# Export Proxmox cluster node details as CSV with base board info

echo "Node,IPs,Board,CPU,Mem,GPU" > proxmox_nodes.csv

ssh_opts="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

nodes=$(pvesh get /nodes --output-format=json | jq -r '.[].node')
if [ -z "$nodes" ]; then
    echo "No nodes found or invalid JSON output."
    exit 1
fi

for node in $nodes; do
    if [ "$node" = "pve" ]; then
        host="$node"
    else
        host="$node.maas"
    fi

    # Retrieve base board info from /sys/class/dmi/id/
    board_vendor=$(ssh $ssh_opts root@$host "cat /sys/class/dmi/id/board_vendor 2>/dev/null" | tr -d '\n')
    board_name=$(ssh $ssh_opts root@$host "cat /sys/class/dmi/id/board_name 2>/dev/null" | tr -d '\n')
    if echo "$board_vendor" | grep -qi "ASUSTeK"; then
        vendor_short="ASUS"
    else
        vendor_short=$(echo "$board_vendor" | awk '{print $1}')
    fi
    board="$vendor_short $board_name"

    # CPU info: shorten the output to "Brand Model @Freq"
    cpu_raw=$(ssh $ssh_opts root@$host "lscpu | grep 'Model name:' | cut -d':' -f2")
    cpu_clean=$(echo "$cpu_raw" | sed -e 's/Intel(R)/Intel/g' -e 's/Core(TM)//g' -e 's/CPU//g' \
                                      -e 's/GHz//g' -e 's/To Be Filled By O.E.M.//g' | sed 's/  */ /g' | sed 's/^[ \t]*//')
    cpu_model=$(echo "$cpu_clean" | sed 's/Intel *\(N100\)Intel/Intel \1/' | awk '{print $1, $2, "@"$NF}')

    # Memory in GB (two decimals)
    total_mem=$(ssh $ssh_opts root@$host "grep MemTotal /proc/meminfo | awk '{printf \"%.2f\", \$2/1048576}'")

    # Retrieve only IPv4 addresses, join with commas
    ips=$(ssh $ssh_opts root@$host "hostname -I | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}'" | tr '\n' ',' | sed 's/,$//')

    # GPU info: remove PCI prefix and join multiple lines with "; "
    gpu_info=$(ssh $ssh_opts root@$host "lspci | grep -i -E 'vga|3d'" | awk -F': ' '{print $2}' | tr '\n' '; ' | sed 's/; *$//')

    echo "$node,\"$ips\",\"$board\",\"$cpu_model\",$total_mem,\"$gpu_info\"" >> proxmox_nodes.csv
done

echo "Data collection complete. Output saved to proxmox_nodes.csv"
