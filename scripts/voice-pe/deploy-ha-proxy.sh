#!/bin/bash
# Deploy ha-proxy.service to pve host
# This socat proxy allows Voice PE to reach Home Assistant across network segments
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/../../proxmox/systemd/ha-proxy.service"
TARGET_HOST="pve.maas"
TARGET_PATH="/etc/systemd/system/ha-proxy.service"

echo "=== Deploy ha-proxy.service to $TARGET_HOST ==="
echo ""

# Check service file exists
if [[ ! -f "$SERVICE_FILE" ]]; then
    echo "ERROR: Service file not found: $SERVICE_FILE"
    exit 1
fi

echo "1. Copying service file to $TARGET_HOST..."
scp "$SERVICE_FILE" "root@$TARGET_HOST:$TARGET_PATH"

echo "2. Reloading systemd daemon..."
ssh "root@$TARGET_HOST" "systemctl daemon-reload"

echo "3. Enabling service..."
ssh "root@$TARGET_HOST" "systemctl enable ha-proxy.service"

echo "4. Restarting service..."
ssh "root@$TARGET_HOST" "systemctl restart ha-proxy.service"

echo "5. Checking status..."
ssh "root@$TARGET_HOST" "systemctl status ha-proxy.service --no-pager"

echo ""
echo "=== Verification ==="
echo "Testing proxy from $TARGET_HOST..."
ssh "root@$TARGET_HOST" "curl -s --max-time 5 http://192.168.4.240:8123/ | head -c 50 && echo '... OK'"

echo ""
echo "Done. ha-proxy.service deployed successfully."
echo ""
echo "Voice PE should now be able to reach HA via http://192.168.1.122:8123"
