#!/bin/bash
# One-time OneDrive sign-in for the cloud-backup host (interactive)
#
# Usage (from a machine with a browser, in a real terminal; inside Claude Code use `! <path>`):
#   ./cloud-backup-auth-onedrive.sh            # sign in (asks before replacing an existing remote)
#   ./cloud-backup-auth-onedrive.sh --repair   # keep the stored token, only (re)detect the default drive
#
# How it works:
#   1. Opens an SSH session to the host with a tunnel: local 127.0.0.1:53682 -> host 127.0.0.1:53682.
#   2. Runs `rclone authorize onedrive` ON THE HOST. You open the printed URL in your browser and
#      sign in; Microsoft redirects to 127.0.0.1:53682, which is the tunnel, so the token is
#      delivered to the host. The token is filtered out of the terminal output and saved straight
#      into the host's rclone config.
#   3. Asks Microsoft Graph for the account's DEFAULT drive (GET /me/drive) using the stored token
#      and writes drive_id / drive_type. This step runs on its own with --repair (or when you keep
#      an existing remote), which fixes "unable to get drive_id and drive_type" without a new sign-in.
#
# Why not rclone's interactive drive picker: on some personal accounts the picker selects a drive
# Graph refuses ("ObjectHandle is Invalid", e.g. Personal Vault or a stale drive ID), and rclone
# then loops. /me/drive always returns the main drive.
#
# Expired access token: rclone won't start the backend without drive_id/drive_type, so step 3 sets
# placeholders first; one rclone call then refreshes the token (saved back to the config) before
# Graph is queried.
#
# The browser is only used for sign-in; no file data passes through this machine.
# The token is stored only in the host's rclone config (never committed, never printed).
# Design: docs/plans/cloud-drive-backup-and-reclaim.md (Phase 1, §8)

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

remote_exists() {
  cb_ssh "rclone listremotes --config '$CB_RCLONE_CONF' 2>/dev/null | grep -qx '$CB_ONEDRIVE_REMOTE:'"
}

set_default_drive() {
  cb_ssh "CONF='$CB_RCLONE_CONF' REMOTE='$CB_ONEDRIVE_REMOTE' bash -s" <<'EOF'
set -euo pipefail
get() { rclone config show "$REMOTE" --config "$CONF" | sed -n "s/^$1 = //p"; }
if [[ -z "$(get drive_id)" ]]; then
  rclone config update "$REMOTE" drive_type=personal drive_id=placeholder \
    --non-interactive --config "$CONF" >/dev/null
fi
# Any backend call refreshes an expired access token; the call itself may fail on the placeholder.
rclone about "$REMOTE:" --config "$CONF" >/dev/null 2>&1 || true
DRIVE="$(TOKEN="$(get token)" python3 - <<'PY'
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
# --non-interactive: without it `config update` re-runs the OAuth flow and waits for a browser.
rclone config update "$REMOTE" drive_id="$DRIVE_ID" drive_type="$DRIVE_TYPE" \
  --non-interactive --config "$CONF" >/dev/null
chmod 600 "$CONF"
EOF
}

SIGN_IN=1
if [[ "${1:-}" == "--repair" ]]; then
  remote_exists || { echo "ERROR: no '$CB_ONEDRIVE_REMOTE' remote to repair - run without --repair"; exit 1; }
  SIGN_IN=0
elif remote_exists; then
  [[ -t 0 ]] || { echo "ERROR: needs an interactive terminal"; exit 1; }
  read -r -p "Remote '$CB_ONEDRIVE_REMOTE' already exists on $CB_HOST. Replace it (new sign-in)? [y/N] " ans
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    cb_ssh "rclone config delete '$CB_ONEDRIVE_REMOTE' --config '$CB_RCLONE_CONF'"
  else
    echo "Keeping the existing token; only checking the drive settings."
    SIGN_IN=0
  fi
fi

if [[ $SIGN_IN -eq 1 ]]; then
  [[ -t 0 ]] || { echo "ERROR: sign-in needs an interactive terminal"; exit 1; }
  AUTH_TMP="$(dirname "$CB_RCLONE_CONF")/.onedrive-auth.tmp"
  echo "Starting OneDrive sign-in on $CB_HOST."
  echo "Open the URL below in your browser and sign in. (The token itself is hidden.)"
  echo
  # Token block goes to a 0600 file on the host and is deleted from what the terminal shows.
  ssh -t -o ExitOnForwardFailure=yes -L 53682:127.0.0.1:53682 "$CB_HOST" \
    "umask 077; rclone authorize onedrive --auth-no-open-browser 2>&1 | tee '$AUTH_TMP' \
       | sed -u '/Paste the following/,/End paste/d'"
  echo
  echo "Saving token to remote '$CB_ONEDRIVE_REMOTE'..."
  cb_ssh "AUTH_TMP='$AUTH_TMP' CONF='$CB_RCLONE_CONF' REMOTE='$CB_ONEDRIVE_REMOTE' bash -s" <<'EOF'
set -euo pipefail
trap 'rm -f "$AUTH_TMP"' EXIT
TOKEN="$(python3 - "$AUTH_TMP" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
m = re.search(r"--->\s*(\{.*?\})\s*<---", text, re.S)
if not m:
    sys.exit("ERROR: no token found in rclone authorize output (sign-in not completed?)")
print(m.group(1).replace("\r", "").replace("\n", ""))
PY
)"
rclone config create "$REMOTE" onedrive token="$TOKEN" drive_type=personal drive_id=placeholder \
  --non-interactive --config "$CONF" >/dev/null
chmod 600 "$CONF"
EOF
fi

echo "Detecting the account's default drive (GET /me/drive)..."
set_default_drive

echo
echo "Verifying..."
cb_ssh "rclone about '$CB_ONEDRIVE_REMOTE:' --config '$CB_RCLONE_CONF'"
