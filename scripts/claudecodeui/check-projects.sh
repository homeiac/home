#!/bin/bash
# Check claudecodeui projects via API
set -e

NAMESPACE="claudecodeui"
SERVICE="claudecodeui"
PORT=3001
LOCAL_PORT=${1:-3001}

echo "=== ClaudeCodeUI Project Check ==="

# Check pod status
echo -e "\n1. Pod status:"
KUBECONFIG=~/kubeconfig kubectl get pods -n "$NAMESPACE" -o wide

# Port-forward in background
echo -e "\n2. Starting port-forward..."
KUBECONFIG=~/kubeconfig kubectl port-forward -n "$NAMESPACE" "svc/$SERVICE" "$LOCAL_PORT:$PORT" &
PF_PID=$!
sleep 3

cleanup() {
    kill $PF_PID 2>/dev/null || true
}
trap cleanup EXIT

# Check API endpoints
echo -e "\n3. Checking API endpoints..."

echo -e "\n--- /api/projects ---"
curl -s "http://localhost:$LOCAL_PORT/api/projects" 2>/dev/null | jq . 2>/dev/null || curl -s "http://localhost:$LOCAL_PORT/api/projects"

echo -e "\n--- /api/status ---"
curl -s "http://localhost:$LOCAL_PORT/api/status" 2>/dev/null | jq . 2>/dev/null || curl -s "http://localhost:$LOCAL_PORT/api/status"

echo -e "\n4. Check in browser: http://localhost:$LOCAL_PORT"
echo "   Press Ctrl+C to stop port-forward"

# Keep port-forward alive for manual testing
wait $PF_PID
