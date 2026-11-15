#!/bin/bash
# One-time OneDrive sign-in for the cloud-backup host (interactive)
#
# Usage (from a machine with a browser, in a real terminal; inside Claude Code use `! <path>`):
#   ./cloud-backup-auth-onedrive.sh
#
# How it works:
#   1. Opens an SSH session to the host with a tunnel: local 127.0.0.1:53682 -> host 127.0.0.1:53682.
#   2. Runs `rclone authorize onedrive` ON THE HOST. You open the printed URL in your browser and
#      sign in; Microsoft redirects to 127.0.0.1:53682, which is the tunnel, so the token is
#      delivered to the host. The token is filtered out of the terminal output.
#   3. On the host, asks Microsoft Graph for the account's DEFAULT drive (GET /me/drive) and creates
#      the remote with that drive_id and drive_type, non-interactively.
#
# Why not rclone's interactive drive picker: on some personal accounts the picker selects a drive
# Graph refuses ("ObjectHandle is Invalid", e.g. Personal Vault or a stale drive ID), and rclone
# then loops. /me/drive always returns the main drive.
#
# The browser is only used for sign-in; no file data passes through this machine.
# The token is stored only in the host's rclone config (never committed, never printed).
# Design: docs/plans/cloud-drive-backup-and-reclaim.md (Phase 1, §8)

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

[[ -t 0 ]] || { echo "ERROR: needs an interactive terminal"; exit 1; }

if cb_ssh "rclone listremotes --config '$CB_RCLONE_CONF' 2>/dev/null | grep -qx '$CB_ONEDRIVE_REMOTE:'"; then
  read -r -p "Remote '$CB_ONEDRIVE_REMOTE' already exists on $CB_HOST. Replace it? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || { echo "Keeping existing remote."; exit 0; }
  cb_ssh "rclone config delete '$CB_ONEDRIVE_REMOTE' --config '$CB_RCLONE_CONF'"
fi

AUTH_TMP="$(dirname "$CB_RCLONE_CONF")/.onedrive-auth.tmp"

echo "Starting OneDrive sign-in on $CB_HOST."
echo "Open the URL below in your browser and sign in. (The token itself is hidden.)"
echo
# Token block is written to a 0600 file on the host and deleted from what the terminal shows.
ssh -t -o ExitOnForwardFailure=yes -L 53682:127.0.0.1:53682 "$CB_HOST" \
  "umask 077; rclone authorize onedrive --auth-no-open-browser 2>&1 | tee '$AUTH_TMP' \
     | sed -u '/Paste the following/,/End paste/d'"

echo
echo "Configuring remote '$CB_ONEDRIVE_REMOTE' with the account's default drive..."
cb_ssh "AUTH_TMP='$AUTH_TMP' CONF='$CB_RCLONE_CONF' REMOTE='$CB_ONEDRIVE_REMOTE' bash -s" <<'EOF'
set -euo pipefail
trap 'rm -f "$AUTH_TMP"' EXIT
TOKEN="$(python3 - "$AUTH_TMP" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
m = re.search(r"--->\s*(\{.*?\})\s*<---", text, re.S)
if not m:
    sys.exit("ERROR: no token found in rclone authorize output (sign-in not completed?)")
print(m.group(1).replace("\n", ""))
PY
)"
DRIVE="$(TOKEN="$TOKEN" python3 - <<'PY'
import json, os, urllib.request
tok = json.loads(os.environ["TOKEN"])["access_token"]
req = urllib.request.Request("https://graph.microsoft.com/v1.0/me/drive",
                             headers={"Authorization": "Bearer " + tok})
d = json.load(urllib.request.urlopen(req, timeout=30))
print(d["id"], d["driveType"])
PY
)"
read -r DRIVE_ID DRIVE_TYPE <<<"$DRIVE"
echo "Default drive: type=$DRIVE_TYPE id=${DRIVE_ID:0:6}..."
rclone config create "$REMOTE" onedrive \
  token="$TOKEN" drive_id="$DRIVE_ID" drive_type="$DRIVE_TYPE" \
  --non-interactive --config "$CONF" >/dev/null
chmod 600 "$CONF"
echo "Remote '$REMOTE' created."
EOF

echo
echo "Verifying..."
cb_ssh "rclone about '$CB_ONEDRIVE_REMOTE:' --config '$CB_RCLONE_CONF'"
