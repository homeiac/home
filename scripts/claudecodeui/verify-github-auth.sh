#!/bin/bash
# verify-github-auth.sh - Verify GitHub SSH auth and git config in Claude Code UI pod
# Usage: ./scripts/claudecodeui/verify-github-auth.sh
set -euo pipefail

NAMESPACE="claudecodeui"
LABEL="app=claudecodeui-blue"
SSH_DIR="/home/claude/.claude/ssh"

echo "=== Claude Code UI: GitHub Auth Verification ==="
echo ""

# Find the pod
POD=$(kubectl get pods -n "$NAMESPACE" -l "$LABEL" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [[ -z "$POD" ]]; then
    echo "ERROR: No running pod found with label $LABEL in namespace $NAMESPACE"
    exit 1
fi
echo "Pod: $POD"
echo ""

# Check 1: SSH key exists (stored in PVC at /home/claude/.claude/ssh/)
echo "--- Check 1: SSH key files ---"
kubectl exec -n "$NAMESPACE" "$POD" -- ls -la "$SSH_DIR/" 2>/dev/null || {
    echo "FAIL: $SSH_DIR/ not found"
    exit 1
}
echo ""

# Check 2: SSH config
echo "--- Check 2: SSH config ---"
kubectl exec -n "$NAMESPACE" "$POD" -- cat "$SSH_DIR/config" 2>/dev/null || echo "WARN: No SSH config"
echo ""

# Check 3: known_hosts
echo "--- Check 3: known_hosts ---"
kubectl exec -n "$NAMESPACE" "$POD" -- wc -l "$SSH_DIR/known_hosts" 2>/dev/null || echo "FAIL: No known_hosts"
echo ""

# Check 4: Test GitHub SSH connection (uses GIT_SSH_COMMAND env var)
echo "--- Check 4: GitHub SSH test ---"
kubectl exec -n "$NAMESPACE" "$POD" -- ssh -F "$SSH_DIR/config" -T git@github.com 2>&1 || true
echo ""

# Check 5: Git identity
echo "--- Check 5: Git env vars ---"
kubectl exec -n "$NAMESPACE" "$POD" -- env | grep -E "^GIT_" 2>/dev/null || echo "WARN: No GIT_ env vars"
echo ""

# Check 6: GH_TOKEN
echo "--- Check 6: GH_TOKEN ---"
kubectl exec -n "$NAMESPACE" "$POD" -- sh -c 'if [ -n "$GH_TOKEN" ]; then echo "GH_TOKEN is set (${#GH_TOKEN} chars)"; else echo "WARN: GH_TOKEN not set"; fi'
echo ""

# Check 7: Test clone (quick, small repo)
echo "--- Check 7: Test git clone ---"
kubectl exec -n "$NAMESPACE" "$POD" -- sh -c 'rm -rf /tmp/ssh-test && git clone --depth 1 git@github.com:homeiac/home.git /tmp/ssh-test 2>&1 && echo "SUCCESS: Clone worked" && rm -rf /tmp/ssh-test' || echo "FAIL: Clone failed"
echo ""

echo "=== Verification Complete ==="
