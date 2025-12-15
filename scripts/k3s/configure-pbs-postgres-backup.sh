#!/bin/bash
# Configure Proxmox Backup Server to backup K3s VM containing PostgreSQL data
# This ensures PostgreSQL data is backed up to PBS at the VM level

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================="
echo "Configure PBS Backup for PostgreSQL"
echo "========================================="
echo ""

# Detect which K3s VM is running PostgreSQL
echo "Step 1: Detecting K3s node running PostgreSQL..."
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

# Get the node where postgres pod is scheduled
NODE=$(kubectl get pod -n database -l app=postgres -o jsonpath='{.items[0].spec.nodeName}' 2>/dev/null || echo "")

if [ -z "$NODE" ]; then
    echo "  ⚠ PostgreSQL pod not found or not yet scheduled"
    echo "  Please deploy PostgreSQL first using setup-postgres.sh"
    exit 1
fi

echo "  PostgreSQL is running on node: $NODE"
echo ""

# Map node name to Proxmox host and VMID
case "$NODE" in
    *"still-fawn"*)
        PVE_HOST="still-fawn.maas"
        VMID="108"
        ;;
    *"pumped-piglet"*)
        PVE_HOST="pumped-piglet.maas"
        VMID="105"
        ;;
    *)
        echo "  ⚠ Unknown node: $NODE"
        echo "  Cannot determine Proxmox host and VMID"
        exit 1
        ;;
esac

echo "Step 2: Proxmox VM Details"
echo "  Host: $PVE_HOST"
echo "  VMID: $VMID"
echo ""

# Check current backup configuration
echo "Step 3: Checking current backup configuration..."
ssh root@$PVE_HOST << REMOTE_CHECK
set -e

echo "  Current VM backup jobs:"
vzdump_jobs=\$(cat /etc/pve/vzdump.cron 2>/dev/null || echo "No cron jobs found")
echo "\$vzdump_jobs"
echo ""

echo "  Current backup schedules:"
pvesh get /cluster/backup 2>/dev/null || echo "  No backup schedules configured"
REMOTE_CHECK

echo ""
echo "Step 4: Recommended PBS Backup Configuration"
echo ""
echo "To ensure PostgreSQL data is backed up to PBS, configure a backup job:"
echo ""
echo "Option 1: Via Proxmox Web UI"
echo "  1. Navigate to Datacenter → Backup"
echo "  2. Add a new backup job:"
echo "     - Storage: homelab-backup (PBS)"
echo "     - Schedule: Daily at 3 AM (after PostgreSQL dumps)"
echo "     - Selection Mode: Include selected VMs"
echo "     - Virtual Machines: $VMID"
echo "     - Retention: Keep last 7 backups"
echo "     - Compression: ZSTD"
echo "     - Mode: Snapshot"
echo ""
echo "Option 2: Via CLI on $PVE_HOST"
echo "  Run this command on the Proxmox host:"
echo ""
echo "  ssh root@$PVE_HOST"
echo "  pvesh create /cluster/backup \\"
echo "    --schedule 'daily-03:00' \\"
echo "    --storage 'homelab-backup' \\"
echo "    --vmid '$VMID' \\"
echo "    --mode 'snapshot' \\"
echo "    --compress 'zstd' \\"
echo "    --prune-backups 'keep-last=7' \\"
echo "    --enabled 1"
echo ""
echo "========================================="
echo "Backup Strategy Summary"
echo "========================================="
echo ""
echo "Two-tier backup approach:"
echo ""
echo "1. Application-level (K8s CronJob)"
echo "   - Daily pg_dumpall at 2 AM"
echo "   - Stored in postgres-backup PVC"
echo "   - 7-day retention"
echo "   - Fast recovery for database-only issues"
echo ""
echo "2. Infrastructure-level (PBS)"
echo "   - Daily VM snapshot at 3 AM (recommended)"
echo "   - Includes entire K3s node with PostgreSQL data"
echo "   - Stored in Proxmox Backup Server"
echo "   - Full disaster recovery capability"
echo ""
echo "Note: The postgres-data PVC is stored in the VM's local-path"
echo "      storage, so backing up the VM includes the PostgreSQL data."
echo ""
