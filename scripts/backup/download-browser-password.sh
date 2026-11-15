#!/bin/bash
# Copy the download browser's login password to the clipboard (never printed)
#
# Usage: ./download-browser-password.sh
#
# Decrypts gitops/clusters/homelab/apps/cloud-backup/secrets/download-browser-auth.sops.yaml
# with the local age key. Prints the username; the password goes to the clipboard (pbcopy on
# macOS, wl-copy / xclip on Linux).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SECRET_FILE="$REPO_ROOT/gitops/clusters/homelab/apps/cloud-backup/secrets/download-browser-auth.sops.yaml"
export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"

if   command -v pbcopy  >/dev/null; then CLIP=(pbcopy)
elif command -v wl-copy >/dev/null; then CLIP=(wl-copy)
elif command -v xclip   >/dev/null; then CLIP=(xclip -selection clipboard)
else echo "ERROR: no clipboard tool (pbcopy / wl-copy / xclip)" >&2; exit 1; fi

echo "User: $(sops -d --extract '["stringData"]["username"]' "$SECRET_FILE")"
sops -d --extract '["stringData"]["password"]' "$SECRET_FILE" | tr -d '\n' | "${CLIP[@]}"
echo "Password copied to the clipboard."
