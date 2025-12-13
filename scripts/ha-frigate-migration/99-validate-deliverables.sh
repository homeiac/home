#!/bin/bash
#
# 99-validate-deliverables.sh
#
# Validates that all HA Frigate IP migration deliverables exist
# and meet architectural/security constraints
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "========================================="
echo "HA Frigate IP Migration Deliverables Check"
echo "========================================="
echo ""

PASS=0
FAIL=0

check_file() {
    local path="$1"
    local desc="$2"
    if [[ -f "$REPO_ROOT/$path" ]]; then
        echo "PASS: $desc"
        echo "      $path"
        PASS=$((PASS+1))
    else
        echo "FAIL: $desc"
        echo "      Missing: $path"
        FAIL=$((FAIL+1))
    fi
}

check_no_secrets() {
    local path="$1"
    if [[ -f "$REPO_ROOT/$path" ]]; then
        if grep -qiE "password|secret|token|apikey" "$REPO_ROOT/$path" 2>/dev/null; then
            echo "WARN: $path may contain secrets - review required"
        else
            echo "PASS: No secrets in $path"
            PASS=$((PASS+1))
        fi
    fi
}

echo "--- Deliverable Files ---"
check_file "docs/troubleshooting/blueprint-ha-frigate-ip-migration.md" "Blueprint"
check_file "docs/templates/action-log-template-ha-frigate-ip-migration.md" "Action Log Template"
check_file "docs/troubleshooting/2025-12-13-action-log-ha-frigate-ip-migration.md" "Action Log Instance"
check_file "scripts/ha-frigate-migration/99-validate-deliverables.sh" "Validation Script"
echo ""

echo "--- Security Checks ---"
check_no_secrets "docs/troubleshooting/blueprint-ha-frigate-ip-migration.md"
check_no_secrets "docs/templates/action-log-template-ha-frigate-ip-migration.md"
check_no_secrets "scripts/ha-frigate-migration/99-validate-deliverables.sh"
echo ""

echo "--- Existing Scripts Check ---"
check_file "scripts/frigate/update-ha-frigate-url.sh" "Migration Script"
check_file "scripts/ha-frigate-migration/rollback-ha-frigate-url.sh" "Rollback Script"
check_file "scripts/frigate/check-ha-frigate-integration.sh" "Verification Script"
echo ""

echo "========================================="
echo "Summary: $PASS passed, $FAIL failed"
echo "========================================="

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit 0
