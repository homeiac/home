#!/bin/bash
# Setup PBS verify job for backup integrity checking
#
# This script:
# 1. Creates a PBS verify job for the main datastore
# 2. Optionally creates verify job for external datastore
# 3. Configures weekly schedule
#
# Why verify jobs matter:
# - Detects bit rot and corruption before you need the backup
# - Validates all backup chunks are intact
# - Alerts on corrupted backups via PBS notifications
#
# Run on: pumped-piglet.maas (where PBS LXC 103 is)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
PBS_LXC_ID=103
MAIN_DATASTORE="homelab-backup"
EXTERNAL_DATASTORE="external-hdd"
MAIN_VERIFY_JOB="weekly-verify"
EXTERNAL_VERIFY_JOB="external-verify"
SCHEDULE="sat 03:00"  # Weekly on Saturday at 3 AM

echo "========================================="
echo "PBS Verify Job Setup"
echo "========================================="
echo ""
echo "This creates PBS verify jobs to check backup integrity."
echo "Verify jobs read all backup chunks and validate checksums."
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

# List available datastores
echo "Available datastores:"
pct exec $PBS_LXC_ID -- proxmox-backup-manager datastore list
echo ""

# Function to create verify job
create_verify_job() {
    local DATASTORE=$1
    local JOB_ID=$2
    local JOB_SCHEDULE=$3

    # Check if datastore exists
    if ! pct exec $PBS_LXC_ID -- proxmox-backup-manager datastore list 2>/dev/null | grep -q "^$DATASTORE"; then
        echo "Datastore '$DATASTORE' not found, skipping..."
        return 1
    fi

    # Check if verify job already exists
    if pct exec $PBS_LXC_ID -- proxmox-backup-manager verify-job list 2>/dev/null | grep -q "^$JOB_ID"; then
        echo "Verify job '$JOB_ID' already exists for $DATASTORE"
        echo "Current configuration:"
        pct exec $PBS_LXC_ID -- proxmox-backup-manager verify-job show "$JOB_ID" 2>/dev/null || \
            pct exec $PBS_LXC_ID -- proxmox-backup-manager verify-job list | grep "$JOB_ID"
        echo ""
        read -p "Update existing verify job? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Keeping existing configuration."
            return 0
        fi
        # Remove existing job to recreate
        pct exec $PBS_LXC_ID -- proxmox-backup-manager verify-job remove "$JOB_ID"
        echo "Removed existing verify job"
    fi

    echo "Creating verify job '$JOB_ID' for $DATASTORE..."
    pct exec $PBS_LXC_ID -- proxmox-backup-manager verify-job create \
        "$JOB_ID" \
        --store "$DATASTORE" \
        --schedule "$JOB_SCHEDULE" \
        --comment "Weekly integrity verification for $DATASTORE"

    echo "Verify job created successfully"
    return 0
}

# Create verify job for main datastore
echo "Setting up verify job for main datastore..."
echo ""
create_verify_job "$MAIN_DATASTORE" "$MAIN_VERIFY_JOB" "$SCHEDULE"

# Check if external datastore exists and offer to create verify job
echo ""
if pct exec $PBS_LXC_ID -- proxmox-backup-manager datastore list 2>/dev/null | grep -q "^$EXTERNAL_DATASTORE"; then
    echo "External datastore '$EXTERNAL_DATASTORE' found."
    read -p "Create verify job for external datastore? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        # Schedule external verify on Sunday to avoid overlap
        EXTERNAL_SCHEDULE="sun 03:00"
        create_verify_job "$EXTERNAL_DATASTORE" "$EXTERNAL_VERIFY_JOB" "$EXTERNAL_SCHEDULE"
    fi
else
    echo "External datastore '$EXTERNAL_DATASTORE' not found."
    echo "Run setup-pbs-external-datastore.sh first if you want external backup."
fi

# List all verify jobs
echo ""
echo "Current verify jobs:"
pct exec $PBS_LXC_ID -- proxmox-backup-manager verify-job list

# Offer to run verification now
echo ""
read -p "Run verification now on $MAIN_DATASTORE? This may take a while. [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Starting verification..."
    echo "You can monitor progress in PBS Web UI: https://192.168.4.218:8007"
    echo ""

    # Run verify directly on datastore
    pct exec $PBS_LXC_ID -- proxmox-backup-manager verify "$MAIN_DATASTORE" &
    VERIFY_PID=$!
    echo "Verification started in background (PID: $VERIFY_PID)"
    echo ""
    echo "To monitor:"
    echo "  pct exec $PBS_LXC_ID -- proxmox-backup-manager task list"
fi

echo ""
echo "========================================="
echo "Setup Complete"
echo "========================================="
echo ""
echo "Verify jobs configured:"
echo ""
echo "  $MAIN_VERIFY_JOB:"
echo "    Datastore: $MAIN_DATASTORE"
echo "    Schedule: $SCHEDULE"
echo ""
if pct exec $PBS_LXC_ID -- proxmox-backup-manager verify-job list 2>/dev/null | grep -q "^$EXTERNAL_VERIFY_JOB"; then
    echo "  $EXTERNAL_VERIFY_JOB:"
    echo "    Datastore: $EXTERNAL_DATASTORE"
    echo "    Schedule: sun 03:00"
    echo ""
fi
echo "Commands:"
echo "  Run verify:      pct exec $PBS_LXC_ID -- proxmox-backup-manager verify $MAIN_DATASTORE"
echo "  List jobs:       pct exec $PBS_LXC_ID -- proxmox-backup-manager verify-job list"
echo "  View tasks:      pct exec $PBS_LXC_ID -- proxmox-backup-manager task list"
echo ""
echo "Verify checks:"
echo "  - Validates all chunk checksums"
echo "  - Detects bit rot and corruption"
echo "  - Alerts via PBS notification system"
echo ""
echo "PBS Web UI: https://192.168.4.218:8007"
