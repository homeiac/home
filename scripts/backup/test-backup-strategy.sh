#!/bin/bash
# Test backup strategy components
# Safe to run - no destructive operations
#
# Usage: ./test-backup-strategy.sh [--full]
#   --full: Include Level 3 component tests (requires infrastructure access)

# Don't use set -e as we want to continue on test failures
# set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECTL="${KUBECTL:-kubectl}"
FULL_TEST=false

if [[ "$1" == "--full" ]]; then
    FULL_TEST=true
fi

echo "========================================="
echo "Backup Strategy Test Suite"
echo "========================================="
echo ""

PASS=0
FAIL=0
SKIP=0

# Helper functions
pass() { echo "   ✓ $1"; ((PASS++)); }
fail() { echo "   ✗ $1"; ((FAIL++)); }
skip() { echo "   - $1 (skipped)"; ((SKIP++)); }

# ===========================================
# Level 1: Script Validation
# ===========================================
echo "Level 1: Script Syntax Validation"
echo "-----------------------------------------"

for script in "$SCRIPT_DIR"/*.sh; do
    name=$(basename "$script")
    if [[ "$name" == "test-backup-strategy.sh" ]]; then
        continue
    fi
    if bash -n "$script" 2>/dev/null; then
        pass "$name"
    else
        fail "$name - syntax error"
    fi
done

# Check shellcheck if available
echo ""
if command -v shellcheck &>/dev/null; then
    echo "Running shellcheck..."
    shellcheck_errors=0
    for script in "$SCRIPT_DIR"/*.sh; do
        if ! shellcheck -S warning "$script" 2>/dev/null; then
            ((shellcheck_errors++))
        fi
    done
    if [[ $shellcheck_errors -eq 0 ]]; then
        pass "shellcheck passed"
    else
        fail "shellcheck found issues in $shellcheck_errors scripts"
    fi
else
    skip "shellcheck not installed"
fi

# ===========================================
# Level 2: Connectivity & Prerequisites
# ===========================================
echo ""
echo "Level 2: Connectivity & Prerequisites"
echo "-----------------------------------------"

# Check kubectl
if command -v "$KUBECTL" &>/dev/null; then
    pass "kubectl available"
else
    fail "kubectl not found"
fi

# Check kubectl cluster access
if $KUBECTL cluster-info &>/dev/null; then
    pass "kubectl cluster access"
else
    fail "kubectl cannot access cluster"
fi

# Check SSH to pumped-piglet
if ssh -o ConnectTimeout=5 -o BatchMode=yes root@pumped-piglet.maas "echo ok" &>/dev/null; then
    pass "SSH to pumped-piglet.maas"
else
    fail "Cannot SSH to pumped-piglet.maas"
fi

# Check PBS container
if ssh -o ConnectTimeout=5 root@pumped-piglet.maas "pct status 103" &>/dev/null; then
    pass "PBS container (LXC 103) running"
else
    fail "PBS container (LXC 103) not accessible"
fi

# Check rclone
if command -v rclone &>/dev/null; then
    pass "rclone installed"
    # Check if gdrive-backup remote exists
    if rclone listremotes 2>/dev/null | grep -q "gdrive-backup:"; then
        pass "rclone gdrive-backup remote configured"
    else
        skip "rclone gdrive-backup remote not configured"
    fi
else
    skip "rclone not installed"
fi

# ===========================================
# Level 3: Component Tests (if --full)
# ===========================================
if [[ "$FULL_TEST" == "true" ]]; then
    echo ""
    echo "Level 3: Component Tests"
    echo "-----------------------------------------"

    # Test 3.1: PostgreSQL backup PVC
    echo ""
    echo "3.1 PostgreSQL Backup PVC..."
    if $KUBECTL get pvc postgres-backup -n database &>/dev/null; then
        pass "postgres-backup PVC exists"
    else
        fail "postgres-backup PVC not found"
    fi

    # Test 3.2: PostgreSQL backup CronJob
    echo ""
    echo "3.2 PostgreSQL Backup CronJob..."
    if $KUBECTL get cronjob postgres-backup -n database &>/dev/null; then
        pass "postgres-backup CronJob exists"

        # Check last successful job
        LAST_SUCCESS=$($KUBECTL get cronjob postgres-backup -n database -o jsonpath='{.status.lastSuccessfulTime}' 2>/dev/null || echo "")
        if [[ -n "$LAST_SUCCESS" ]]; then
            pass "Last successful backup: $LAST_SUCCESS"
        else
            skip "No successful backup recorded yet"
        fi
    else
        fail "postgres-backup CronJob not found"
    fi

    # Test 3.3: Check backup files exist (using temporary pod to access PVC)
    echo ""
    echo "3.3 PostgreSQL Backup Files..."
    # The backup PVC is not mounted on the main postgres pod, so we use a temp pod
    BACKUP_FILES=$($KUBECTL run backup-check-$$ --rm -i --restart=Never \
        --image=busybox \
        -n database \
        --overrides='{"spec":{"containers":[{"name":"check","image":"busybox","command":["ls","-1","/backup"],"volumeMounts":[{"name":"backup","mountPath":"/backup"}]}],"volumes":[{"name":"backup","persistentVolumeClaim":{"claimName":"postgres-backup"}}]}}' 2>/dev/null || echo "")
    BACKUP_COUNT=$(echo "$BACKUP_FILES" | grep -c "pg_dumpall" 2>/dev/null || echo "0")
    if [[ "$BACKUP_COUNT" -gt 0 ]]; then
        pass "Found $BACKUP_COUNT backup file(s)"
        LATEST=$(echo "$BACKUP_FILES" | grep "pg_dumpall" | sort -r | head -1)
        echo "      Latest: $LATEST"
    else
        fail "No backup files found in /backup/"
    fi

    # Test 3.4: PBS datastore status
    echo ""
    echo "3.4 PBS Datastore Status..."
    PBS_DATASTORES=$(ssh root@pumped-piglet.maas "pct exec 103 -- proxmox-backup-manager datastore list" 2>/dev/null || echo "")
    if echo "$PBS_DATASTORES" | grep -q "homelab-backup"; then
        pass "homelab-backup datastore exists"
    else
        fail "homelab-backup datastore not found"
    fi

    if echo "$PBS_DATASTORES" | grep -q "external-hdd"; then
        pass "external-hdd datastore exists"
    else
        skip "external-hdd datastore not configured yet"
    fi

    # Test 3.5: PBS backup count
    echo ""
    echo "3.5 PBS Backup Inventory..."
    PBS_BACKUP_COUNT=$(ssh root@pumped-piglet.maas "pvesm list homelab-backup 2>/dev/null | wc -l" || echo "0")
    if [[ "$PBS_BACKUP_COUNT" -gt 1 ]]; then
        pass "Found $((PBS_BACKUP_COUNT - 1)) backups in PBS"
    else
        fail "No backups found in PBS"
    fi

    # Test 3.6: Google Drive sync (if configured)
    echo ""
    echo "3.6 Google Drive Status..."
    if command -v rclone &>/dev/null && rclone listremotes 2>/dev/null | grep -q "gdrive-backup:"; then
        GDRIVE_FILES=$(rclone ls gdrive-backup:homelab-backup/postgres/ 2>/dev/null | wc -l || echo "0")
        if [[ "$GDRIVE_FILES" -gt 0 ]]; then
            pass "Found $GDRIVE_FILES file(s) on Google Drive"
        else
            skip "Google Drive backup folder empty"
        fi
    else
        skip "Google Drive not configured"
    fi
else
    echo ""
    echo "Level 3: Component Tests (skipped)"
    echo "-----------------------------------------"
    echo "   Run with --full to include component tests"
fi

# ===========================================
# Summary
# ===========================================
echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="
echo "  Passed:  $PASS"
echo "  Failed:  $FAIL"
echo "  Skipped: $SKIP"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
    echo "Status: SOME TESTS FAILED"
    exit 1
else
    echo "Status: ALL TESTS PASSED"
    exit 0
fi
