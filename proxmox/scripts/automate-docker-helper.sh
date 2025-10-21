#!/bin/bash
# Automated Docker LXC creation using Proxmox VE Helper Scripts
# This script properly handles whiptail automation with correct TERM and environment setup

set -e

# Configuration
CONTAINER_ID="104"
HOSTNAME="docker-webtop"
DISK_SIZE="50"
CPU_CORES="4"
RAM_SIZE="8192"
IP_ADDRESS="192.168.4.104"
GATEWAY="192.168.4.1"
BRIDGE="vmbr0"

echo "Setting up environment for whiptail automation..."

# Set up proper terminal environment for whiptail
export TERM=ansi
export NEWT_COLORS='window=,red border=white,red textbox=white,red button=black,white'
export DEBIAN_FRONTEND=noninteractive

# Create expect script on the fly
cat > /tmp/docker-lxc-automation.exp << 'EOF'
#!/usr/bin/expect -f

set timeout 300
log_user 1

# Set environment
set env(TERM) "ansi"
set env(NEWT_COLORS) "window=,red border=white,red textbox=white,red button=black,white"

# Configuration variables
set container_id "104"
set hostname "docker-webtop"
set disk_size "50"
set cpu_cores "4"
set ram_size "8192"
set ip_address "192.168.4.104"
set gateway "192.168.4.1"

# Start the script
spawn bash -c "curl -fsSL https://github.com/community-scripts/ProxmoxVE/raw/main/ct/docker.sh | bash"

expect {
    -re "SSH.*continue.*\\?" {
        send "y\r"
        exp_continue
    }
    -re "Choose Type.*" {
        # Navigate to Advanced option (second option)
        send " \r"
        exp_continue
    }
    -re "CONTAINER TYPE.*" {
        # Select Advanced
        send " \r"
        exp_continue
    }
    -re "Set Container ID.*" {
        send "$container_id\r"
        exp_continue
    }
    -re "Set Hostname.*" {
        send "$hostname\r"
        exp_continue
    }
    -re "Set Disk Size.*" {
        send "$disk_size\r"
        exp_continue
    }
    -re "Set CPU Core Count.*" {
        send "$cpu_cores\r"
        exp_continue
    }
    -re "Set RAM.*" {
        send "$ram_size\r"
        exp_continue
    }
    -re "Set a Bridge.*" {
        send "vmbr0\r"
        exp_continue
    }
    -re "Set a Static IPv4.*" {
        send "$ip_address/24\r"
        exp_continue
    }
    -re "Set a Gateway.*" {
        send "$gateway\r"
        exp_continue
    }
    -re "Disable IPv6.*" {
        send "n\r"
        exp_continue
    }
    -re "Set Interface MTU.*" {
        send "\r"
        exp_continue
    }
    -re "Set a DNS Search.*" {
        send "\r"
        exp_continue
    }
    -re "Set a DNS Server.*" {
        send "\r"
        exp_continue
    }
    -re "Set a MAC Address.*" {
        send "\r"
        exp_continue
    }
    -re "Set a VLAN.*" {
        send "\r"
        exp_continue
    }
    -re "Enable Root SSH.*" {
        send "y\r"
        exp_continue
    }
    -re "Enable Verbose.*" {
        send "y\r"
        exp_continue
    }
    -re "Create CT.*" {
        send "y\r"
        exp_continue
    }
    -re "Completed Successfully.*" {
        puts "\nDocker LXC container created successfully!"
        exit 0
    }
    timeout {
        puts "\nScript timed out"
        exit 1
    }
    eof {
        puts "\nScript completed"
        exit 0
    }
}

expect eof
EOF

# Make the expect script executable
chmod +x /tmp/docker-lxc-automation.exp

echo "Running automated Docker LXC creation..."
/tmp/docker-lxc-automation.exp

echo "Verifying container creation..."
if pct status 104 >/dev/null 2>&1; then
    echo "✓ Container 104 created successfully"
    pct start 104
    sleep 5
    echo "✓ Container started"
    
    # Test Docker installation
    if pct exec 104 -- docker --version >/dev/null 2>&1; then
        echo "✓ Docker is installed and working"
        echo ""
        echo "Container Details:"
        echo "  ID: 104"
        echo "  Hostname: docker-webtop"
        echo "  IP: 192.168.4.104"
        echo "  SSH: ssh root@192.168.4.104"
        echo ""
        echo "Ready for Webtop deployment!"
    else
        echo "⚠ Docker installation needs verification"
    fi
else
    echo "✗ Container creation failed"
    exit 1
fi