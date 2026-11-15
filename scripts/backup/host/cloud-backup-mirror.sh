#!/bin/bash
# Secondary copy: mirror the primary cloud backup onto the SSK USB disk (runs ON the Proxmox host)
#
# Installed to /usr/local/sbin/cloud-backup-mirror.sh by scripts/backup/cloud-backup-install-mirror.sh
# and run daily by cloud-backup-mirror.timer. Settings come from /etc/default/cloud-backup-mirror.
#
# How it gets a consistent, read-only view of the primary without credentials or network:
#   1. ZFS snapshot of the SMB share's zvol ($ZVOL, ext4 used by the K3s VM)
#   2. clone that snapshot (readonly=on) and mount the clone on the host with -o ro,noload
#   3. rclone copy <clone>/cloud-backup -> SSK:/cloud-backup   (copy, never sync: S1)
#      files changed since the last mirror keep their old version in SSK:/.versions/<date>/ (S2)
#   4. always (trap): unmount clone, destroy clone + snapshot, unmount the SSK
#
# The SSK is found by USB serial ($SSK_SERIAL) and must be exFAT labelled $SSK_LABEL; the script never
# writes into an unmounted mountpoint. exFAT can't store some characters (: ? * " < > | \): the SSK
# remote uses rclone's Windows-style encoding, so such names are stored with look-alike characters
# and restored by rclone on the way back.
#
# Status: $REPORT_DIR/mirror-last-run.json, logs in $REPORT_DIR/mirror-logs/ (60 days).
# Design: docs/plans/cloud-drive-backup-and-reclaim.md (§5.3, Phase 4)

set -euo pipefail

# shellcheck disable=SC1091
[[ -f /etc/default/cloud-backup-mirror ]] && source /etc/default/cloud-backup-mirror
: "${ZVOL:?ZVOL not set in /etc/default/cloud-backup-mirror}"
: "${SSK_SERIAL:?SSK_SERIAL not set}"
SSK_LABEL="${SSK_LABEL:-SSK}"
SSK_MNT="${SSK_MNT:-/mnt/ssk-cloud}"
SNAP_MNT="${SNAP_MNT:-/mnt/cloud-backup-snap}"
SRC_SUBDIR="${SRC_SUBDIR:-cloud-backup}"
REPORT_DIR="${REPORT_DIR:-/var/lib/cloud-backup/reports}"
RCLONE_FLAGS="${RCLONE_FLAGS:---transfers 8 --checkers 16}"

readonly STAMP="$(date +%Y%m%d-%H%M%S)" DAY="$(date +%Y-%m-%d)"
readonly POOL="${ZVOL%%/*}"
readonly SNAP="$ZVOL@cloudmirror-$STAMP"
readonly CLONE="$POOL/cloudmirror-clone"
readonly LOG_DIR="$REPORT_DIR/mirror-logs"
readonly LOG="$LOG_DIR/mirror-$STAMP.log"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG") 2>&1

log() { echo "[$(date '+%F %T')] $*"; }
STATUS="failed" STEP="start"
write_status() {
  printf '{"finished": "%s", "status": "%s", "step": "%s", "log": "%s"}\n' \
    "$(date -Iseconds)" "$STATUS" "$STEP" "$LOG" > "$REPORT_DIR/mirror-last-run.json"
}

# One run at a time
exec 9>/run/cloud-backup-mirror.lock
flock -n 9 || { log "another mirror run is active - exiting"; exit 0; }

SSK_MOUNTED_BY_US=0
cleanup() {
  local rc=$?
  set +e
  mountpoint -q "$SNAP_MNT" && umount "$SNAP_MNT"
  zfs list -H "$CLONE" >/dev/null 2>&1 && zfs destroy "$CLONE"
  zfs list -H "$SNAP" >/dev/null 2>&1 && zfs destroy "$SNAP"
  if [[ $SSK_MOUNTED_BY_US -eq 1 ]]; then sync; umount "$SSK_MNT"; fi
  [[ $rc -eq 0 ]] && STATUS="ok"
  write_status
  log "done: status=$STATUS step=$STEP exit=$rc"
  find "$LOG_DIR" -name 'mirror-*.log' -mtime +60 -delete
}
trap cleanup EXIT

log "cloud-backup-mirror start (zvol=$ZVOL ssk=$SSK_SERIAL)"

# --- 1. SSK: find by serial, verify, mount
STEP="find-ssk"
mapfile -t DISKS < <(lsblk -dnro NAME,SERIAL | awk -v s="$SSK_SERIAL" '$2==s {print $1}')
[[ ${#DISKS[@]} -eq 1 ]] || { log "ERROR: expected 1 disk with serial $SSK_SERIAL, found ${#DISKS[@]} (unplugged?)"; exit 1; }
PART="/dev/$(lsblk -nro NAME "/dev/${DISKS[0]}" | sed -n 2p)"
read -r FSTYPE LABEL < <(lsblk -no FSTYPE,LABEL "$PART")
[[ "$FSTYPE" == exfat && "$LABEL" == "$SSK_LABEL" ]] \
  || { log "ERROR: $PART is '$FSTYPE' label '$LABEL', expected exfat '$SSK_LABEL'"; exit 1; }
mkdir -p "$SSK_MNT"
if ! mountpoint -q "$SSK_MNT"; then
  mount -t exfat -o noatime,fmask=0077,dmask=0077 "$PART" "$SSK_MNT"
  SSK_MOUNTED_BY_US=1
fi
findmnt -no SOURCE "$SSK_MNT" | grep -qx "$PART" || { log "ERROR: $SSK_MNT is not $PART"; exit 1; }
log "SSK $PART mounted at $SSK_MNT ($(df -h --output=avail "$SSK_MNT" | tail -1 | tr -d ' ') free)"

# --- 2. point-in-time read-only view of the primary
STEP="snapshot"
zfs list -H "$CLONE" >/dev/null 2>&1 && { log "removing stale clone $CLONE"; zfs destroy "$CLONE"; }
zfs snapshot "$SNAP"
zfs clone -o readonly=on -o volmode=dev "$SNAP" "$CLONE"
DEV="/dev/zvol/$CLONE"
for _ in $(seq 1 30); do [[ -b "$DEV" ]] && break; udevadm settle; sleep 1; done
[[ -b "$DEV" ]] || { log "ERROR: clone device $DEV did not appear"; exit 1; }
mkdir -p "$SNAP_MNT"
mount -t ext4 -o ro,noload "$DEV" "$SNAP_MNT"
SRC="$SNAP_MNT/$SRC_SUBDIR"
[[ -d "$SRC" ]] || { log "ERROR: $SRC missing in the snapshot"; exit 1; }
log "snapshot $SNAP mounted read-only at $SNAP_MNT"

# --- 3. capacity check (rclone would fail with ENOSPC anyway; this fails early and clearly)
STEP="capacity"
need=$(du -sb --exclude='*.part' "$SRC" | cut -f1)
have=$(( $(df -B1 --output=avail "$SSK_MNT" | tail -1) + $(du -sb "$SSK_MNT/$SRC_SUBDIR" 2>/dev/null | cut -f1 || echo 0) ))
log "source $((need / 1000000000)) GB, SSK usable $((have / 1000000000)) GB"
(( need < have )) || { log "ERROR: SSK too small for the backup"; exit 1; }

# --- 4. copy
STEP="copy"
export RCLONE_CONFIG_SSK_TYPE=local
# rclone's default encoding for Windows/exFAT-safe names
export RCLONE_CONFIG_SSK_ENCODING="Slash,LtGt,DoubleQuote,Colon,Question,Asterisk,Pipe,BackSlash,Ctl,RightSpace,RightPeriod,InvalidUtf8,Dot"
# shellcheck disable=SC2086
rclone copy "$SRC" "SSK:$SSK_MNT/$SRC_SUBDIR" \
  --config /dev/null \
  --backup-dir "SSK:$SSK_MNT/.versions/$DAY" \
  --exclude '*.part' \
  --modify-window 2s \
  --stats 1m --stats-one-line --log-level INFO \
  $RCLONE_FLAGS
sync
STEP="complete"
log "copy finished; SSK now holds $(du -sh "$SSK_MNT/$SRC_SUBDIR" | cut -f1)"
