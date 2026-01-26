#!/bin/bash
# Setup proper-raptor network: USB 2.5GbE with bridge (like Proxmox hosts)
#
# This converts proper-raptor from netplan to ifupdown with a bridge,
# matching the proven fun-bedbug configuration.
#
# After running: unplug built-in NIC cable, keep only USB 2.5GbE connected
#
set -e

HOST="ubuntu@192.168.4.189"
USB_NIC="enx00e04ca81110"  # USB 2.5GbE adapter
BUILTIN_NIC="enp1s0"       # Built-in 1GbE
MGMT_IP="192.168.4.189"    # Management IP (current)
STORAGE_IP="192.168.4.190" # Crucible storage IP (new, on bridge)
GATEWAY="192.168.4.1"
DNS="192.168.4.53"

echo "=== Setting up proper-raptor network ==="
echo "USB NIC: $USB_NIC"
echo "Management IP: $MGMT_IP (will move to bridge)"
echo "Storage IP: $STORAGE_IP (Crucible traffic)"
echo ""

# Check SSH access
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" "echo 'SSH OK'" 2>/dev/null; then
    echo "ERROR: Cannot SSH to $HOST"
    exit 1
fi

echo "=== Step 1: Install bridge-utils and ifupdown ==="
ssh "$HOST" "sudo apt-get update && sudo apt-get install -y bridge-utils ifupdown"

echo "=== Step 2: Disable cloud-init network config ==="
ssh "$HOST" "sudo mkdir -p /etc/cloud/cloud.cfg.d && echo 'network: {config: disabled}' | sudo tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg"

echo "=== Step 3: Backup current netplan ==="
ssh "$HOST" "sudo cp /etc/netplan/50-cloud-init.yaml /etc/netplan/50-cloud-init.yaml.backup.\$(date +%Y%m%d)"

echo "=== Step 4: Create /etc/network/interfaces ==="
ssh "$HOST" "sudo tee /etc/network/interfaces" << 'EOF'
# Network configuration for proper-raptor
# Matches Proxmox host pattern (fun-bedbug)
# USB 2.5GbE adapter with bridge for reliable boot

auto lo
iface lo inet loopback

# Built-in 1GbE - unused, no cable connected
iface enp1s0 inet manual

# USB 2.5GbE adapter - bridge member
auto enx00e04ca81110
iface enx00e04ca81110 inet manual

# Bridge on USB adapter - gets the IP
auto br0
iface br0 inet static
    address 192.168.4.189/24
    gateway 192.168.4.1
    bridge-ports enx00e04ca81110
    bridge-stp off
    bridge-fd 0
    dns-nameservers 192.168.4.53
    dns-search maas

# Secondary IP for Crucible storage traffic (optional)
# Uncomment if you want separate IP for storage
#auto br0:0
#iface br0:0 inet static
#    address 192.168.4.190/24
EOF

echo "=== Step 5: Disable netplan and enable ifupdown ==="
ssh "$HOST" "sudo systemctl mask systemd-networkd-wait-online.service"
ssh "$HOST" "sudo rm -f /etc/netplan/50-cloud-init.yaml"

echo "=== Step 6: Fix /etc/hosts ==="
ssh "$HOST" "sudo tee /etc/hosts" << 'EOF'
127.0.0.1 localhost
192.168.4.189 proper-raptor.maas proper-raptor

# IPv6
::1 localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
EOF

echo ""
echo "=== Configuration complete ==="
echo ""
echo "NEXT STEPS:"
echo "1. Unplug the cable from built-in NIC (enp1s0)"
echo "2. Ensure USB 2.5GbE adapter cable is connected to switch"
echo "3. Reboot: ssh $HOST 'sudo reboot'"
echo "4. Wait ~60 seconds, then verify: ssh $HOST 'ip addr show br0'"
echo ""
echo "If boot hangs, connect cable to built-in NIC temporarily to recover."
