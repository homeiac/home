#!/bin/bash
# Configure Grafana to send all alerts to email
# Usage: ./configure-email-alerts.sh
set -e

# Get Grafana password from K8s secret
GRAFANA_PASS=$(KUBECONFIG=~/kubeconfig kubectl get secret -n monitoring kube-prometheus-stack-grafana -o jsonpath='{.data.admin-password}' | base64 -d)
GRAFANA_URL="http://grafana.app.homelab"

echo "=== Configure Email Alert Routing ==="

# Get current notification policy
echo "--- Current Notification Policy ---"
curl -s "$GRAFANA_URL/api/v1/provisioning/policies" -u "admin:$GRAFANA_PASS" | jq .
echo ""

# Update notification policy to use homelab-email as default
echo "--- Updating Notification Policy ---"
RESULT=$(curl -s -X PUT "$GRAFANA_URL/api/v1/provisioning/policies" \
  -u "admin:$GRAFANA_PASS" \
  -H "Content-Type: application/json" \
  -d '{
    "receiver": "homelab-email",
    "group_by": ["alertname", "namespace"],
    "group_wait": "30s",
    "group_interval": "5m",
    "repeat_interval": "4h"
  }')
echo "$RESULT" | jq . 2>/dev/null || echo "$RESULT"
echo ""

# Verify
echo "--- Updated Notification Policy ---"
curl -s "$GRAFANA_URL/api/v1/provisioning/policies" -u "admin:$GRAFANA_PASS" | jq .
echo ""

echo "Done! All alerts will now be sent to email."
