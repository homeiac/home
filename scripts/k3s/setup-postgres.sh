#!/bin/bash
# Setup PostgreSQL with pgvector, TimescaleDB, and PBS backups on K3s
# This script deploys via Flux GitOps

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

echo "========================================="
echo "PostgreSQL K3s Deployment Setup"
echo "========================================="
echo ""

# Step 1: Verify cluster is accessible
echo "Step 1: Verifying K3s cluster access..."
kubectl cluster-info
echo ""

# Step 2: Check if postgres namespace exists
echo "Step 2: Checking for existing postgres deployment..."
if kubectl get namespace database >/dev/null 2>&1; then
    echo "  ⚠ WARNING: database namespace already exists"
    read -p "  Continue anyway? (y/N): " confirm
    if [ "$confirm" != "y" ]; then
        echo "  Aborted"
        exit 1
    fi
fi
echo ""

# Step 3: Remind about secret configuration
echo "Step 3: ⚠ SECURITY REMINDER"
echo "  Before deploying, update the password in:"
echo "  gitops/clusters/homelab/apps/postgres/secret.yaml"
echo ""
echo "  Change 'changeme-secure-password' to a strong password"
echo "  (DO NOT commit the real password to git - see CLAUDE.md)"
echo ""
read -p "  Have you updated the password? (y/N): " password_confirm
if [ "$password_confirm" != "y" ]; then
    echo "  ⚠ Please update the password before deploying"
    exit 1
fi
echo ""

# Step 4: Commit and push changes
echo "Step 4: Committing GitOps configuration..."
cd "$REPO_ROOT"
git status
echo ""
read -p "  Commit and push changes? (y/N): " git_confirm
if [ "$git_confirm" = "y" ]; then
    git add gitops/clusters/homelab/apps/postgres/
    git add gitops/clusters/homelab/kustomization.yaml
    git commit -m "feat(k8s): add PostgreSQL with pgvector, TimescaleDB, and PBS backups

- PostgreSQL 16 with TimescaleDB, pgvector, PostGIS extensions
- 100Gi persistent storage for database
- 50Gi persistent storage for backups
- Daily automated backups via CronJob
- LoadBalancer service on 192.168.4.51
- Database namespace for organization

Related: Infrastructure enhancement for AI workloads"

    git push
    echo "  ✓ Changes pushed to GitOps repository"
else
    echo "  ⚠ Skipping git commit - you'll need to commit manually"
fi
echo ""

# Step 5: Monitor Flux reconciliation
echo "Step 5: Monitoring Flux deployment..."
echo "  Waiting for Flux to reconcile (this may take 1-2 minutes)..."
sleep 5

kubectl get kustomization -n flux-system -w &
WATCH_PID=$!
sleep 60
kill $WATCH_PID 2>/dev/null || true
echo ""

# Step 6: Check deployment status
echo "Step 6: Checking PostgreSQL deployment status..."
kubectl get all -n database
echo ""

# Step 7: Check PVC status
echo "Step 7: Checking persistent volume claims..."
kubectl get pvc -n database
echo ""

# Step 8: Display connection information
echo "========================================="
echo "PostgreSQL Deployment Summary"
echo "========================================="
echo ""
echo "Service: postgres.app.homelab:5432 (via Traefik)"
echo "Traefik IP: 192.168.4.80"
echo "Database: homelab"
echo "Username: postgres"
echo ""
echo "Connection string:"
echo "  postgresql://postgres:<password>@postgres.app.homelab:5432/homelab"
echo ""
echo "Installed extensions:"
echo "  - TimescaleDB (time-series data)"
echo "  - pgvector (vector embeddings)"
echo "  - PostGIS (geospatial/graph operations)"
echo "  - JSONB (built-in JSON support)"
echo ""
echo "Backups:"
echo "  - Daily at 2 AM"
echo "  - Stored in postgres-backup PVC"
echo "  - 7-day retention"
echo ""
echo "Next steps:"
echo "  1. Wait for pod to be Running: kubectl get pods -n database -w"
echo "  2. Verify Traefik config updated: kubectl get svc -n kube-system traefik"
echo "  3. Test connection from cluster: kubectl run -it --rm psql --image=postgres:16 --restart=Never -- psql -h postgres.database.svc.cluster.local -U postgres"
echo "  4. Test external: psql -h postgres.app.homelab -U postgres -d homelab"
echo "  5. Configure PBS to backup the postgres-data PVC"
echo ""
