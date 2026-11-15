#!/bin/bash
# Mirror the primary cloud backup onto a USB disk (runs ON the Proxmox host): secondary/tertiary copies
#
# Usage: cloud-backup-mirror.sh <target>        (e.g. ssk, wd25)
#
# Installed to /usr/local/sbin/ by scripts/backup/cloud-backup-install-mirror.sh and run daily by
# cloud-backup-mirror@<target>.timer. Settings:
#   /etc/default/cloud-backup-mirror            shared: ZVOL, SRC_SUBDIR, REPORT_DIR
#   /etc/default/cloud-backup-mirror-<target>   DEST_SERIAL, DEST_LABEL, DEST_MNT, DEST_VERSIONS,
#                                               EXCLUDES (space-separated rclone patterns), VERIFY (0/1)
#
# Each run, for consistency without credentials or network:
#   1. find the target disk by USB serial, the partition by filesystem label (must be exFAT), mount it
#   2. ZFS snapshot of the SMB share's zvol, clone it readonly=on, mount the clone -o ro,noload
#   3. capacity check (rclone size with the same filters), then
#      rclone copy <clone>/$SRC_SUBDIR -> <disk>/$SRC_SUBDIR   (copy, never sync: S1)
#      changed files keep their previous version in <disk>/$DEST_VERSIONS/<date>/ (S2)
#   4. VERIFY=1: rclone check (hashes, reads every file back) - for disks with a history of bad sectors
#   5. always (trap): unmount clone, destroy clone + snapshot, unmount the disk if we mounted it
# Only $SRC_SUBDIR and $DEST_VERSIONS are written on the target disk; other files there are untouched.
# exFAT can't store : ? * " < > | \ in names: the target uses rclone's Windows-style encoding.
# Runs are serialized with a global lock (a second target waits for the first).
#
# Status: $REPORT_DIR/mirror-<target>-last-run.json, logs $REPORT_DIR/mirror-logs/mirror-<target>-*.log (60 days)
# Design: docs/plans/cloud-drive-backup-and-reclaim.md (§5.3, Phase 4)

set -euo pipefail

readonly TARGET="${1:?usage: cloud-backup-mirror.sh <target>}"
[[ "$TARGET" =~ ^[a-z0-9-]+$ ]] || { echo "bad target name: $TARGET"; exit 2; }
# shellcheck disable=SC1091
[[ -f /etc/default/cloud-backup-mirror ]] && source /etc/default/cloud-backup-mirror
# shellcheck disable=SC1090
[[ -f "/etc/default/cloud-backup-mirror-$TARGET" ]] && source "/etc/default/cloud-backup-mirror-$TARGET" \
  || { echo "missing /etc/default/cloud-backup-mirror-$TARGET"; exit 2; }
: "${ZVOL:?}" "${DEST_SERIAL:?}" "${DEST_LABEL:?}" "${DEST_MNT:?}"
SRC_SUBDIR="${SRC_SUBDIR:-cloud-backup}"
REPORT_DIR="${REPORT_DIR:-/var/lib/cloud-backup/reports}"
DEST_VERSIONS="${DEST_VERSIONS:-.versions}"
EXCLUDES="${EXCLUDES:-}"
VERIFY="${VERIFY:-0}"
RCLONE_FLAGS="${RCLONE_FLAGS:---transfers 8 --checkers 16}"

readonly STAMP="$(date +%Y%m%d-%H%M%S)" DAY="$(date +%Y-%m-%d)"
readonly POOL="${ZVOL%%/*}"
readonly SNAP="$ZVOL@cloudmirror-$TARGET-$STAMP"
readonly CLONE="$POOL/cloudmirror-clone-$TARGET"
readonly SNAP_MNT="/mnt/cloud-backup-snap-$TARGET"
readonly LOG_DIR="$REPORT_DIR/mirror-logs"
readonly LOG="$LOG_DIR/mirror-$TARGET-$STAMP.log"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG") 2>&1

log() { echo "[$(date '+%F %T')] $*"; }
STATUS="failed" STEP="start" DETAIL=""
write_status() {
  printf '{"target": "%s", "finished": "%s", "status": "%s", "step": "%s", "detail": "%s", "log": "%s"}\n' \
    "$TARGET" "$(date -Iseconds)" "$STATUS" "$STEP" "$DETAIL" "$LOG" > "$REPORT_DIR/mirror-$TARGET-last-run.json"
}

# Filters shared by size, copy and check
FILTERS=(--exclude '*.part')
for p in $EXCLUDES; do FILTERS+=(--exclude "$p"); done

# One mirror at a time (any target); wait up to 6h for another run to finish
exec 9>/run/cloud-backup-mirror.lock
log "waiting for mirror lock"
flock -w 21600 9 || { log "ERROR: lock wait timed out"; DETAIL="lock timeout"; write_status; exit 1; }

DEST_MOUNTED_BY_US=0
cleanup() {
  local rc=$?
  set +e
  mountpoint -q "$SNAP_MNT" && umount "$SNAP_MNT"
  zfs list -H "$CLONE" >/dev/null 2>&1 && zfs destroy "$CLONE"
  zfs list -H "$SNAP" >/dev/null 2>&1 && zfs destroy "$SNAP"
  if [[ $DEST_MOUNTED_BY_US -eq 1 ]]; then sync; umount "$DEST_MNT"; fi
  [[ $rc -eq 0 ]] && STATUS="ok"
  write_status
  log "done: target=$TARGET status=$STATUS step=$STEP exit=$rc ${DETAIL}"
  find "$LOG_DIR" -name "mirror-$TARGET-*.log" -mtime +60 -delete
}
trap cleanup EXIT

log "cloud-backup-mirror $TARGET start (zvol=$ZVOL serial=$DEST_SERIAL label=$DEST_LABEL excludes='$EXCLUDES' verify=$VERIFY)"

# --- 1. target disk: by serial, partition by label, exFAT only
STEP="find-disk"
mapfile -t DISKS < <(lsblk -dnro NAME,SERIAL | awk -v s="$DEST_SERIAL" '$2==s {print $1}')
[[ ${#DISKS[@]} -eq 1 ]] || { DETAIL="disk $DEST_SERIAL not attached"; log "ERROR: expected 1 disk with serial $DEST_SERIAL, found ${#DISKS[@]}"; exit 1; }
PART="$(lsblk -lnpo NAME,LABEL,FSTYPE "/dev/${DISKS[0]}" | awk -v l="$DEST_LABEL" '$2==l && $3=="exfat" {print $1}')"
[[ -n "$PART" && $(wc -l <<<"$PART") -eq 1 ]] \
  || { DETAIL="no single exfat partition labelled $DEST_LABEL"; log "ERROR: $DETAIL on /dev/${DISKS[0]}"; exit 1; }
mkdir -p "$DEST_MNT"
if ! mountpoint -q "$DEST_MNT"; then
  mount -t exfat -o noatime,fmask=0077,dmask=0077 "$PART" "$DEST_MNT"
  DEST_MOUNTED_BY_US=1
fi
findmnt -no SOURCE "$DEST_MNT" | grep -qx "$PART" || { DETAIL="$DEST_MNT is not $PART"; log "ERROR: $DETAIL"; exit 1; }
log "target $PART mounted at $DEST_MNT ($(df -h --output=avail "$DEST_MNT" | tail -1 | tr -d ' ') free)"

# --- 2. point-in-time read-only view of the primary
STEP="snapshot"
zfs list -H "$CLONE" >/dev/null 2>&1 && { log "removing stale clone $CLONE"; zfs destroy "$CLONE"; }
zfs snapshot "$SNAP"
zfs clone -o readonly=on -o volmode=dev "$SNAP" "$CLONE"
DEV="/dev/zvol/$CLONE"
for _ in $(seq 1 30); do [[ -b "$DEV" ]] && break; udevadm settle; sleep 1; done
[[ -b "$DEV" ]] || { DETAIL="clone device missing"; log "ERROR: $DEV did not appear"; exit 1; }
mkdir -p "$SNAP_MNT"
mount -t ext4 -o ro,noload "$DEV" "$SNAP_MNT"
SRC="$SNAP_MNT/$SRC_SUBDIR"
[[ -d "$SRC" ]] || { DETAIL="$SRC_SUBDIR missing in snapshot"; log "ERROR: $DETAIL"; exit 1; }
log "snapshot $SNAP mounted read-only at $SNAP_MNT"

export RCLONE_CONFIG_DEST_TYPE=local
export RCLONE_CONFIG_DEST_ENCODING="Slash,LtGt,DoubleQuote,Colon,Question,Asterisk,Pipe,BackSlash,Ctl,RightSpace,RightPeriod,InvalidUtf8,Dot"
DST="DEST:$DEST_MNT/$SRC_SUBDIR"

# --- 3. capacity (same filters as the copy)
STEP="capacity"
need=$(rclone size "$SRC" "${FILTERS[@]}" --json --config /dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["bytes"])')
have=$(( $(df -B1 --output=avail "$DEST_MNT" | tail -1) + $(du -sb "$DEST_MNT/$SRC_SUBDIR" 2>/dev/null | cut -f1 || echo 0) ))
log "to mirror $((need / 1000000)) MB, usable on target $((have / 1000000)) MB"
(( need < have )) || { DETAIL="target too small: need $((need/1000000)) MB, have $((have/1000000)) MB"; log "ERROR: $DETAIL"; exit 1; }

# --- 4. copy
STEP="copy"
# shellcheck disable=SC2086
rclone copy "$SRC" "$DST" "${FILTERS[@]}" \
  --config /dev/null \
  --backup-dir "DEST:$DEST_MNT/$DEST_VERSIONS/$DAY" \
  --modify-window 2s \
  --stats 1m --stats-one-line --log-level INFO \
  $RCLONE_FLAGS
sync

# --- 5. optional read-back verification
if [[ "$VERIFY" == 1 ]]; then
  STEP="verify"
  echo 3 > /proc/sys/vm/drop_caches   # make the check read from the disk, not the page cache
  if ! rclone check "$SRC" "$DST" "${FILTERS[@]}" --one-way --config /dev/null --log-level NOTICE; then
    DETAIL="verify found differences (possible bad sectors) - see log"; log "ERROR: $DETAIL"; exit 1
  fi
  log "verify: every file reads back identical"
fi
STEP="complete"
DETAIL="$(du -sh "$DEST_MNT/$SRC_SUBDIR" | cut -f1) on target"
log "mirror complete; $DETAIL"
