#!/bin/bash
# Unpack Google Photos Takeout archives ON THE PROXMOX HOST into a ZFS dataset (no VM / K3s in the path)
#
# Usage (on the host; normally started by scripts/backup/gphotos-ingest-ctl.sh):
#   gphotos-ingest-host.sh
#
# Why on the host (2026-11-16): unpacking inside K3s VM 105 onto its USB-HDD SMB disk stalled etcd's
# fsyncs on the VM's root disk (shared virtio-scsi controller; scripts/k3s/io-isolation-test.sh p99 4.2 s)
# and the K3s node went NotReady. Here tar writes straight into a host ZFS dataset.
#
# Sources (read-only): the archives live inside VM 105's disks. For each zvol in SOURCES the script takes
# a ZFS snapshot, clones it readonly=on, mounts the given partition -o ro,noload, and reads *.tgz from the
# given directory. Archives are complete files, so a snapshot of the running VM is safe for them.
# Target: dataset $DATASET (created if missing, recordsize=1M), mounted at $LIB_ROOT:
#   $LIB_ROOT/library/Google Photos/...   the kept library (+ Takeout .json sidecars)
#   $LIB_ROOT/_staging/<archive>/         one archive at a time, same dataset (final step is renames)
#   $LIB_ROOT/.versions/<date>/...        a library file replaced by a different one from a later export
#   $LIB_ROOT/_ingested.tsv               archive, bytes, md5, files, date  (re-runs skip these)
# Per archive: one read pass (md5 + gunzip CRC + extract), extracted file count == archive member count,
# then every file is renamed into the library (albums split across parts merge). Archives are NOT deleted.
# Cleanup (always, via trap): unmount clones, destroy clones + snapshots, remove partial staging.
# Log: /var/lib/cloud-backup/reports/gphotos-ingest-<time>.log; status: $LIB_ROOT/_last-run.json

set -euo pipefail
DATASET="${DATASET:-local-3TB-backup/gphotos}"
# zvol:partition-suffix:directory-inside-that-filesystem   (partition suffix "" = whole disk)
SOURCES="${SOURCES:-local-2TB-zfs/vm-105-disk-1:-part1:/var/lib/cloud-backup/downloads local-3TB-backup/vm-105-disk-0::/cloud-backup/gphotos/_incoming}"
REPORT_DIR=/var/lib/cloud-backup/reports
ARCHIVE_FILTER="${ARCHIVE_FILTER:-}"   # optional substring: only archives whose name contains it (smoke tests)
STAMP="$(date +%Y%m%d-%H%M%S)"; DAY="$(date +%Y-%m-%d)"
LOG="$REPORT_DIR/gphotos-ingest-$STAMP.log"
mkdir -p "$REPORT_DIR"
exec > >(tee -a "$LOG") 2>&1
log() { echo "[$(date '+%F %T')] $*"; }

exec 9>/run/gphotos-ingest.lock
flock -n 9 || { log "another ingest is running"; exit 0; }

# --- target dataset
if ! zfs list -H "$DATASET" >/dev/null 2>&1; then
  zfs create -o recordsize=1M -o compression=lz4 -o atime=off "$DATASET"
  log "created dataset $DATASET"
fi
LIB_ROOT="$(zfs get -H -o value mountpoint "$DATASET")"
[[ -d "$LIB_ROOT" ]] || { log "ERROR: $DATASET not mounted"; exit 1; }
mkdir -p "$LIB_ROOT/library/Google Photos" "$LIB_ROOT/_staging"
LEDGER="$LIB_ROOT/_ingested.tsv"; touch "$LEDGER"

CLONES=() MOUNTS=() SNAPS=() CUR=""
DONE_N=0 RESULT=failed
cleanup() {
  local rc=$?; set +e
  [[ -n "$CUR" ]] && rm -rf "$LIB_ROOT/_staging/$CUR" "$LIB_ROOT/_staging/$CUR.list" "$LIB_ROOT/_staging/$CUR.rc" && log "removed partial staging $CUR"
  for m in "${MOUNTS[@]}"; do mountpoint -q "$m" && umount "$m"; rmdir "$m" 2>/dev/null; done
  for c in "${CLONES[@]}"; do zfs destroy "$c"; done
  for s in "${SNAPS[@]}"; do zfs destroy "$s"; done
  [[ $rc -eq 0 ]] && RESULT=ok
  printf '{"finished": "%s", "status": "%s", "ingested_this_run": %d, "ingested_total": %d, "log": "%s"}\n' \
    "$(date -Iseconds)" "$RESULT" "$DONE_N" "$(wc -l < "$LEDGER")" "$LOG" > "$LIB_ROOT/_last-run.json"
  log "done: status=$RESULT ingested_this_run=$DONE_N total=$(wc -l < "$LEDGER")"
}
trap cleanup EXIT

# --- read-only views of the source disks
ARCHIVES=()
i=0
for src in $SOURCES; do
  IFS=: read -r zvol part dir <<<"$src"
  pool="${zvol%%/*}"; snap="$zvol@gphotos-ingest-$STAMP"; clone="$pool/gphotos-ingest-src-$i"
  zfs list -H "$clone" >/dev/null 2>&1 && zfs destroy "$clone"
  zfs snapshot "$snap"; SNAPS+=("$snap")
  zfs clone -o readonly=on -o volmode=dev "$snap" "$clone"; CLONES+=("$clone")
  dev="/dev/zvol/$clone$part"
  for _ in $(seq 1 30); do [[ -b "$dev" ]] && break; udevadm settle; sleep 1; done
  [[ -b "$dev" ]] || { log "ERROR: $dev did not appear"; exit 1; }
  mnt="/mnt/gphotos-ingest-src-$i"; mkdir -p "$mnt"
  mount -t ext4 -o ro,noload "$dev" "$mnt"; MOUNTS+=("$mnt")
  log "source $zvol$part mounted read-only at $mnt"
  for f in "$mnt$dir"/*.tgz; do [[ -s "$f" ]] || continue; [[ -z "$ARCHIVE_FILTER" || "$(basename "$f")" == *"$ARCHIVE_FILTER"* ]] && ARCHIVES+=("$f"); done
  i=$((i + 1))
done
log "archives found: ${#ARCHIVES[@]}"

# --- ingest, one archive at a time
for f in "${ARCHIVES[@]}"; do
  base="$(basename "$f")"; name="${base%.tgz}"
  if cut -f1 "$LEDGER" | grep -qxF "$base"; then log "skip $base: already ingested"; continue; fi
  size=$(stat -c %s "$f")
  free=$(zfs get -Hp -o value available "$DATASET")
  (( free > size + size / 10 )) || { log "ERROR: not enough space in $DATASET for $base"; exit 1; }
  CUR="$name"; st="$LIB_ROOT/_staging/$name"
  rm -rf "$st"; mkdir -p "$st"
  log "extracting $base ($((size / 1000000000)) GB)"
  md5=$( { tee >(tar -xzvf - -C "$st" --no-same-owner > "$st.list"; echo $? > "$st.rc") < "$f" | md5sum | cut -c1-32; } )
  for _ in $(seq 1 600); do [[ -s "$st.rc" ]] && break; sleep 1; done   # process substitution finishes async
  [[ "$(cat "$st.rc" 2>/dev/null)" == 0 ]] || { log "ERROR $base: tar/gunzip failed (exit $(cat "$st.rc" 2>/dev/null)) - corrupt archive?"; exit 1; }
  members=$(grep -vc '/$' "$st.list" || true)
  files=$(find "$st" -type f | wc -l)
  (( members == files )) || { log "ERROR $base: archive has $members files, extracted $files"; exit 1; }
  # rename every file into the library (same dataset: instant); keep a replaced, different file
  python3 - "$st" "$LIB_ROOT" "$DAY" <<'PY'
import filecmp, os, sys
st, root, day = sys.argv[1:4]
src_root = os.path.join(st, "Takeout", "Google Photos")
if not os.path.isdir(src_root):
    src_root = os.path.join(st, "Takeout")
lib = os.path.join(root, "library", "Google Photos")
moved = same = versioned = 0
for d, _, files in os.walk(src_root):
    rel = os.path.relpath(d, src_root)
    for fn in files:
        s = os.path.join(d, fn); t = os.path.normpath(os.path.join(lib, rel, fn))
        os.makedirs(os.path.dirname(t), exist_ok=True)
        if os.path.exists(t):
            if filecmp.cmp(s, t, shallow=False):
                os.remove(s); same += 1; continue
            v = os.path.normpath(os.path.join(root, ".versions", day, rel, fn))
            os.makedirs(os.path.dirname(v), exist_ok=True); os.rename(t, v); versioned += 1
        os.rename(s, t); moved += 1
print("moved %d, identical %d, previous versions kept %d" % (moved, same, versioned))
PY
  printf '%s\t%s\t%s\t%s\t%s\n' "$base" "$size" "$md5" "$files" "$(date -Iseconds)" >> "$LEDGER"
  rm -rf "$st" "$st.list" "$st.rc"; CUR=""
  DONE_N=$((DONE_N + 1))
  log "ingested $base ($files files)"
done
