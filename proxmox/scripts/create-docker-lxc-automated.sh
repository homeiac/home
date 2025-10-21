#!/bin/bash
# Automated Docker LXC Creation Script for Proxmox VE
# This script automates the creation of a Docker LXC container using environment variables
# instead of interactive prompts from the Proxmox VE Helper Scripts

set -e

# Configuration variables
CONTAINER_ID="${CT_ID:-104}"
CONTAINER_HOSTNAME="${CT_HOSTNAME:-docker-webtop}"
DISK_SIZE="${DISK_SIZE:-50}"
RAM_SIZE="${RAM_SIZE:-8192}"
CPU_CORES="${CPU_CORES:-4}"
BRIDGE="${BRIDGE:-vmbr0}"
IP_ADDRESS="${IP_ADDRESS:-192.168.4.104/24}"
GATEWAY="${GATEWAY:-192.168.4.1}"
STORAGE="${STORAGE:-local-zfs}"
NODE="${NODE:-still-fawn}"
ROOT_PASSWORD="${ROOT_PASSWORD:-}"  # Leave empty for auto-login
ENABLE_SSH="${ENABLE_SSH:-yes}"

echo "Creating Docker LXC Container with following settings:"
echo "  Container ID: $CONTAINER_ID"
echo "  Hostname: $CONTAINER_HOSTNAME"
echo "  Disk: ${DISK_SIZE}GB"
echo "  RAM: ${RAM_SIZE}MB"
echo "  CPU Cores: $CPU_CORES"
echo "  Network: $IP_ADDRESS via $BRIDGE"
echo "  Gateway: $GATEWAY"
echo "  Storage: $STORAGE"

# Function to create the container using native Proxmox commands
create_docker_lxc() {
    # Download the latest Debian 12 template if not exists
    TEMPLATE="debian-12-standard_12.7-1_amd64.tar.zst"
    
    # Check if template exists
    if ! pveam list local | grep -q "$TEMPLATE"; then
        echo "Downloading Debian 12 template..."
        pveam download local $TEMPLATE
    fi
    
    # Create the container with Docker-ready configuration
    echo "Creating LXC container..."
    pct create $CONTAINER_ID local:vztmpl/$TEMPLATE \
        --hostname $CONTAINER_HOSTNAME \
        --cores $CPU_CORES \
        --memory $RAM_SIZE \
        --swap 512 \
        --storage $STORAGE \
        --rootfs ${STORAGE}:${DISK_SIZE} \
        --net0 name=eth0,bridge=$BRIDGE,ip=$IP_ADDRESS,gw=$GATEWAY \
        --unprivileged 1 \
        --features nesting=1,keyctl=1 \
        --ostype debian \
        --description "Docker LXC Container (Automated Creation)" \
        --onboot 1
    
    # Set root password if provided
    if [ -n "$ROOT_PASSWORD" ]; then
        echo "Setting root password..."
        echo "root:$ROOT_PASSWORD" | pct exec $CONTAINER_ID -- chpasswd
    fi
    
    # Start the container
    echo "Starting container..."
    pct start $CONTAINER_ID
    
    # Wait for container to be ready
    sleep 5
    
    # Install Docker inside the container
    echo "Installing Docker inside the container..."
    pct exec $CONTAINER_ID -- bash -c "
        # Update system
        apt-get update && apt-get upgrade -y
        
        # Install prerequisites
        apt-get install -y ca-certificates curl gnupg lsb-release
        
        # Add Docker's official GPG key
        mkdir -p /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        
        # Set up the repository
        echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \$(lsb_release -cs) stable\" | tee /etc/apt/sources.list.d/docker.list > /dev/null
        
        # Install Docker Engine
        apt-get update
        apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        
        # Enable Docker service
        systemctl enable docker
        systemctl start docker
        
        # Install Docker Compose standalone (for compatibility)
        curl -L \"https://github.com/docker/compose/releases/latest/download/docker-compose-\$(uname -s)-\$(uname -m)\" -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
    "
    
    # Enable SSH if requested
    if [ "$ENABLE_SSH" = "yes" ]; then
        echo "Enabling SSH access..."
        pct exec $CONTAINER_ID -- bash -c "
            apt-get install -y openssh-server
            sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
            systemctl enable ssh
            systemctl restart ssh
        "
    fi
    
    echo "Docker LXC container created successfully!"
    echo "Container ID: $CONTAINER_ID"
    echo "IP Address: ${IP_ADDRESS%/*}"
    echo ""
    echo "You can access the container with:"
    echo "  SSH: ssh root@${IP_ADDRESS%/*}"
    echo "  Console: pct console $CONTAINER_ID"
    echo ""
    echo "Docker and Docker Compose are installed and ready to use."
}

# Main execution
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: $0"
    echo ""
    echo "Environment variables:"
    echo "  CT_ID           - Container ID (default: 104)"
    echo "  CT_HOSTNAME     - Container hostname (default: docker-webtop)"
    echo "  DISK_SIZE       - Disk size in GB (default: 50)"
    echo "  RAM_SIZE        - RAM in MB (default: 8192)"
    echo "  CPU_CORES       - Number of CPU cores (default: 4)"
    echo "  BRIDGE          - Network bridge (default: vmbr0)"
    echo "  IP_ADDRESS      - IP address with CIDR (default: 192.168.4.104/24)"
    echo "  GATEWAY         - Network gateway (default: 192.168.4.1)"
    echo "  STORAGE         - Storage pool (default: local-zfs)"
    echo "  NODE            - Proxmox node (default: still-fawn)"
    echo "  ROOT_PASSWORD   - Root password (leave empty for auto-login)"
    echo "  ENABLE_SSH      - Enable SSH access (default: yes)"
    exit 0
fi

# Check if running on Proxmox node
if [ ! -f /etc/pve/version ]; then
    echo "Error: This script must be run on a Proxmox VE node"
    exit 1
fi

# Create the container
create_docker_lxc