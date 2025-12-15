#!/bin/bash
# Reset PostgreSQL deployment - deletes all data and reinitializes
# This ensures init scripts run to create extensions

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECTL="${KUBECTL:-kubectl}"

echo "⚠️  WARNING: This will DELETE all PostgreSQL data!"
echo "Press Ctrl+C within 5 seconds to abort..."
sleep 5

echo ""
echo "=== Resetting PostgreSQL deployment ==="

echo "1. Deleting HelmRelease..."
$KUBECTL delete helmrelease postgres -n database --ignore-not-found

echo "2. Waiting for pod termination..."
$KUBECTL wait --for=delete pod/postgres-postgresql-0 -n database --timeout=60s 2>/dev/null || true

echo "3. Deleting PVCs (all data will be lost)..."
$KUBECTL delete pvc --all -n database

echo "4. Triggering Flux reconciliation..."
$KUBECTL annotate --overwrite kustomization flux-system -n flux-system \
    reconcile.fluxcd.io/requestedAt="$(date +%s)"

echo "5. Waiting for new deployment..."
sleep 10

echo "6. Checking status..."
$KUBECTL get helmrelease,pods,pvc -n database

echo ""
echo "=== Reset complete ==="
echo "Monitor with: kubectl get pods -n database -w"
