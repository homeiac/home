#!/bin/bash
#
# Backup Claude Code session logs to SMB share
#
# Sources:
#   - Mac local: ~/.claude/projects/
#   - claudecodeui pods: via kubectl cp
#
# Target: /Volumes/secure/claude-sessions/
#
set -euo pipefail

# Configuration
SMB_MOUNT="/Volumes/secure"
BACKUP_BASE="$SMB_MOUNT/claude-sessions"
MAC_PROJECTS_BASE="$HOME/.claude/projects"
KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"

# Default options
SOURCE="all"
REPO="all"
DRY_RUN=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Backup Claude Code session logs to SMB share.

Options:
    --source mac|k8s|all    Source to backup (default: all)
    --repo home|chorus|devops|all  Repo to backup (default: all)
    --dry-run               Show what would be copied
    -h, --help              Show this help

Examples:
    $(basename "$0")                     # Backup everything
    $(basename "$0") --source mac        # Only Mac local
    $(basename "$0") --repo home         # Only home repo
    $(basename "$0") --dry-run           # Dry run
EOF
}

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

check_smb_mount() {
    if [[ ! -d "$SMB_MOUNT" ]]; then
        log_error "SMB share not mounted at $SMB_MOUNT"
        log_info "Mount with: open 'smb://gshiva@192.168.4.120/secure'"
        exit 1
    fi
}

ensure_dirs() {
    local dirs=(
        "$BACKUP_BASE/source-mac-local/repo-home"
        "$BACKUP_BASE/source-mac-local/repo-chorus"
        "$BACKUP_BASE/source-mac-local/repo-the-road-to-devops"
        "$BACKUP_BASE/source-claudecodeui/repo-home"
        "$BACKUP_BASE/source-claudecodeui-blue/repo-home"
    )
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            if [[ "$DRY_RUN" == "true" ]]; then
                log_info "[DRY-RUN] Would create: $dir"
            else
                mkdir -p "$dir"
                log_info "Created: $dir"
            fi
        fi
    done
}

backup_mac_local() {
    local repo="$1"
    local src_path=""
    local dst_path=""

    case "$repo" in
        home)
            src_path="$MAC_PROJECTS_BASE/-Users-10381054-code-home"
            dst_path="$BACKUP_BASE/source-mac-local/repo-home"
            ;;
        chorus)
            src_path="$MAC_PROJECTS_BASE/-Users-10381054-code-chorus"
            dst_path="$BACKUP_BASE/source-mac-local/repo-chorus"
            ;;
        devops)
            src_path="$MAC_PROJECTS_BASE/-Users-10381054-code-the-road-to-devops"
            dst_path="$BACKUP_BASE/source-mac-local/repo-the-road-to-devops"
            ;;
    esac

    if [[ ! -d "$src_path" ]]; then
        log_warn "Source not found: $src_path"
        return
    fi

    local file_count
    file_count=$(find "$src_path" -name "*.jsonl" 2>/dev/null | wc -l | tr -d ' ')

    if [[ "$file_count" -eq 0 ]]; then
        log_info "No .jsonl files in $src_path"
        return
    fi

    log_info "Backing up Mac local $repo ($file_count files)..."

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] rsync -av $src_path/*.jsonl $dst_path/"
    else
        rsync -av "$src_path"/*.jsonl "$dst_path/" 2>/dev/null || true
    fi
}

backup_k8s_pod() {
    local deployment="$1"  # claudecodeui or claudecodeui-blue
    local dst_subdir="$2"  # source-claudecodeui or source-claudecodeui-blue

    # Get pod name
    local pod
    pod=$(kubectl --kubeconfig="$KUBECONFIG" get pods -n claudecodeui -l "app=$deployment" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -z "$pod" ]]; then
        log_warn "No pod found for deployment $deployment"
        return
    fi

    log_info "Backing up K8s pod $pod..."

    # The pod has SMB mounted at /mnt/claude-sessions
    # We can exec into the pod and rsync directly
    local cmd="rsync -av /home/claude/.claude/projects/-home-claude-projects-home/*.jsonl /mnt/claude-sessions/$dst_subdir/repo-home/ 2>/dev/null || true"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] kubectl exec -n claudecodeui $pod -- sh -c '$cmd'"
    else
        kubectl --kubeconfig="$KUBECONFIG" exec -n claudecodeui "$pod" -- sh -c "$cmd" || log_warn "Backup from $pod failed (pod may not have SMB mounted yet)"
    fi
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --source)
            SOURCE="$2"
            shift 2
            ;;
        --repo)
            REPO="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate options
if [[ ! "$SOURCE" =~ ^(mac|k8s|all)$ ]]; then
    log_error "Invalid source: $SOURCE"
    exit 1
fi

if [[ ! "$REPO" =~ ^(home|chorus|devops|all)$ ]]; then
    log_error "Invalid repo: $REPO"
    exit 1
fi

# Main
log_info "Claude Session Logs Backup"
log_info "Source: $SOURCE, Repo: $REPO, Dry-run: $DRY_RUN"

check_smb_mount
ensure_dirs

# Backup Mac local
if [[ "$SOURCE" == "mac" || "$SOURCE" == "all" ]]; then
    log_info "=== Mac Local Backup ==="
    if [[ "$REPO" == "all" ]]; then
        backup_mac_local "home"
        backup_mac_local "chorus"
        backup_mac_local "devops"
    else
        backup_mac_local "$REPO"
    fi
fi

# Backup K8s pods
if [[ "$SOURCE" == "k8s" || "$SOURCE" == "all" ]]; then
    log_info "=== K8s Pod Backup ==="

    # Check kubectl access
    if ! kubectl --kubeconfig="$KUBECONFIG" get ns claudecodeui &>/dev/null; then
        log_warn "Cannot access K8s cluster. Skipping K8s backup."
    else
        backup_k8s_pod "claudecodeui" "source-claudecodeui"
        backup_k8s_pod "claudecodeui-blue" "source-claudecodeui-blue"
    fi
fi

log_info "=== Backup Complete ==="
log_info "Files backed up to: $BACKUP_BASE"

# Summary
if [[ "$DRY_RUN" == "false" ]]; then
    log_info "Summary:"
    for dir in "$BACKUP_BASE"/source-*/repo-*; do
        if [[ -d "$dir" ]]; then
            count=$(find "$dir" -name "*.jsonl" 2>/dev/null | wc -l | tr -d ' ')
            log_info "  $(basename "$(dirname "$dir")")/$(basename "$dir"): $count files"
        fi
    done
fi
