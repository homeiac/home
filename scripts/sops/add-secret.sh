#!/opt/homebrew/bin/bash
# add-secret.sh - Create and encrypt a new K8s secret via SOPS
#
# Generic runbook for adding any SOPS-encrypted secret to the GitOps repo.
# Generates the YAML, encrypts it, and tells you what to add to kustomization.yaml.
#
# Usage:
#   ./scripts/sops/add-secret.sh --name my-secret --namespace myapp key1=value1 key2=value2
#   echo "s3cr3t" | ./scripts/sops/add-secret.sh --name api-creds --namespace myapp token=-
#
# Options:
#   --name NAME         Secret name (required)
#   --namespace NS      Kubernetes namespace (required)
#   --output DIR        Output directory (default: gitops/clusters/homelab/apps/<namespace>/secrets/)
#   --filename FILE     Output filename (default: <name>.sops.yaml)
#   --force             Overwrite existing file
#
# Arguments:
#   key=value           Secret data as key=value pairs
#   key=-               Read value from stdin (only one key can use stdin)
#   key=@file           Read value from a file
#
# Examples:
#   # Simple key-value secret
#   ./scripts/sops/add-secret.sh --name db-creds --namespace postgres \
#       POSTGRES_USER=admin POSTGRES_PASSWORD=hunter2
#
#   # Read a token from stdin
#   gh auth token | ./scripts/sops/add-secret.sh --name gh-token --namespace myapp token=-
#
#   # Read a file (e.g., SSH key)
#   ./scripts/sops/add-secret.sh --name ssh-key --namespace myapp \
#       id_ed25519=@~/.ssh/id_ed25519 id_ed25519.pub=@~/.ssh/id_ed25519.pub
#
#   # Custom output location
#   ./scripts/sops/add-secret.sh --name api-key --namespace myapp \
#       --output gitops/clusters/homelab/infrastructure/myapp/secrets/ \
#       API_KEY=abc123
#
# Prerequisites:
#   - sops installed (brew install sops)
#   - age key at ~/.config/sops/age/keys.txt (run scripts/sops/setup-local-sops.sh)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENCRYPT_SCRIPT="$SCRIPT_DIR/encrypt-secret.sh"

# --- Parse arguments ---
SECRET_NAME=""
NAMESPACE=""
OUTPUT_DIR=""
FILENAME=""
FORCE=false
declare -a KV_PAIRS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name)
            SECRET_NAME="$2"
            shift 2
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --filename)
            FILENAME="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            awk 'NR>1 && /^#/{sub(/^# ?/,""); print} /^set -/{exit}' "$0"
            exit 0
            ;;
        -*)
            echo "ERROR: Unknown option: $1" >&2
            exit 1
            ;;
        *)
            KV_PAIRS+=("$1")
            shift
            ;;
    esac
done

# --- Validate required args ---
if [[ -z "$SECRET_NAME" ]]; then
    echo "ERROR: --name is required" >&2
    exit 1
fi

if [[ -z "$NAMESPACE" ]]; then
    echo "ERROR: --namespace is required" >&2
    exit 1
fi

if [[ ${#KV_PAIRS[@]} -eq 0 ]]; then
    echo "ERROR: At least one key=value pair is required" >&2
    exit 1
fi

# --- Defaults ---
if [[ -z "$OUTPUT_DIR" ]]; then
    OUTPUT_DIR="$REPO_ROOT/gitops/clusters/homelab/apps/$NAMESPACE/secrets"
fi

if [[ -z "$FILENAME" ]]; then
    FILENAME="${SECRET_NAME}.sops.yaml"
fi

SECRET_FILE="$OUTPUT_DIR/$FILENAME"

# --- Check for existing file ---
if [[ -f "$SECRET_FILE" ]] && [[ "$FORCE" != true ]]; then
    echo "ERROR: File already exists: $SECRET_FILE" >&2
    echo "       Use --force to overwrite, or 'sops $SECRET_FILE' to edit." >&2
    exit 1
fi

# --- Build stringData entries ---
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

STDIN_READ=false
STRING_DATA=""

for pair in "${KV_PAIRS[@]}"; do
    KEY="${pair%%=*}"
    RAW_VALUE="${pair#*=}"

    if [[ "$KEY" == "$pair" ]]; then
        echo "ERROR: Invalid format '$pair'. Use key=value, key=-, or key=@file" >&2
        exit 1
    fi

    if [[ "$RAW_VALUE" == "-" ]]; then
        # Read from stdin
        if [[ "$STDIN_READ" == true ]]; then
            echo "ERROR: Only one key can read from stdin (key=-)" >&2
            exit 1
        fi
        if [[ -t 0 ]]; then
            echo "ERROR: key=- expects piped stdin but stdin is a terminal" >&2
            exit 1
        fi
        RAW_VALUE=$(cat)
        STDIN_READ=true
    elif [[ "$RAW_VALUE" == @* ]]; then
        # Read from file
        FILE_PATH="${RAW_VALUE#@}"
        # Expand tilde
        FILE_PATH="${FILE_PATH/#\~/$HOME}"
        if [[ ! -f "$FILE_PATH" ]]; then
            echo "ERROR: File not found: $FILE_PATH" >&2
            exit 1
        fi
        RAW_VALUE=$(cat "$FILE_PATH")
    fi

    # Determine if value is multiline
    if [[ "$RAW_VALUE" == *$'\n'* ]]; then
        # Multiline: use YAML block scalar
        STRING_DATA+="  ${KEY}: |\n"
        while IFS= read -r line; do
            STRING_DATA+="    ${line}\n"
        done <<< "$RAW_VALUE"
    else
        # Single line: use quoted scalar
        STRING_DATA+="  ${KEY}: \"${RAW_VALUE}\"\n"
    fi
done

# --- Write plaintext YAML ---
PLAIN_FILE="$TMPDIR/secret.yaml"
printf '%s\n' "apiVersion: v1" \
              "kind: Secret" \
              "metadata:" \
              "  name: $SECRET_NAME" \
              "  namespace: $NAMESPACE" \
              "type: Opaque" \
              "stringData:" > "$PLAIN_FILE"
printf '%b' "$STRING_DATA" >> "$PLAIN_FILE"

# --- Encrypt ---
mkdir -p "$OUTPUT_DIR"
cp "$PLAIN_FILE" "$SECRET_FILE"
"$ENCRYPT_SCRIPT" "$SECRET_FILE" >&2

echo "" >&2
echo "Secret created: $SECRET_FILE" >&2
echo "" >&2

# --- Print next steps ---
# Compute relative path from repo root for kustomization.yaml reference
REL_PATH="${SECRET_FILE#$REPO_ROOT/gitops/clusters/homelab/apps/$NAMESPACE/}"
KUSTOMIZATION="$REPO_ROOT/gitops/clusters/homelab/apps/$NAMESPACE/kustomization.yaml"

echo "Next steps:" >&2
if [[ -f "$KUSTOMIZATION" ]]; then
    echo "  1. Add to $KUSTOMIZATION:" >&2
    echo "       - $REL_PATH" >&2
else
    echo "  1. Create a kustomization.yaml in the app directory and add:" >&2
    echo "       - $REL_PATH" >&2
fi
echo "  2. Commit: git add $SECRET_FILE && git commit -m 'feat: add $SECRET_NAME secret'" >&2
echo "  3. Push and reconcile: git push && flux reconcile kustomization flux-system --with-source" >&2
echo "" >&2
echo "To edit later: sops $SECRET_FILE" >&2
echo "To view:       sops --decrypt $SECRET_FILE" >&2

# Output the file path to stdout (for piping)
echo "$SECRET_FILE"
