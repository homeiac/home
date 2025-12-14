#!/bin/bash
# Index all shell scripts into OpenMemory for discovery and dedup detection
# Usage: ./index-scripts.sh [--dry-run]

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DRY_RUN="${1:-}"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[INDEX]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; }

# Determine category from path
get_category() {
    local path="$1"
    case "$path" in
        */homelab/src/*)     echo "cat:product" ;;
        */frigate-coral-lxc/*) echo "cat:migration" ;;
        */virtiofs-import/*) echo "cat:migration" ;;
        */still-fawn-coral/*) echo "cat:migration" ;;
        */pumped-piglet-coral/*) echo "cat:migration" ;;
        */package-detection/*) echo "cat:helper" ;;
        */voice-pe-debug/*) echo "cat:helper" ;;
        *test*.sh)           echo "cat:helper" ;;
        *debug*.sh)          echo "cat:helper" ;;
        *)                   echo "cat:ops" ;;
    esac
}

# Determine component from path
get_component() {
    local path="$1"
    case "$path" in
        */k3s/*)        echo "k3s" ;;
        */haos/*)       echo "haos" ;;
        */frigate/*)    echo "frigate" ;;
        */coral*)       echo "coral" ;;
        */proxmox/*)    echo "proxmox" ;;
        */ollama*)      echo "ollama" ;;
        */openmemory/*) echo "openmemory" ;;
        *)              echo "infra" ;;
    esac
}

# Determine purpose from filename
get_purpose() {
    local name="$1"
    case "$name" in
        exec*.sh)       echo "purpose:exec" ;;
        diagnose*.sh)   echo "purpose:diagnose" ;;
        check*.sh)      echo "purpose:verify" ;;
        verify*.sh)     echo "purpose:verify" ;;
        test*.sh)       echo "purpose:test" ;;
        deploy*.sh)     echo "purpose:deploy" ;;
        setup*.sh)      echo "purpose:deploy" ;;
        install*.sh)    echo "purpose:deploy" ;;
        backup*.sh)     echo "purpose:backup" ;;
        restore*.sh)    echo "purpose:backup" ;;
        debug*.sh)      echo "purpose:diagnose" ;;
        *)              echo "purpose:util" ;;
    esac
}

# Extract purpose from script comments
extract_purpose() {
    local file="$1"
    # Get first comment line after shebang (macOS compatible)
    local purpose=$(awk 'NR>=2 && NR<=5 && /^#/ {sub(/^# */, ""); print; exit}' "$file")
    if [[ -z "$purpose" ]]; then
        purpose="$(basename "$file" .sh)"
    fi
    echo "$purpose"
}

# Extract usage from script
extract_usage() {
    local file="$1"
    grep -i "^# Usage:" "$file" 2>/dev/null | head -1 | sed 's/^# Usage: *//' || echo ""
}

# Index a single script
index_script() {
    local file="$1"
    local rel_path="${file#$REPO_ROOT/}"
    local name=$(basename "$file")

    local category=$(get_category "$rel_path")
    local component=$(get_component "$rel_path")
    local purpose_tag=$(get_purpose "$name")
    local description=$(extract_purpose "$file")
    local usage=$(extract_usage "$file")

    # Build content
    local content="SCRIPT: $rel_path
PURPOSE: $description
USAGE: ${usage:-./$(basename "$file")}
COMPONENT: $component
CATEGORY: ${category#cat:}"

    # Build tags
    local tags="script,$category,$component,$purpose_tag"

    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log "Would index: $rel_path"
        echo "  Content: $content" | head -2
        echo "  Tags: $tags"
        return
    fi

    # Store in OpenMemory
    opm add "$content" --tags "$tags" 2>/dev/null && log "Indexed: $rel_path" || warn "Failed: $rel_path"
}

main() {
    log "Starting script indexing from $REPO_ROOT"
    [[ "$DRY_RUN" == "--dry-run" ]] && warn "DRY RUN MODE - no changes will be made"

    local count=0
    local indexed=0

    # Find all shell scripts, excluding node_modules and .git
    while IFS= read -r file; do
        ((count++))
        index_script "$file"
        ((indexed++))

        # Rate limit to avoid overwhelming OpenMemory
        [[ "$DRY_RUN" != "--dry-run" ]] && sleep 0.1

    done < <(find "$REPO_ROOT/scripts" -name "*.sh" -type f ! -path "*/node_modules/*" | sort)

    log "Done. Found $count scripts, indexed $indexed"
}

main "$@"
