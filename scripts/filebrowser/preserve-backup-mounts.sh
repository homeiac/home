#!/usr/bin/env bash
# Apply only the mount arrangement; no FileBrowser update or password changes.
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ssh -o BatchMode=yes "root@${1:-pumped-piglet.maas}" 'bash -s' < "$SCRIPT_DIR/configure-mounts-host.sh"
