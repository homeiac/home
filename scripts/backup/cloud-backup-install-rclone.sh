#!/bin/bash
# Install a pinned, checksum-verified rclone on the cloud-backup host (pumped-piglet)
#
# Usage: ./cloud-backup-install-rclone.sh
#
# Uses the official rclone .deb, not Debian's package: Debian ships 1.60 (2022), which
# is too old for the current OneDrive API. Idempotent: does nothing if the pinned
# version is already installed.
# Design: docs/plans/cloud-drive-backup-and-reclaim.md (Phase 1)

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

echo "Host: $CB_HOST   rclone: $CB_RCLONE_VERSION"

cb_ssh "V='$CB_RCLONE_VERSION'" 'bash -s' <<'EOF'
set -euo pipefail
if command -v rclone >/dev/null && rclone version | head -1 | grep -q "rclone $V\$"; then
  echo "rclone $V already installed"
  exit 0
fi
F="rclone-$V-linux-amd64.deb"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
curl -fsSLO "https://downloads.rclone.org/$V/$F"
curl -fsSL "https://downloads.rclone.org/$V/SHA256SUMS" | grep " $F\$" | sha256sum -c -
dpkg -i "$F" >/dev/null
rclone version | head -1
EOF
