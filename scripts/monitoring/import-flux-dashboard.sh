#!/bin/bash
# Import Flux Grafana Dashboard
# Usage: ./import-flux-dashboard.sh [dashboard_id]
# Default: 14936 (Flux Cluster Stats)
set -e

DASHBOARD_ID="${1:-14936}"

# Get Grafana password from K8s secret
GRAFANA_PASS=$(KUBECONFIG=~/kubeconfig kubectl get secret -n monitoring kube-prometheus-stack-grafana -o jsonpath='{.data.admin-password}' | base64 -d)
GRAFANA_URL="http://grafana.app.homelab"

echo "=== Import Flux Dashboard ==="
echo "Dashboard ID: $DASHBOARD_ID"
echo "Grafana URL: $GRAFANA_URL"
echo ""

# Get datasource UID
echo "--- Finding Prometheus Datasource ---"
DS_UID=$(curl -s "$GRAFANA_URL/api/datasources" -u "admin:$GRAFANA_PASS" | jq -r '.[] | select(.type=="prometheus") | .uid' | head -1)
echo "Datasource UID: $DS_UID"
echo ""

# Fetch dashboard from grafana.com
echo "--- Fetching Dashboard from Grafana.com ---"
DASHBOARD_JSON=$(curl -s "https://grafana.com/api/dashboards/$DASHBOARD_ID" | jq '.json')
if [[ -z "$DASHBOARD_JSON" || "$DASHBOARD_JSON" == "null" ]]; then
    echo "ERROR: Failed to fetch dashboard from grafana.com"
    exit 1
fi
echo "Fetched dashboard JSON"
echo ""

# Replace datasource placeholder with actual UID
DASHBOARD_JSON=$(echo "$DASHBOARD_JSON" | sed "s/\${DS_PROMETHEUS}/$DS_UID/g")

# Import dashboard
echo "--- Importing Dashboard ---"
RESULT=$(curl -s -X POST "$GRAFANA_URL/api/dashboards/db" \
  -u "admin:$GRAFANA_PASS" \
  -H "Content-Type: application/json" \
  -d "{
    \"dashboard\": $DASHBOARD_JSON,
    \"overwrite\": true,
    \"folderId\": 0
  }")

echo "$RESULT" | jq . 2>/dev/null || echo "$RESULT"
echo ""

# Extract dashboard URL
DASH_URL=$(echo "$RESULT" | jq -r '.url // empty')
if [[ -n "$DASH_URL" ]]; then
    echo "Dashboard imported successfully!"
    echo "URL: $GRAFANA_URL$DASH_URL"
else
    echo "Import may have failed. Check the result above."
fi
