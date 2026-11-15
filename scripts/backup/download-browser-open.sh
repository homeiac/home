#!/bin/bash
# Open a URL in the running download browser (Firefox inside the homelab pod), as a new tab
#
# Usage: ./download-browser-open.sh <url>        e.g. https://takeout.google.com/manage
#
# Runs `firefox --new-tab <url>` inside the pod as the browser's user (abc, uid 65534) on its display,
# which hands the URL to the already-running Firefox. Useful when typing into the streamed desktop is
# awkward, or to script the start of a Takeout download session. Whoever has the browser open sees
# the new tab. Read the pod name and kubectl via cb_kubectl (no kubeconfig needed here).

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
URL="${1:?usage: $0 <url>}"
[[ "$URL" =~ ^(https?://|about:) ]] || { echo "ERROR: give a full http(s) URL or an about: page"; exit 1; }

POD="$(cb_kubectl -n cloud-backup get pods -l app=download-browser -o jsonpath='{.items[0].metadata.name}')"
[[ -n "$POD" ]] || { echo "ERROR: download-browser pod not found"; exit 1; }
cb_kubectl -n cloud-backup exec "$POD" -c firefox -- \
  s6-setuidgid abc env DISPLAY=:0 HOME=/config firefox --new-tab "$URL"
echo "Opened $URL in the download browser ($POD)"
