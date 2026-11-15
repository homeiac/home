#!/bin/bash
# Create the SOPS-encrypted basic-auth Secret for the download browser (design §5.4)
#
# Usage: ./download-browser-create-secret.sh [--force]
#
# Generates a random password (never printed), writes the K8s Secret
# gitops/clusters/homelab/apps/cloud-backup/secrets/download-browser-auth.sops.yaml
# and encrypts it in place with scripts/sops/encrypt-secret.sh. Commit the encrypted file;
# Flux decrypts it. Get the password later with download-browser-password.sh (copies to clipboard).
#   DOWNLOAD_BROWSER_USER   login name (default: backup)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SECRET_FILE="$REPO_ROOT/gitops/clusters/homelab/apps/cloud-backup/secrets/download-browser-auth.sops.yaml"
USER_NAME="${DOWNLOAD_BROWSER_USER:-backup}"

if [[ -f "$SECRET_FILE" && "${1:-}" != "--force" ]]; then
  echo "ERROR: $SECRET_FILE exists. Use --force to replace (changes the password)." >&2
  exit 1
fi
command -v sops >/dev/null || { echo "ERROR: sops not installed (brew install sops)" >&2; exit 1; }

mkdir -p "$(dirname "$SECRET_FILE")"
PASS="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
umask 077
# Plain text exists only until the encrypt step below; removed if that step fails.
trap 'grep -q "ENC\[AES256_GCM" "$SECRET_FILE" 2>/dev/null || rm -f "$SECRET_FILE"' EXIT
cat > "$SECRET_FILE" <<YAML
apiVersion: v1
kind: Secret
metadata:
  name: download-browser-auth
  namespace: cloud-backup
type: Opaque
stringData:
  username: $USER_NAME
  password: $PASS
YAML
unset PASS
"$REPO_ROOT/scripts/sops/encrypt-secret.sh" "$SECRET_FILE" >/dev/null
grep -q "ENC\[AES256_GCM" "$SECRET_FILE" || { echo "ERROR: encryption failed" >&2; exit 1; }
echo "Encrypted secret written: ${SECRET_FILE#$REPO_ROOT/} (user: $USER_NAME)"
