#!/bin/bash
# Test Grafana email alerting
# Usage: ./test-grafana-email.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get Grafana password from K8s secret
GRAFANA_PASS=$(KUBECONFIG=~/kubeconfig kubectl get secret -n monitoring kube-prometheus-stack-grafana -o jsonpath='{.data.admin-password}' | base64 -d)
GRAFANA_URL="http://grafana.app.homelab"

# Get email from SMTP secret
EMAIL=$(KUBECONFIG=~/kubeconfig kubectl get secret -n monitoring smtp-credentials -o jsonpath='{.data.user}' | base64 -d)

echo "=== Grafana Email Test ==="
echo "Grafana URL: $GRAFANA_URL"
echo "Email: $EMAIL"
echo ""

# Check current contact points
echo "--- Current Contact Points ---"
curl -s "$GRAFANA_URL/api/v1/provisioning/contact-points" -u "admin:$GRAFANA_PASS" | jq .
echo ""

# Create/update contact point
echo "--- Creating Email Contact Point ---"
RESULT=$(curl -s -X POST "$GRAFANA_URL/api/v1/provisioning/contact-points" \
  -u "admin:$GRAFANA_PASS" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"homelab-email\",
    \"type\": \"email\",
    \"settings\": {
      \"addresses\": \"$EMAIL\",
      \"singleEmail\": true
    }
  }")
echo "$RESULT" | jq . 2>/dev/null || echo "$RESULT"
echo ""

# Test notification
echo "--- Sending Test Notification ---"
# Get the UID of the contact point we just created
CP_UID=$(curl -s "$GRAFANA_URL/api/v1/provisioning/contact-points" -u "admin:$GRAFANA_PASS" | jq -r '.[] | select(.name=="homelab-email") | .uid')

if [[ -n "$CP_UID" && "$CP_UID" != "null" ]]; then
    TEST_RESULT=$(curl -s -X POST "$GRAFANA_URL/api/alertmanager/grafana/config/api/v1/receivers/test" \
      -u "admin:$GRAFANA_PASS" \
      -H "Content-Type: application/json" \
      -d "{
        \"receivers\": [{
          \"name\": \"homelab-email\",
          \"grafana_managed_receiver_configs\": [{
            \"uid\": \"$CP_UID\",
            \"name\": \"homelab-email\",
            \"type\": \"email\",
            \"settings\": {
              \"addresses\": \"$EMAIL\",
              \"singleEmail\": true
            }
          }]
        }],
        \"alert\": {
          \"labels\": {
            \"alertname\": \"TestAlert\",
            \"severity\": \"info\"
          },
          \"annotations\": {
            \"summary\": \"Test alert from Grafana\",
            \"description\": \"This is a test email to verify alerting works.\"
          }
        }
      }")
    echo "$TEST_RESULT" | jq . 2>/dev/null || echo "$TEST_RESULT"
else
    echo "ERROR: Could not find contact point UID"
fi

echo ""
echo "Check your email: $EMAIL"
