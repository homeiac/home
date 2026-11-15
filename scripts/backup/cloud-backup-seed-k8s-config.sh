#!/bin/bash
# Copy the host's rclone config into the K3s VM for the cloud-drive-pull CronJob
#
# Usage: ./cloud-backup-seed-k8s-config.sh [--force] [--only <remote>]
#   --force          overwrite the whole VM config with the host's
#   --only <remote>  replace just that remote's section in the VM config; other remotes (e.g. a
#                    OneDrive token the CronJob has refreshed since) are kept. Implies --force.
#
# Copies $CB_RCLONE_CONF on $CB_HOST (Proxmox host) into VM $CB_K3S_VMID at
# /var/lib/cloud-backup/rclone/rclone.conf (dir 0700, file 0600) using qm guest exec --pass-stdin.
# The copy runs host -> VM; the OAuth tokens never pass through this workstation and are never
# committed (not even SOPS-encrypted). The previous VM config is kept as rclone.conf.bak-<time>.
#
# Idempotent: without flags, if the VM already has a config with every remote, it does nothing.
# After seeding, the VM copy is the one the CronJob refreshes and keeps current. Re-seed after
# re-authorizing a remote on the host (cloud-backup-auth-onedrive.sh, cloud-backup-gdrive-own-client.sh).
# Design: docs/plans/cloud-drive-backup-and-reclaim.md (§8)

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

readonly VM_DIR=/var/lib/cloud-backup/rclone
FORCE=0 ONLY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1;;
    --only) ONLY="${2:?--only needs a remote name}"; FORCE=1; shift;;
    -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "ERROR: unknown option $1"; exit 1;;
  esac
  shift
done

cb_ssh "VMID='$CB_K3S_VMID' CONF='$CB_RCLONE_CONF' VM_DIR='$VM_DIR' FORCE='$FORCE' ONLY='$ONLY' \
        REMOTES='$CB_GDRIVE_REMOTE $CB_ONEDRIVE_REMOTE' bash -s" <<'EOS'
set -euo pipefail
gx() { qm guest exec "$VMID" --timeout 60 "$@" | python3 -c 'import json,sys
d=json.load(sys.stdin); sys.stdout.write(d.get("out-data","")); sys.stderr.write(d.get("err-data","")); sys.exit(d.get("exitcode",1))'; }

[[ -s "$CONF" ]] || { echo "ERROR: $CONF missing on host"; exit 1; }
for r in $REMOTES; do grep -q "^\[$r\]" "$CONF" || { echo "ERROR: remote [$r] not in host config"; exit 1; }; done

if [[ "$FORCE" != 1 ]]; then
  have="$(gx -- sh -c "grep -o '^\[[^]]*\]' $VM_DIR/rclone.conf 2>/dev/null | tr -d '[]' | tr '\n' ' '" || true)"
  missing=""; for r in $REMOTES; do [[ " $have " == *" $r "* ]] || missing="$missing $r"; done
  if [[ -z "$missing" ]]; then echo "VM already has: $have- nothing to do (use --force or --only)"; exit 0; fi
  echo "VM config missing:$missing - seeding"
fi

TMPD="$(mktemp -d)"; chmod 700 "$TMPD"; trap 'rm -rf "$TMPD"' EXIT
SRC="$CONF"
if [[ -n "$ONLY" ]]; then
  grep -q "^\[$ONLY\]" "$CONF" || { echo "ERROR: remote [$ONLY] not in host config"; exit 1; }
  gx -- cat "$VM_DIR/rclone.conf" > "$TMPD/vm.conf" 2>/dev/null || : > "$TMPD/vm.conf"
  cat > "$TMPD/merge.py" <<'PY'
import configparser, sys
vm, host, name = sys.argv[1:4]
a = configparser.RawConfigParser(); a.optionxform = str; a.read(vm)
b = configparser.RawConfigParser(); b.optionxform = str; b.read(host)
if a.has_section(name):
    a.remove_section(name)
a.add_section(name)
for k, v in b.items(name):
    a.set(name, k, v)
a.write(sys.stdout)
PY
  python3 "$TMPD/merge.py" "$TMPD/vm.conf" "$CONF" "$ONLY" > "$TMPD/merged.conf"
  SRC="$TMPD/merged.conf"
fi

gx -- sh -c "umask 077; mkdir -p $VM_DIR; chmod 700 $VM_DIR; [ -f $VM_DIR/rclone.conf ] && cp -a $VM_DIR/rclone.conf $VM_DIR/rclone.conf.bak-\$(date +%Y%m%d-%H%M%S); true" >/dev/null
gx --pass-stdin 1 -- sh -c "umask 077; cat > $VM_DIR/rclone.conf.new && mv $VM_DIR/rclone.conf.new $VM_DIR/rclone.conf && chmod 600 $VM_DIR/rclone.conf" < "$SRC"
echo "Seeded VM $VMID:$VM_DIR/rclone.conf (${ONLY:+only [$ONLY] replaced; }remotes: $(grep -o '^\[[^]]*\]' "$SRC" | tr -d '[]' | tr '\n' ' '))"
EOS
