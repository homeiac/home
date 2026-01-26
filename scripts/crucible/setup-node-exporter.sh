#!/bin/bash
# Install node_exporter on proper-raptor for Prometheus monitoring
#
set -e

HOST="ubuntu@192.168.4.189"
NODE_EXPORTER_VERSION="1.7.0"

echo "=== Installing node_exporter on proper-raptor ==="

# Check SSH access
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$HOST" "echo 'SSH OK'" 2>/dev/null; then
    echo "ERROR: Cannot SSH to $HOST"
    exit 1
fi

echo "=== Step 1: Download and install node_exporter ==="
ssh "$HOST" << EOF
set -e
cd /tmp
curl -LO https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
tar xzf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
sudo mv node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64/node_exporter /usr/local/bin/
rm -rf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64*
node_exporter --version
EOF

echo "=== Step 2: Create systemd service ==="
ssh "$HOST" "sudo tee /etc/systemd/system/node_exporter.service" << 'EOF'
[Unit]
Description=Prometheus Node Exporter
After=network.target

[Service]
Type=simple
User=nobody
ExecStart=/usr/local/bin/node_exporter
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "=== Step 3: Start and enable service ==="
ssh "$HOST" "sudo systemctl daemon-reload && sudo systemctl enable --now node_exporter"

echo "=== Step 4: Verify ==="
ssh "$HOST" "systemctl status node_exporter --no-pager"
ssh "$HOST" "curl -s http://localhost:9100/metrics | head -20"

echo ""
echo "=== node_exporter installed ==="
echo "Metrics available at: http://192.168.4.189:9100/metrics"
echo ""
echo "Add to Prometheus scrape config:"
echo "  - job_name: 'crucible-node'"
echo "    static_configs:"
echo "      - targets: ['192.168.4.189:9100']"
