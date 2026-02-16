#!/bin/bash
# test-sms-gateway.sh - Test SMS Gateway connectivity
# Supports: Traccar SMS Gateway (Play Store)
#
# Usage:
#   ./test-sms-gateway.sh                           # Use SOPS-encrypted defaults
#   ./test-sms-gateway.sh <phone-ip> <token> <recipient>

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SOPS_SECRET="$REPO_ROOT/gitops/clusters/homelab/infrastructure/nut-pve/secrets/sms-gateway-creds.sops.yaml"

# Try to load from SOPS if no args provided
if [[ $# -eq 0 ]] && [[ -f "$SOPS_SECRET" ]] && command -v sops &>/dev/null; then
  echo "Loading credentials from SOPS..."
  eval "$(sops -d "$SOPS_SECRET" | grep -E '^\s+\w+:' | sed 's/^[[:space:]]*/export /' | sed 's/: /=/' | tr -d '"')"
  PHONE_IP="${SMS_GATEWAY_IP:-192.0.0.4}"
  SMS_TOKEN="${SMS_GATEWAY_TOKEN:-}"
  RECIPIENT="${SMS_RECIPIENT:-}"
  SMS_PORT="8082"
else
  PHONE_IP="${1:-192.0.0.4}"
  SMS_TOKEN="${2:-CHANGE_ME}"
  RECIPIENT="${3:-+1XXXXXXXXXX}"
  SMS_PORT="${4:-8082}"
fi

if [[ -z "$SMS_TOKEN" ]] || [[ "$SMS_TOKEN" == "CHANGE_ME" ]]; then
  echo "Usage: $0 <phone-ip> <token> <recipient> [port]"
  echo ""
  echo "  phone-ip   IP address of phone running Traccar SMS Gateway"
  echo "  token      Authorization token from Traccar SMS Gateway app"
  echo "  recipient  Phone number to send test SMS (e.g., +15551234567)"
  echo "  port       Optional, default 8082"
  echo ""
  echo "Or run without args to load from SOPS-encrypted secrets."
  exit 1
fi

echo "=== Traccar SMS Gateway Test ==="
echo "Phone IP: ${PHONE_IP}"
echo "Port: ${SMS_PORT}"
echo "Recipient: ${RECIPIENT}"
echo ""

# First test connectivity
echo "Testing connectivity..."
if ! nc -z -w 3 "${PHONE_IP}" "${SMS_PORT}" 2>/dev/null; then
  echo "✗ Cannot connect to ${PHONE_IP}:${SMS_PORT}"
  echo ""
  echo "Troubleshooting:"
  echo "  1. Is Traccar SMS Gateway app open?"
  echo "  2. Is 'HTTP server' enabled in the app?"
  echo "  3. Is the phone on the same network (or hotspot connected)?"
  echo "  4. Check the IP shown in the app"
  exit 1
fi
echo "✓ Port ${SMS_PORT} is reachable"
echo ""

echo "Sending test SMS..."
response=$(curl -s -w "\n%{http_code}" -X POST "http://${PHONE_IP}:${SMS_PORT}/" \
  -H "Authorization: ${SMS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"to\": \"${RECIPIENT}\", \"message\": \"[TEST] SMS Gateway test at $(date '+%Y-%m-%d %H:%M:%S')\"}" \
  --connect-timeout 5 \
  --max-time 10)

http_code=$(echo "$response" | tail -1)
body=$(echo "$response" | head -n -1)

echo ""
if [[ "$http_code" == "200" ]] || [[ "$http_code" == "204" ]]; then
  echo "✓ SMS sent successfully!"
  echo "HTTP: $http_code"
  [[ -n "$body" ]] && echo "Response: $body"
  echo ""
  echo "Check your phone for the incoming SMS."
elif [[ "$http_code" == "401" ]] || [[ "$http_code" == "403" ]]; then
  echo "✗ Authentication failed (HTTP $http_code)"
  echo "Check the Authorization token in Traccar SMS Gateway app"
  exit 1
else
  echo "✗ Failed with HTTP $http_code"
  echo "Response: $body"
  exit 1
fi
