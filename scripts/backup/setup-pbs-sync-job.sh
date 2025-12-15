#!/bin/bash
# Setup PBS sync job to replicate backups to external datastore
#
# This script:
# 1. Creates a PBS sync job from homelab-backup to external-hdd
# 2. Configures daily schedule
# 3. Enables deduplication and incremental sync
#
# Prerequisites:
# - setup-pbs-external-datastore.sh has been run
# - Both datastores exist in PBS
#
# Run on: pumped-piglet.maas (where PBS LXC 103 is)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
PBS_LXC_ID=103
SOURCE_DATASTORE="homelab-backup"
TARGET_DATASTORE="external-hdd"
SYNC_JOB_ID="external-sync"
SCHEDULE="daily"  # PBS schedule format

echo "========================================="
echo "PBS Sync Job Setup"
echo "========================================="
echo ""
echo "This creates a PBS sync job to replicate:"
echo "  $SOURCE_DATASTORE -> $TARGET_DATASTORE"
echo ""

# Check we're on a Proxmox host
if ! command -v pct &>/dev/null; then
    echo "ERROR: This script must be run on a Proxmox host (pct not found)"
    exit 1
fi

# Check PBS container exists
if ! pct status $PBS_LXC_ID &>/dev/null; then
    echo "ERROR: PBS container (LXC $PBS_LXC_ID) not found"
    exit 1
fi

# Verify datastores exist
echo "Checking datastores..."

SOURCE_EXISTS=$(pct exec $PBS_LXC_ID -- proxmox-backup-manager datastore list 2>/dev/null | grep -c "^$SOURCE_DATASTORE" || echo "0")
TARGET_EXISTS=$(pct exec $PBS_LXC_ID -- proxmox-backup-manager datastore list 2>/dev/null | grep -c "^$TARGET_DATASTORE" || echo "0")

if [ "$SOURCE_EXISTS" -eq 0 ]; then
    echo "ERROR: Source datastore '$SOURCE_DATASTORE' not found"
    echo ""
    echo "Available datastores:"
    pct exec $PBS_LXC_ID -- proxmox-backup-manager datastore list
    exit 1
fi

if [ "$TARGET_EXISTS" -eq 0 ]; then
    echo "ERROR: Target datastore '$TARGET_DATASTORE' not found"
    echo ""
    echo "Run setup-pbs-external-datastore.sh first to create the external datastore."
    echo ""
    echo "Available datastores:"
    pct exec $PBS_LXC_ID -- proxmox-backup-manager datastore list
    exit 1
fi

echo "  Source: $SOURCE_DATASTORE"
echo "  Target: $TARGET_DATASTORE"
echo ""

# Check if sync job already exists
echo "Checking existing sync jobs..."
if pct exec $PBS_LXC_ID -- proxmox-backup-manager sync-job list 2>/dev/null | grep -q "^$SYNC_JOB_ID"; then
    echo "Sync job '$SYNC_JOB_ID' already exists"
    echo ""
    echo "Current configuration:"
    pct exec $PBS_LXC_ID -- proxmox-backup-manager sync-job list
    echo ""
    read -p "Update existing sync job? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing configuration."
        exit 0
    fi
    # Remove existing job to recreate
    pct exec $PBS_LXC_ID -- proxmox-backup-manager sync-job remove "$SYNC_JOB_ID"
    echo "Removed existing sync job"
fi

# Create sync job
# Note: PBS sync jobs work between datastores on the same server
# For local-to-local sync, we use a "pull" job from the target datastore
echo ""
echo "Creating sync job '$SYNC_JOB_ID'..."

# PBS sync jobs require a remote configuration for the source
# For local datastores, we need to set up differently

# First, let's check if there's a local remote configured
LOCAL_REMOTE="local-pbs"

# Create or verify local remote pointing to ourselves
if ! pct exec $PBS_LXC_ID -- proxmox-backup-manager remote list 2>/dev/null | grep -q "^$LOCAL_REMOTE"; then
    echo "Creating local remote configuration..."

    # Get the PBS API token or use password auth
    # For simplicity, we'll create a token for sync

    # First, ensure we have the API token or prompt for auth
    echo "NOTE: PBS sync jobs require authentication."
    echo ""
    echo "Option 1: Use existing admin credentials"
    echo "Option 2: Create a dedicated sync token"
    echo ""

    # Try to create with fingerprint of local server
    FINGERPRINT=$(pct exec $PBS_LXC_ID -- openssl s_client -connect localhost:8007 2>/dev/null </dev/null | openssl x509 -fingerprint -sha256 -noout 2>/dev/null | cut -d= -f2 || echo "")

    if [ -z "$FINGERPRINT" ]; then
        echo "Could not auto-detect server fingerprint."
        echo ""
        echo "Please configure the sync job manually via PBS Web UI:"
        echo "  1. Go to https://192.168.4.218:8007"
        echo "  2. Navigate to Datastore > $TARGET_DATASTORE > Sync Jobs"
        echo "  3. Add sync job from $SOURCE_DATASTORE"
        echo ""
        exit 0
    fi

    echo "Server fingerprint: $FINGERPRINT"
    echo ""
    read -p "Enter PBS root@pam password for sync authentication: " -s PBS_PASSWORD
    echo ""

    # Create remote
    pct exec $PBS_LXC_ID -- proxmox-backup-manager remote create \
        "$LOCAL_REMOTE" \
        --host localhost \
        --auth-id "root@pam" \
        --password "$PBS_PASSWORD" \
        --fingerprint "$FINGERPRINT"

    echo "Local remote created"
fi

# Now create the sync job
# The sync job pulls from remote (source) to local (target) datastore
echo ""
echo "Creating sync job..."

pct exec $PBS_LXC_ID -- proxmox-backup-manager sync-job create \
    "$SYNC_JOB_ID" \
    --remote "$LOCAL_REMOTE" \
    --remote-store "$SOURCE_DATASTORE" \
    --store "$TARGET_DATASTORE" \
    --schedule "$SCHEDULE" \
    --remove-vanished true \
    --comment "Sync homelab backups to external HDD"

echo "Sync job created successfully"

# Show sync job configuration
echo ""
echo "Sync job configuration:"
pct exec $PBS_LXC_ID -- proxmox-backup-manager sync-job list

# Run initial sync
echo ""
read -p "Run initial sync now? This may take a while. [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Starting initial sync..."
    echo "You can monitor progress in PBS Web UI: https://192.168.4.218:8007"
    echo ""
    pct exec $PBS_LXC_ID -- proxmox-backup-manager sync-job run "$SYNC_JOB_ID" &
    SYNC_PID=$!
    echo "Sync started in background (PID: $SYNC_PID)"
    echo ""
    echo "To monitor:"
    echo "  pct exec $PBS_LXC_ID -- proxmox-backup-manager task list"
fi

echo ""
echo "========================================="
echo "Setup Complete"
echo "========================================="
echo ""
echo "Sync job '$SYNC_JOB_ID' configured:"
echo "  Source: $SOURCE_DATASTORE (via $LOCAL_REMOTE)"
echo "  Target: $TARGET_DATASTORE"
echo "  Schedule: $SCHEDULE"
echo "  Remove vanished: yes"
echo ""
echo "Commands:"
echo "  Run sync now:    pct exec $PBS_LXC_ID -- proxmox-backup-manager sync-job run $SYNC_JOB_ID"
echo "  List sync jobs:  pct exec $PBS_LXC_ID -- proxmox-backup-manager sync-job list"
echo "  View tasks:      pct exec $PBS_LXC_ID -- proxmox-backup-manager task list"
echo ""
echo "PBS Web UI: https://192.168.4.218:8007"
