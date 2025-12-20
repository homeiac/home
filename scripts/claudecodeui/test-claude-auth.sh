#!/bin/bash
# Test Claude auth in the claudecodeui container
set -e

NAMESPACE="claudecodeui"
DEPLOYMENT="claudecodeui"

echo "=== Testing Claude Auth in Container ==="

# Check credentials file exists
echo -e "\n1. Checking credentials file..."
KUBECONFIG=~/kubeconfig kubectl exec -n "$NAMESPACE" "deploy/$DEPLOYMENT" -- \
  ls -la /home/claude/.claude/.credentials.json

# Check expiry
echo -e "\n2. Checking token expiry..."
KUBECONFIG=~/kubeconfig kubectl exec -n "$NAMESPACE" "deploy/$DEPLOYMENT" -- \
  cat /home/claude/.claude/.credentials.json | python3 -c "
import json, sys, datetime
data = json.load(sys.stdin)
oauth = data.get('claudeAiOauth', {})
expires = oauth.get('expiresAt', 0)
expires_dt = datetime.datetime.fromtimestamp(expires/1000)
print(f'Subscription: {oauth.get(\"subscriptionType\")}')
print(f'Expires: {expires_dt}')
print(f'Valid: {expires_dt > datetime.datetime.now()}')
"

# Test a simple Claude query
echo -e "\n3. Testing Claude query (simple math)..."
KUBECONFIG=~/kubeconfig kubectl exec -n "$NAMESPACE" "deploy/$DEPLOYMENT" -- \
  bash -c "cd /home/claude/projects/home && claude -p 'What is 2+2? Reply with just the number.' --output-format text 2>&1 | head -20"

echo -e "\n=== Test Complete ==="
