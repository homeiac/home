#!/bin/bash
# Show the download browser's state: pod, URL check, and what has landed in _incoming
#
# Usage: ./download-browser-status.sh
#
# Read-only. kubectl runs inside the K3s VM (cb_kubectl). Downloads in progress end in .part.
# Open the browser at https://$DOWNLOAD_BROWSER_HOST (LAN or Tailscale), sign in with the
# credentials from download-browser-password.sh.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
NS=cloud-backup
APP=download-browser
DOWNLOAD_BROWSER_HOST="${DOWNLOAD_BROWSER_HOST:-download-browser.app.home.panderosystems.com}"

echo "== Pod"
cb_kubectl -n "$NS" get pods -l app="$APP" -o wide
echo
echo "== URL https://$DOWNLOAD_BROWSER_HOST"
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://$DOWNLOAD_BROWSER_HOST/" || true)"
case "$code" in
  401) echo "  reachable, asks for login (expected)";;
  200) echo "  reachable WITHOUT login - check the download-browser-auth secret!";;
  *)   echo "  HTTP $code (000 = not reachable from here)";;
esac
echo
echo "== Downloads (cloud-backup/gphotos/_incoming on the SMB share)"
POD="$(cb_kubectl -n "$NS" get pods -l app="$APP" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -n "$POD" ]]; then
  cb_kubectl -n "$NS" exec "$POD" -c firefox -- sh -c 'ls -la /config/Downloads; echo; df -h /config/Downloads | tail -1'
else
  echo "  (no pod)"
fi
