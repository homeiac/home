#!/bin/bash
# Seed the host's rclone config with the existing Google Drive remote from the SOPS secret
#
# Usage: ./cloud-backup-seed-gdrive-config.sh
#
# Run from a machine that has sops and the repo's age key. It decrypts the
# `rclone.conf` held in the postgres SOPS secret (remote "gdrive-backup", scope=drive)
# and streams it over SSH into the host's rclone config. The secret is never printed
# and never written to local disk.
#
# Merges by section: other remotes already on the host (e.g. onedrive) are kept, and
# only the gdrive-backup section is replaced.
# Design: docs/plans/cloud-drive-backup-and-reclaim.md (Phase 1, §8)

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

command -v sops >/dev/null || { echo "ERROR: sops not installed"; exit 1; }
SECRET="$CB_REPO_ROOT/$CB_GDRIVE_SOPS_SECRET"
[[ -f "$SECRET" ]] || { echo "ERROR: $SECRET not found"; exit 1; }

sops -d "$SECRET" \
  | python3 -c 'import sys, yaml; sys.stdout.write(yaml.safe_load(sys.stdin)["stringData"]["rclone.conf"])' \
  | cb_ssh "CONF='$CB_RCLONE_CONF' REMOTE='$CB_GDRIVE_REMOTE' python3 -c '
import configparser, os, sys
new = configparser.RawConfigParser(); new.read_string(sys.stdin.read())
remote = os.environ[\"REMOTE\"]
if remote not in new.sections():
    sys.exit(\"ERROR: remote %s not found in secret\" % remote)
conf = os.environ[\"CONF\"]
os.makedirs(os.path.dirname(conf), mode=0o700, exist_ok=True)
cur = configparser.RawConfigParser(); cur.read(conf)
if cur.has_section(remote): cur.remove_section(remote)
cur.add_section(remote)
for k, v in new.items(remote): cur.set(remote, k, v)
old = os.umask(0o077)
with open(conf, \"w\") as f: cur.write(f)
os.umask(old); os.chmod(conf, 0o600)
print(\"wrote [%s] to %s\" % (remote, conf))
'"

echo "Verifying..."
cb_ssh "rclone about '$CB_GDRIVE_REMOTE:' --config '$CB_RCLONE_CONF'"
