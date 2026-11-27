#!/usr/bin/env bash
# Save an Immich database backup before pet metadata writes; never store in Git.
set -euo pipefail
umask 077
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
dest="${1:?Usage: backup.sh /absolute/private/backup-directory}"
mkdir -p "$dest"
file="$dest/immich-before-pets-$(date -u +%Y%m%dT%H%M%SZ).dump"
kubectl -n immich-pilot exec deployment/immich-postgres -- \
  pg_dump -U immich -d immich -Fc > "$file"
test -s "$file"
pg_restore --list "$file" > "$file.contents"
# Fully decompress and parse the archive without connecting to any database.
pg_restore --file=/dev/null "$file"
echo "Verified database archive: $file ($(wc -c < "$file") bytes)"
