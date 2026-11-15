#!/bin/bash
# One-time OneDrive sign-in for the cloud-backup host (interactive)
#
# Usage (from a machine with a browser, in a real terminal; inside Claude Code use `! <path>`):
#   ./cloud-backup-auth-onedrive.sh
#
# How it works:
#   - Opens an SSH session to the host with a tunnel: local 127.0.0.1:53682 -> host 127.0.0.1:53682
#   - Runs `rclone config create <remote> onedrive` ON THE HOST. rclone prints a sign-in URL
#     and starts its OAuth callback listener on host port 53682.
#   - You open the URL in your browser and sign in to Microsoft. The redirect to
#     127.0.0.1:53682 goes through the tunnel to the host, so the token lands on the host.
#   - Answer rclone's follow-up prompts: pick "OneDrive Personal or Business" and the
#     drive it lists (usually the first one).
#
# The browser is only used for sign-in; no file data passes through this machine.
# The token is stored only in the host's rclone config (never committed).
# Design: docs/plans/cloud-drive-backup-and-reclaim.md (Phase 1, §8)

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

[[ -t 0 ]] || { echo "ERROR: needs an interactive terminal"; exit 1; }

if cb_ssh "rclone listremotes --config '$CB_RCLONE_CONF' 2>/dev/null | grep -qx '$CB_ONEDRIVE_REMOTE:'"; then
  read -r -p "Remote '$CB_ONEDRIVE_REMOTE' already exists on $CB_HOST. Replace it? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || { echo "Keeping existing remote."; exit 0; }
  cb_ssh "rclone config delete '$CB_ONEDRIVE_REMOTE' --config '$CB_RCLONE_CONF'"
fi

echo "Starting OneDrive sign-in on $CB_HOST."
echo "When rclone prints a URL, open it in your browser and sign in."
echo
ssh -t -o ExitOnForwardFailure=yes -L 53682:127.0.0.1:53682 "$CB_HOST" \
  "umask 077; rclone config create '$CB_ONEDRIVE_REMOTE' onedrive --config '$CB_RCLONE_CONF'"

echo
echo "Verifying..."
cb_ssh "rclone about '$CB_ONEDRIVE_REMOTE:' --config '$CB_RCLONE_CONF'"
