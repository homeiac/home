#!/bin/bash
# Automation using keystroke simulation for Proxmox VE Helper Scripts

set -e

echo "Creating Docker LXC using keystroke automation..."

# Create a script that sends the exact keystrokes needed
cat > /tmp/docker-keystrokes.sh << 'EOF'
#!/bin/bash

# Set proper environment
export TERM=xterm
export DEBIAN_FRONTEND=noninteractive

# Function to send keystrokes to the script
send_keystrokes() {
    # Download and start the script
    curl -fsSL https://github.com/community-scripts/ProxmoxVE/raw/main/ct/docker.sh | bash << 'KEYSTROKES'
y
y
104
docker-webtop
50
4
8192
vmbr0
192.168.4.104/24
192.168.4.1
n


192.168.4.1


y
y
y
KEYSTROKES
}

send_keystrokes
EOF

chmod +x /tmp/docker-keystrokes.sh

echo "Running keystroke automation..."
/tmp/docker-keystrokes.sh

echo "Checking if container was created..."
if pct status 104 >/dev/null 2>&1; then
    echo "✓ Container 104 created successfully!"
    pct start 104
    echo "✓ Container started"
    
    # Verify Docker is installed
    sleep 5
    if pct exec 104 -- which docker >/dev/null 2>&1; then
        echo "✓ Docker is installed"
        pct exec 104 -- docker --version
    else
        echo "⚠ Docker installation needs verification"
    fi
else
    echo "✗ Container creation failed"
    exit 1
fi