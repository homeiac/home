#!/bin/bash
#
# deploy_uptime_kuma.sh - Deploy Uptime Kuma to Docker LXC containers
#
# This script should be run directly on each Proxmox node to deploy Uptime Kuma
# in the local Docker LXC container.
#
# Usage: ./deploy_uptime_kuma.sh [lxc_id]
#

set -e

# Configuration
UPTIME_KUMA_IMAGE="louislam/uptime-kuma:1"
CONTAINER_NAME="uptime-kuma"
CONTAINER_PORT="3001"
VOLUME_NAME="uptime-kuma-data"
MEMORY_LIMIT="512m"

# Default LXC IDs for known nodes
case $(hostname) in
    "pve")
        DEFAULT_LXC_ID=100
        ;;
    "fun-bedbug") 
        DEFAULT_LXC_ID=112
        ;;
    *)
        DEFAULT_LXC_ID=""
        ;;
esac

# Use provided LXC ID or default
LXC_ID=${1:-$DEFAULT_LXC_ID}

if [ -z "$LXC_ID" ]; then
    echo "❌ Error: No LXC ID provided and no default for hostname $(hostname)"
    echo "Usage: $0 <lxc_id>"
    echo "Available LXC containers:"
    pct list
    exit 1
fi

echo "🚀 Deploying Uptime Kuma to LXC container $LXC_ID on $(hostname)"

# Verify LXC container exists and is running
if ! pct status $LXC_ID | grep -q "running"; then
    echo "❌ Error: LXC container $LXC_ID is not running"
    echo "Current status:"
    pct status $LXC_ID
    exit 1
fi

# Verify Docker is available in the container
if ! pct exec $LXC_ID -- which docker >/dev/null 2>&1; then
    echo "❌ Error: Docker is not installed in LXC container $LXC_ID"
    echo "Please install Docker first or use a different container"
    exit 1
fi

echo "✅ LXC container $LXC_ID is running with Docker"

# Check if Uptime Kuma container already exists
if pct exec $LXC_ID -- docker ps -a --filter name=$CONTAINER_NAME --format "{{.Names}}" | grep -q $CONTAINER_NAME; then
    echo "📦 Uptime Kuma container already exists"
    
    # Check if it's running
    if pct exec $LXC_ID -- docker ps --filter name=$CONTAINER_NAME --format "{{.Names}}" | grep -q $CONTAINER_NAME; then
        echo "✅ Uptime Kuma is already running"
        STATUS="already_running"
    else
        echo "🔄 Starting existing Uptime Kuma container..."
        pct exec $LXC_ID -- docker start $CONTAINER_NAME
        STATUS="started"
    fi
else
    echo "🆕 Creating new Uptime Kuma container..."
    
    # Pull latest image
    echo "📥 Pulling Uptime Kuma image..."
    pct exec $LXC_ID -- docker pull $UPTIME_KUMA_IMAGE
    
    # Create and start container
    pct exec $LXC_ID -- docker run -d \
        --name $CONTAINER_NAME \
        --restart unless-stopped \
        -p $CONTAINER_PORT:$CONTAINER_PORT \
        -v $VOLUME_NAME:/app/data \
        --memory $MEMORY_LIMIT \
        $UPTIME_KUMA_IMAGE
    
    echo "✅ Uptime Kuma container created and started"
    STATUS="deployed"
fi

# Get container IP
echo "🌐 Getting container network information..."
CONTAINER_IP=$(pct exec $LXC_ID -- ip addr show eth0 | grep "inet " | awk '{print $2}' | cut -d/ -f1)

if [ -n "$CONTAINER_IP" ]; then
    echo "🎉 Deployment complete!"
    echo "   Node: $(hostname)"
    echo "   LXC Container: $LXC_ID"
    echo "   Status: $STATUS"
    echo "   URL: http://$CONTAINER_IP:$CONTAINER_PORT"
    echo ""
    echo "🔗 Access Uptime Kuma at: http://$CONTAINER_IP:$CONTAINER_PORT"
    echo "📝 Configure monitoring targets manually in the web interface"
else
    echo "⚠️  Could not determine container IP address"
    echo "   You can still access Uptime Kuma via port $CONTAINER_PORT on this node"
fi

# Wait for service to be ready
echo "⏳ Waiting for Uptime Kuma to be ready..."
for i in {1..30}; do
    if [ -n "$CONTAINER_IP" ] && curl -s "http://$CONTAINER_IP:$CONTAINER_PORT" >/dev/null 2>&1; then
        echo "✅ Uptime Kuma is ready and responding!"
        break
    elif [ $i -eq 30 ]; then
        echo "⚠️  Uptime Kuma may still be starting up. Check manually at http://$CONTAINER_IP:$CONTAINER_PORT"
    else
        sleep 2
    fi
done

echo ""
echo "📋 Next steps:"
echo "1. Access the web interface at http://$CONTAINER_IP:$CONTAINER_PORT"
echo "2. Complete initial setup (create admin account)"
echo "3. Configure SMTP settings for notifications"
echo "4. Add monitoring targets for your infrastructure"
echo "5. Run this script on other Proxmox nodes for redundancy"