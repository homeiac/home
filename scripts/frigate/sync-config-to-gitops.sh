#!/bin/bash
# Apply Frigate config changes via GitOps
#
# Source of Truth: gitops/clusters/homelab/apps/frigate/configmap.yaml
# On every pod restart, init container copies configmap → PVC config
#
# Workflow:
#   1. Edit configmap.yaml (or pull live config from pod)
#   2. Check for credentials (BLOCK if found)
#   3. Commit and push
#   4. Flux reconciles → pod restarts → new config applied
#
# Usage:
#   ./sync-config-to-gitops.sh                 # Pull live config → GitOps, commit, push, restart
#   ./sync-config-to-gitops.sh --dry-run       # Show diff only
#   ./sync-config-to-gitops.sh --push-only     # Just commit current configmap and push
#   ./sync-config-to-gitops.sh --rollback      # Revert to previous commit and restart
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIGMAP_PATH="$REPO_ROOT/gitops/clusters/homelab/apps/frigate/configmap.yaml"
NAMESPACE="frigate"
POD_CONFIG_PATH="/config/config.yml"

export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

DRY_RUN=false
ROLLBACK=false
PUSH_ONLY=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --rollback) ROLLBACK=true; shift ;;
        --push-only) PUSH_ONLY=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

get_pod() {
    kubectl get pods -n "$NAMESPACE" -l app=frigate -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

check_for_credentials() {
    local file="$1"
    local found=false

    local patterns=(
        'rtsp://[^{][^:]*:[^@{]+@'
        'http://[^{][^:]*:[^@{]+@'
        'password=[^{]'
    )

    echo "Checking for hardcoded credentials..."
    for pattern in "${patterns[@]}"; do
        if grep -qE "$pattern" "$file" 2>/dev/null; then
            echo -e "${RED}CREDENTIAL DETECTED!${NC}"
            grep -nE "$pattern" "$file" | head -3
            found=true
        fi
    done

    $found && return 1

    if ! grep -q '{FRIGATE_' "$file"; then
        echo -e "${YELLOW}WARNING: No credential placeholders found.${NC}"
        read -p "Continue? [y/N] " -n 1 -r; echo
        [[ ! $REPLY =~ ^[Yy]$ ]] && return 1
    fi

    echo -e "${GREEN}Credentials OK (using placeholders).${NC}"
    return 0
}

extract_config_from_configmap() {
    python3 -c "
import yaml
with open('$CONFIGMAP_PATH', 'r') as f:
    cm = yaml.safe_load(f)
print(cm['data']['config.yml'], end='')
"
}

update_configmap_with_config() {
    local new_config_file="$1"
    python3 << 'PYEOF'
import yaml

CONFIGMAP_PATH = """$CONFIGMAP_PATH"""
new_config_file = """$new_config_file"""

with open(CONFIGMAP_PATH, 'r') as f:
    cm = yaml.safe_load(f)

with open(new_config_file, 'r') as f:
    new_config = f.read()

cm['data']['config.yml'] = new_config

class LiteralDumper(yaml.SafeDumper):
    pass

def str_representer(dumper, data):
    if '\n' in data:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)

LiteralDumper.add_representer(str, str_representer)

with open(CONFIGMAP_PATH, 'w') as f:
    yaml.dump(cm, f, Dumper=LiteralDumper, default_flow_style=False, sort_keys=False)
PYEOF
}

restart_frigate() {
    echo ""
    echo "Triggering Flux reconciliation..."
    flux reconcile kustomization flux-system --with-source 2>/dev/null || true

    echo "Restarting Frigate deployment..."
    kubectl rollout restart deployment/frigate -n "$NAMESPACE"

    echo ""
    echo -e "${GREEN}Restart initiated.${NC}"
    echo "Monitor: kubectl get pods -n frigate -w"
    echo "Logs:    kubectl logs -n frigate -l app=frigate -f"
}

# Rollback
if $ROLLBACK; then
    echo "=== Frigate Config Rollback ==="
    cd "$REPO_ROOT"

    echo "Recent Frigate config commits:"
    git log --oneline -10 -- "$CONFIGMAP_PATH"
    echo ""

    PREV_COMMIT=$(git log --oneline -2 -- "$CONFIGMAP_PATH" | tail -1 | awk '{print $1}')
    [[ -z "$PREV_COMMIT" ]] && { echo "ERROR: No previous commit"; exit 1; }

    echo "Reverting to: $PREV_COMMIT"
    read -p "Proceed? [y/N] " -n 1 -r; echo
    [[ ! $REPLY =~ ^[Yy]$ ]] && exit 0

    git checkout "$PREV_COMMIT" -- "$CONFIGMAP_PATH"
    git add "$CONFIGMAP_PATH"
    git commit -m "revert(frigate): rollback config to $PREV_COMMIT

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
    git push

    restart_frigate
    exit 0
fi

# Push only (no pull from pod)
if $PUSH_ONLY; then
    echo "=== Push Frigate ConfigMap to GitOps ==="
    cd "$REPO_ROOT"

    if ! git diff --quiet "$CONFIGMAP_PATH" 2>/dev/null; then
        echo "Uncommitted changes in configmap:"
        git diff --stat "$CONFIGMAP_PATH"
    else
        echo "No uncommitted changes. Checking for unpushed commits..."
    fi

    # Check for credentials
    TEMP_CHECK=$(mktemp)
    trap "rm -f $TEMP_CHECK" EXIT
    extract_config_from_configmap > "$TEMP_CHECK"
    check_for_credentials "$TEMP_CHECK" || { echo "BLOCKED: Fix credentials first"; exit 1; }

    if ! git diff --quiet "$CONFIGMAP_PATH" 2>/dev/null; then
        git add "$CONFIGMAP_PATH"
        read -p "Commit message [fix(frigate): update config]: " MSG
        MSG="${MSG:-fix(frigate): update config}"
        git commit -m "$MSG

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
    fi

    git push
    restart_frigate
    exit 0
fi

# Main: Pull live config → GitOps → push → restart
echo "=== Sync Frigate Live Config → GitOps ==="
echo ""

POD=$(get_pod)
[[ -z "$POD" ]] && { echo "ERROR: No Frigate pod found"; exit 1; }
echo "Pod: $POD"

TEMP_LIVE=$(mktemp)
TEMP_GITOPS=$(mktemp)
trap "rm -f $TEMP_LIVE $TEMP_GITOPS" EXIT

echo "Downloading live config..."
kubectl exec -n "$NAMESPACE" "$POD" -- cat "$POD_CONFIG_PATH" > "$TEMP_LIVE"

echo ""
check_for_credentials "$TEMP_LIVE" || { echo -e "${RED}BLOCKED: Live config has hardcoded creds!${NC}"; exit 1; }

echo ""
echo "Comparing with GitOps..."
extract_config_from_configmap > "$TEMP_GITOPS"

if diff -q "$TEMP_GITOPS" "$TEMP_LIVE" > /dev/null 2>&1; then
    echo -e "${GREEN}Already in sync. Nothing to do.${NC}"
    exit 0
fi

echo ""
echo "Changes (GitOps current → Live):"
echo "----------------------------------------"
diff --color=auto "$TEMP_GITOPS" "$TEMP_LIVE" || true
echo "----------------------------------------"

$DRY_RUN && { echo -e "${YELLOW}DRY RUN: No changes.${NC}"; exit 0; }

echo ""
read -p "Sync live config to GitOps and restart Frigate? [y/N] " -n 1 -r; echo
[[ ! $REPLY =~ ^[Yy]$ ]] && exit 0

echo "Updating configmap..."
update_configmap_with_config "$TEMP_LIVE"

cd "$REPO_ROOT"
git add "$CONFIGMAP_PATH"

echo ""
read -p "Commit message [fix(frigate): sync config from live]: " MSG
MSG="${MSG:-fix(frigate): sync config from live}"

git commit -m "$MSG

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

git push

restart_frigate

echo ""
echo -e "${GREEN}=== Complete ===${NC}"
echo "Rollback: $0 --rollback"
