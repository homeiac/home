#!/bin/bash
# Check Crossplane provider-proxmox state health
# Verifies: provider pod running, CPU usage, tf-* state secrets, managed resource status
#
# Usage: ./scripts/crossplane/check-state-health.sh
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== Crossplane State Health Check ==="
echo ""

# 1. Provider pod status
echo "--- Provider Pod ---"
PROVIDER_PODS=$(kubectl get pods -n crossplane-system -l pkg.crossplane.io/revision -o wide --no-headers 2>/dev/null || true)
if [[ -z "$PROVIDER_PODS" ]]; then
  echo -e "${RED}No provider pods found in crossplane-system${NC}"
else
  echo "$PROVIDER_PODS"
fi
echo ""

# 2. Provider pod CPU usage
echo "--- Provider CPU Usage ---"
kubectl top pod -n crossplane-system --no-headers 2>/dev/null || echo -e "${YELLOW}metrics-server unavailable or no pods running${NC}"
echo ""

# 3. Resource limits applied
echo "--- Resource Limits ---"
kubectl get pods -n crossplane-system -l pkg.crossplane.io/revision -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{range .spec.containers[*]}  {.name}: cpu={.resources.limits.cpu} mem={.resources.limits.memory}{"\n"}{end}{end}' 2>/dev/null || echo -e "${YELLOW}No provider pods to check${NC}"
echo ""

# 4. Terraform state secrets
echo "--- Terraform State Secrets ---"
TF_SECRETS=$(kubectl get secrets -n crossplane-system --no-headers 2>/dev/null | grep "^tf-" || true)
TF_COUNT=$(echo "$TF_SECRETS" | grep -c "^tf-" 2>/dev/null || echo "0")
echo "Found $TF_COUNT tf-* state secrets"
if [[ -n "$TF_SECRETS" ]]; then
  echo "$TF_SECRETS"
fi
echo ""

# 5. Managed resources status
echo "--- Managed Resources ---"
for KIND in environmentdownloadfile environmentvm; do
  RESOURCES=$(kubectl get "$KIND" --no-headers 2>/dev/null || true)
  if [[ -n "$RESOURCES" ]]; then
    echo "$KIND:"
    kubectl get "$KIND" -o custom-columns='NAME:.metadata.name,SYNCED:.status.conditions[?(@.type=="Synced")].status,READY:.status.conditions[?(@.type=="Ready")].status,PAUSED:.metadata.annotations.crossplane\.io/paused' 2>/dev/null || echo "$RESOURCES"
    echo ""
  fi
done

# 6. Provider health
echo "--- Provider Status ---"
kubectl get provider --no-headers 2>/dev/null || echo -e "${YELLOW}No providers found${NC}"
echo ""

# 7. Summary
echo "=== Summary ==="
HELMRELEASE_SUSPENDED=$(kubectl get helmrelease crossplane -n crossplane-system -o jsonpath='{.spec.suspend}' 2>/dev/null || echo "unknown")
echo "HelmRelease suspended: $HELMRELEASE_SUSPENDED"
echo "State secrets: $TF_COUNT"

PAUSED_COUNT=$(kubectl get environmentdownloadfile,environmentvm -o json 2>/dev/null | grep -c '"crossplane.io/paused": "true"' || echo "0")
TOTAL_COUNT=$(kubectl get environmentdownloadfile,environmentvm --no-headers 2>/dev/null | wc -l | tr -d ' ')
echo "Paused resources: $PAUSED_COUNT / $TOTAL_COUNT"

if [[ "$TF_COUNT" -eq 0 && "$HELMRELEASE_SUSPENDED" == "false" ]]; then
  echo -e "${YELLOW}WARNING: No state secrets found but Crossplane is active. Provider may recreate resources on first reconcile.${NC}"
fi
