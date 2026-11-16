#!/bin/bash
# Statistical read-back check of a mirror target (SSK / WD): random stratified sample, byte-for-byte vs the library
#
# Usage (on the Proxmox host; normally via scripts/backup/verify-mirror-sample-ctl.sh):
#   verify-mirror-sample.sh <target> [--defect-rate 0.001] [--confidence 0.99] [--seed N] [--n COUNT]
#
# Population: every file under <target>/cloud-backup/gphotos/library on the mirror disk.
# Sample size (zero-failure plan): n = ceil(ln(1-C) / ln(1-p)); C=0.99, p=0.001 -> 4603 files. If n >= population: all files.
# Stratified by top folder ("Photos from YYYY" per year; albums as one stratum), proportional, >=1 per stratum.
# Each sampled file must exist in the primary library (host dataset), have the same size and identical bytes.
# Result: 0 defects  -> defect rate <= p_upper = 1-(1-C)^(1/n) with confidence C (printed);  any defect -> exit 1,
# list the defects, and the caller should fall back to the full check (rclone check / VERIFY=1).
# This is NOT six-sigma proof (3.4 per million would need ~880k samples); it bounds the defect rate, and the primary library
# was already fully gzip-verified at ingest, so a lost file needs BOTH copies bad.
# The mirror disk is mounted read-only (or reused if mounted) and unmounted again only if we mounted it. Waits for the mirror lock.
# Output: $REPORT_DIR/verify-sample-<target>-<time>.json + log lines.
set -euo pipefail
TARGET="${1:?usage: verify-mirror-sample.sh <target> [opts]}"; shift
RATE=0.001; CONF=0.99; SEED=$(date +%s); N=""
while [[ $# -gt 0 ]]; do case "$1" in
  --defect-rate) RATE="$2"; shift 2;; --confidence) CONF="$2"; shift 2;; --seed) SEED="$2"; shift 2;; --n) N="$2"; shift 2;;
  *) echo "unknown option $1"; exit 2;; esac; done
[[ "$TARGET" =~ ^[a-z0-9-]+$ ]] || { echo "bad target"; exit 2; }
[[ -f /etc/default/cloud-backup-mirror ]] && source /etc/default/cloud-backup-mirror
source "/etc/default/cloud-backup-mirror-$TARGET"
: "${DEST_SERIAL:?}" "${DEST_LABEL:?}" "${DEST_MNT:?}"
REPORT_DIR="${REPORT_DIR:-/var/lib/cloud-backup/reports}"; STAMP="$(date +%Y%m%d-%H%M%S)"
LIB="${PHOTOS_LIBRARY:-$(zfs get -H -o value mountpoint "${PHOTOS_DATASET:-local-3TB-backup/gphotos}")/library}"
log() { echo "[$(date '+%F %T')] $*"; }

exec 9>/run/cloud-backup-mirror.lock; log "waiting for mirror lock"; flock -w 21600 9
mapfile -t DISKS < <(lsblk -dnro NAME,SERIAL | awk -v s="$DEST_SERIAL" '$2==s {print $1}')
[[ ${#DISKS[@]} -eq 1 ]] || { log "ERROR: disk $DEST_SERIAL not attached"; exit 1; }
PART="$(lsblk -lnpo NAME,LABEL,FSTYPE "/dev/${DISKS[0]}" | awk -v l="$DEST_LABEL" '$2==l && $3=="exfat" {print $1}')"
[[ -n "$PART" ]] || { log "ERROR: no exfat partition labelled $DEST_LABEL"; exit 1; }
MOUNTED_BY_US=0; mkdir -p "$DEST_MNT"
if ! mountpoint -q "$DEST_MNT"; then mount -t exfat -o ro,noatime "$PART" "$DEST_MNT"; MOUNTED_BY_US=1; fi
trap '[[ $MOUNTED_BY_US -eq 1 ]] && umount "$DEST_MNT"' EXIT
log "target $PART at $DEST_MNT; library $LIB; seed $SEED"

python3 - "$DEST_MNT/cloud-backup/gphotos/library" "$LIB" "$RATE" "$CONF" "$SEED" "${N:-0}" "$REPORT_DIR/verify-sample-$TARGET-$STAMP.json" <<'PY'
import filecmp, json, math, os, random, sys, time
mirror, lib, rate, conf, seed, n_arg, out = sys.argv[1:8]
rate, conf, seed, n_arg = float(rate), float(conf), int(seed), int(n_arg)
# rclone's Windows-style encoding on the exFAT target: map the fullwidth stand-ins back
DEC = {ord(b): a for a, b in zip('"*:<>?\\|/', '＂＊：＜＞？＼｜／')}
def decode(name):
    name = name.translate(DEC)
    if name.endswith("␠"): name = name[:-1] + " "
    if name.endswith("．"): name = name[:-1] + "."
    return name
pop = []
for d, _, files in os.walk(mirror):
    rel = os.path.relpath(d, mirror)
    for f in files:
        pop.append((rel if rel != "." else "", f))
n = n_arg or math.ceil(math.log(1 - conf) / math.log(1 - rate))
n = min(n, len(pop))
strata = {}
for rel, f in pop:
    top = rel.split(os.sep)[0] if rel else ""
    if top.startswith("Photos from "): key = top
    elif top.startswith("Google Photos"):
        parts = rel.split(os.sep); key = parts[1] if len(parts) > 1 and parts[1].startswith("Photos from ") else "albums"
    else: key = "other"
    strata.setdefault(key, []).append((rel, f))
rnd = random.Random(seed); sample = []
for key, items in strata.items():
    k = max(1, round(n * len(items) / len(pop))); sample += rnd.sample(items, min(k, len(items)))
rnd.shuffle(sample)
print(f"population {len(pop)} files in {len(strata)} strata; sample {len(sample)} (target {n}), seed {seed}", flush=True)
defects, unmapped, ok, t0 = [], 0, 0, time.time()
for i, (rel, f) in enumerate(sample, 1):
    m = os.path.join(mirror, rel, f)
    p = os.path.normpath(os.path.join(lib, *[decode(x) for x in rel.split(os.sep)], decode(f)))
    try:
        if not os.path.exists(p):
            unmapped += 1; defects.append(("missing-in-library", m)); continue
        if os.path.getsize(m) != os.path.getsize(p): defects.append(("size", m)); continue
        if not filecmp.cmp(m, p, shallow=False): defects.append(("content", m)); continue
        ok += 1
    except OSError as e:
        defects.append((f"read-error {e.errno}", m))
    if i % 500 == 0: print(f"  {i}/{len(sample)} checked, {len(defects)} defects, {time.time()-t0:.0f}s", flush=True)
res = {"population": len(pop), "sampled": len(sample), "ok": ok, "defects": len(defects), "seed": seed,
       "confidence": conf, "defect_rate_target": rate, "defect_list": defects[:50]}
if not defects:
    res["defect_rate_upper_bound"] = 1 - (1 - conf) ** (1 / len(sample))
    print(f"RESULT PASS: {ok}/{len(sample)} identical; defect rate <= {res['defect_rate_upper_bound']:.4%} with {conf:.0%} confidence "
          f"(<= ~{math.ceil(res['defect_rate_upper_bound'] * len(pop))} of {len(pop)} files)")
else:
    print(f"RESULT FAIL: {len(defects)} defects in {len(sample)} samples: {defects[:10]} - run the full check")
json.dump(res, open(out, "w"), indent=1); sys.exit(0 if not defects else 1)
PY
