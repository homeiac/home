#!/bin/bash
# 22-exclude-scsi1-from-backup.sh - Exclude unused 18TB disk from VM 105 backups
#
# Problem: VM 105 has scsi1 (18TB USB disk) attached but not used
#          PBS backups scan the entire disk, taking hours
#
# Solution: Set backup=0 on scsi1 to exclude from backups
#
# Prerequisites:
#   - Must cancel running backup first (VM is locked during backup)
#   - Or wait for backup to complete

set -e

HOST="pumped-piglet.maas"
VMID=105

echo "========================================="
echo "Exclude scsi1 from VM $VMID Backups"
echo "========================================="
echo ""

# Step 1: Check current state
echo "Step 1: Checking current VM config..."
ssh root@$HOST "qm config $VMID | grep -E 'scsi|lock|backup'" 2>/dev/null
echo ""

# Step 2: Check if VM is locked
echo "Step 2: Checking if VM is locked..."
LOCK=$(ssh root@$HOST "qm config $VMID | grep '^lock:'" 2>/dev/null || echo "")
if [ -n "$LOCK" ]; then
    echo "  VM is locked: $LOCK"
    echo ""
    echo "  Need to cancel backup first..."

    # Step 3: Cancel backup
    echo "Step 3: Cancelling backup..."
    ssh root@$HOST "pkill -f 'vzdump.*$VMID' && echo '  Killed vzdump process' || echo '  No vzdump process found'"
    sleep 2

    # Step 4: Unlock VM
    echo "Step 4: Unlocking VM..."
    ssh root@$HOST "qm unlock $VMID && echo '  VM unlocked' || echo '  Failed to unlock (may already be unlocked)'"
    sleep 1
else
    echo "  VM is not locked"
fi
echo ""

# Step 5: Apply backup=0 to scsi1
echo "Step 5: Setting backup=0 on scsi1..."
ssh root@$HOST "qm set $VMID --scsi1 local-20TB-zfs:vm-105-disk-0,cache=writeback,iothread=1,backup=0"
echo ""

# Step 6: Verify change
echo "Step 6: Verifying change..."
ssh root@$HOST "qm config $VMID | grep scsi1"
echo ""

# Step 7: Check I/O
echo "Step 7: Checking I/O (should drop significantly)..."
sleep 5
ssh root@$HOST "zpool iostat local-20TB-zfs 2 3" 2>/dev/null | tail -4
echo ""

# Step 8: Check load
echo "Step 8: Checking host load..."
ssh root@$HOST "uptime" 2>/dev/null
echo ""

echo "========================================="
echo "Done! scsi1 excluded from backups."
echo "========================================="
echo ""
echo "Future backups will skip the 18TB USB disk."
echo "Backup time should be 2-3 minutes instead of hours."
