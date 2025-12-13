#!/bin/bash
# 99-validate-deliverables.sh
# Validates all deliverables meet architectural and security constraints
# Run this BEFORE committing to ensure compliance

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

PASS=0
FAIL=0

check() {
    local name="$1"
    local result="$2"
    if [[ "$result" == "pass" ]]; then
        echo -e "${GREEN}✓${NC} $name"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗${NC} $name"
        FAIL=$((FAIL + 1))
    fi
}

echo "========================================="
echo "Validating HA DNS Homelab Deliverables"
echo "========================================="
echo ""

# 1. Check required files exist
echo "--- File Existence ---"
[[ -f "$SCRIPT_DIR/README.md" ]] && check "README.md exists" "pass" || check "README.md exists" "fail"
[[ -f "$SCRIPT_DIR/00-diagnose-dns-chain.sh" ]] && check "00-diagnose-dns-chain.sh exists" "pass" || check "00-diagnose-dns-chain.sh exists" "fail"
[[ -f "$SCRIPT_DIR/01-test-ha-can-reach-frigate.sh" ]] && check "01-test-ha-can-reach-frigate.sh exists" "pass" || check "01-test-ha-can-reach-frigate.sh exists" "fail"
[[ -f "$SCRIPT_DIR/02-print-opnsense-dns-fix-steps.sh" ]] && check "02-print-opnsense-dns-fix-steps.sh exists" "pass" || check "02-print-opnsense-dns-fix-steps.sh exists" "fail"
[[ -f "$SCRIPT_DIR/03-print-ha-nmcli-fix-commands.sh" ]] && check "03-print-ha-nmcli-fix-commands.sh exists" "pass" || check "03-print-ha-nmcli-fix-commands.sh exists" "fail"
[[ -f "$SCRIPT_DIR/04-verify-frigate-app-homelab-works.sh" ]] && check "04-verify-frigate-app-homelab-works.sh exists" "pass" || check "04-verify-frigate-app-homelab-works.sh exists" "fail"
[[ -f "$SCRIPT_DIR/TEMPLATE-action-log-ha-dns-fix.md" ]] && check "Action log template exists" "pass" || check "Action log template exists" "fail"
[[ -f "$REPO_ROOT/docs/troubleshooting/blueprint-ha-dns-homelab-resolution.md" ]] && check "Blueprint exists" "pass" || check "Blueprint exists" "fail"
echo ""

# 2. Check for secrets/credentials in files
echo "--- Security: No Hardcoded Secrets ---"
# Look for actual secret values (e.g., "password=xxx", "Bearer xxx", JWT tokens starting with eyJ)
# Exclude: instructional text, variable names, documentation
FOUND_SECRETS=""
for f in "$SCRIPT_DIR"/*.sh "$SCRIPT_DIR"/*.md; do
    if [[ -f "$f" ]]; then
        BASENAME=$(basename "$f")
        # Skip the validation script itself
        if [[ "$BASENAME" == "99-validate-deliverables.sh" ]]; then
            continue
        fi
        # Look for actual hardcoded secrets (values, not mentions)
        # Pattern: look for assignment patterns like password=value, Bearer token, or JWT
        if grep -E "(password|secret|apikey|api_key)=['\"]?[a-zA-Z0-9]" "$f" 2>/dev/null | grep -vE '\.env|ENV_FILE|\$' | grep -q .; then
            FOUND_SECRETS="$FOUND_SECRETS $BASENAME"
        elif grep -E "Bearer [a-zA-Z0-9]" "$f" 2>/dev/null | grep -vE '\$|HA_TOKEN' | grep -q .; then
            FOUND_SECRETS="$FOUND_SECRETS $BASENAME"
        elif grep -E "eyJ[a-zA-Z0-9_-]{10,}" "$f" 2>/dev/null | grep -q .; then
            FOUND_SECRETS="$FOUND_SECRETS $BASENAME"
        fi
    fi
done
if [[ -z "$FOUND_SECRETS" ]]; then
    check "No hardcoded secrets in scripts/docs" "pass"
else
    check "No hardcoded secrets in scripts/docs (check:$FOUND_SECRETS)" "fail"
fi
echo ""

# 3. Check line endings (LF not CRLF)
echo "--- Line Endings (LF not CRLF) ---"
CRLF_FILES=""
for f in "$SCRIPT_DIR"/*.sh; do
    if [[ -f "$f" ]]; then
        if file "$f" | grep -q "CRLF"; then
            CRLF_FILES="$CRLF_FILES $(basename "$f")"
        fi
    fi
done
if [[ -z "$CRLF_FILES" ]]; then
    check "All .sh files have LF line endings" "pass"
else
    check "All .sh files have LF line endings (CRLF found:$CRLF_FILES)" "fail"
fi
echo ""

# 4. Check scripts source from .env (for those that need tokens)
echo "--- Scripts Source from .env ---"
for f in "$SCRIPT_DIR"/0*.sh; do
    if [[ -f "$f" ]]; then
        BASENAME=$(basename "$f")
        if grep -q "HA_TOKEN" "$f"; then
            # Script uses HA_TOKEN, check it sources from ENV_FILE
            if grep -q "ENV_FILE" "$f"; then
                check "$BASENAME sources HA_TOKEN from .env" "pass"
            else
                check "$BASENAME sources HA_TOKEN from .env" "fail"
            fi
        else
            check "$BASENAME doesn't need HA_TOKEN" "pass"
        fi
    fi
done
echo ""

# 5. Check scripts are executable (have shebang)
echo "--- Script Headers ---"
for f in "$SCRIPT_DIR"/*.sh; do
    if [[ -f "$f" ]]; then
        BASENAME=$(basename "$f")
        if head -1 "$f" | grep -q "^#!/bin/bash"; then
            check "$BASENAME has bash shebang" "pass"
        else
            check "$BASENAME has bash shebang" "fail"
        fi
    fi
done
echo ""

# 6. Summary
echo "========================================="
echo "Summary: $PASS passed, $FAIL failed"
echo "========================================="
if [[ $FAIL -gt 0 ]]; then
    echo -e "${RED}VALIDATION FAILED - Fix issues before commit${NC}"
    exit 1
else
    echo -e "${GREEN}ALL CHECKS PASSED${NC}"
    exit 0
fi
