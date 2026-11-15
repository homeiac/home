#!/bin/bash
# Test the photos-takeout-ingest scripts locally with Docker, using the same pinned images as the CronJob
#
# Usage: ./test-photos-takeout-ingest.sh
#
# Extracts extract.sh / finalize.sh from the ConfigMap in this repo, builds fake Takeout archives in a
# scratch dir under ~/.cache (never touches the homelab), runs the two steps the way the CronJob does
# (debian initContainer, then rclone container), and asserts:
#   1. a finished archive is extracted into library/Google Photos, recorded in _ingested.tsv, deleted
#   2. an archive with a .part file (still downloading) is skipped and left alone
#   3. a later export with a changed photo replaces it and keeps the old one in .versions/<date>/
#   4. a corrupt (truncated) archive fails the run, stays in _incoming, leaves no staging behind
#   5. re-downloading an already-ingested archive is skipped, not ingested twice
# Exit 0 = all passed. Requires docker (and python3 + PyYAML to read the ConfigMap).

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CM="$REPO_ROOT/gitops/clusters/homelab/apps/cloud-backup/photos-takeout-ingest/configmap.yaml"
CJ="$REPO_ROOT/gitops/clusters/homelab/apps/cloud-backup/photos-takeout-ingest/cronjob.yaml"
DEBIAN_IMG="$(grep -o 'debian:[^ ]*' "$CJ" | head -1)"
RCLONE_IMG="$(grep -o 'rclone/rclone:[^ ]*' "$CJ" | head -1)"

W="$(mktemp -d "$HOME/.cache/photos-ingest-test.XXXXXX")"
trap 'docker run --rm -v "$W:/w" "$DEBIAN_IMG" rm -rf /w/data /w/status >/dev/null 2>&1; rm -rf "$W"' EXIT
mkdir -p "$W/scripts" "$W/data/gphotos/_incoming" "$W/status"
python3 - "$CM" "$W/scripts" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))["data"]
for k, v in d.items():
    open(f"{sys.argv[2]}/{k}", "w").write(v)
PY

PASS=0 FAIL=0
ok()   { echo "  PASS: $*"; PASS=$((PASS + 1)); }
bad()  { echo "  FAIL: $*"; FAIL=$((FAIL + 1)); }
dx()   { docker run --rm -v "$W/data:/data" -v "$W/scripts:/scripts:ro" "$DEBIAN_IMG" bash -c "$1"; }
run_ingest() {   # returns 0 if both steps succeeded (like the Job)
  docker run --rm -v "$W/data:/data" -v "$W/scripts:/scripts:ro" "$DEBIAN_IMG" bash /scripts/extract.sh || return 1
  docker run --rm --entrypoint /bin/sh -v "$W/data:/data" -v "$W/status:/status" -v "$W/scripts:/scripts:ro" \
    "$RCLONE_IMG" /scripts/finalize.sh
}
# make_archive <name> <content-of-a.jpg>: Takeout layout, mtime 1h ago so it counts as finished
make_archive() {
  dx "set -e; t=\$(mktemp -d); mkdir -p \"\$t/Takeout/Google Photos/Album A\" \"\$t/Takeout/Google Photos/Photos from 2020\"
      printf '%s' '$2' > \"\$t/Takeout/Google Photos/Album A/a.jpg\"
      echo '{\"title\":\"a.jpg\"}' > \"\$t/Takeout/Google Photos/Album A/a.jpg.supplemental-metadata.json\"
      echo b > \"\$t/Takeout/Google Photos/Photos from 2020/b.jpg\"
      echo '<html>' > \"\$t/Takeout/archive_browser.html\"
      tar -czf /data/gphotos/_incoming/$1.tgz -C \"\$t\" Takeout
      touch -d '1 hour ago' /data/gphotos/_incoming/$1.tgz"
}
lib="$W/data/gphotos/library/Google Photos"

echo "== 1. normal archive"
make_archive takeout-001 v1
run_ingest >/dev/null 2>&1 && ok "run succeeded" || bad "run failed"
[[ "$(cat "$lib/Album A/a.jpg" 2>/dev/null)" == v1 ]] && ok "a.jpg in library" || bad "a.jpg missing"
[[ -f "$lib/Photos from 2020/b.jpg" && -f "$lib/Album A/a.jpg.supplemental-metadata.json" ]] && ok "other file + sidecar" || bad "files missing"
[[ ! -e "$W/data/gphotos/_incoming/takeout-001.tgz" ]] && ok "archive deleted" || bad "archive not deleted"
grep -q "^takeout-001.tgz" "$W/data/gphotos/_ingested.tsv" && ok "recorded in ledger" || bad "not in ledger"

echo "== 2. still downloading (.part present)"
make_archive takeout-002 v1; dx "touch /data/gphotos/_incoming/takeout-002.tgz.part"
run_ingest >/dev/null 2>&1 || true
[[ -e "$W/data/gphotos/_incoming/takeout-002.tgz" ]] && ok "skipped, left in _incoming" || bad "was ingested while downloading"
dx "rm -f /data/gphotos/_incoming/takeout-002.tgz /data/gphotos/_incoming/takeout-002.tgz.part"

echo "== 2b. still downloading, Firefox naming (<name>.<random>.tgz.part, archive already has data)"
make_archive takeout-002b v1; dx "touch /data/gphotos/_incoming/takeout-002b.S6Uy6z6Y.tgz.part"
run_ingest >/dev/null 2>&1 || true
[[ -e "$W/data/gphotos/_incoming/takeout-002b.tgz" ]] && ok "skipped, left in _incoming" || bad "was ingested while downloading"
dx "rm -f /data/gphotos/_incoming/takeout-002b.tgz /data/gphotos/_incoming/takeout-002b.S6Uy6z6Y.tgz.part"

echo "== 3. later export changes a.jpg"
make_archive takeout-003 v2
run_ingest >/dev/null 2>&1 && ok "run succeeded" || bad "run failed"
[[ "$(cat "$lib/Album A/a.jpg")" == v2 ]] && ok "library has new version" || bad "library not updated"
old="$(find "$W/data/gphotos/.versions" -name a.jpg 2>/dev/null | head -1)"
[[ -n "$old" && "$(cat "$old")" == v1 ]] && ok "old version kept in .versions/" || bad "old version not kept"

echo "== 4. corrupt archive"
make_archive takeout-004 v3
dx "f=/data/gphotos/_incoming/takeout-004.tgz; head -c \$(( \$(stat -c %s \$f) / 2 )) \$f > \$f.cut && mv \$f.cut \$f && touch -d '1 hour ago' \$f"
if run_ingest >/dev/null 2>&1; then bad "corrupt archive did not fail the run"; else ok "run failed"; fi
[[ -e "$W/data/gphotos/_incoming/takeout-004.tgz" ]] && ok "archive left for retry" || bad "archive removed"
[[ ! -d "$W/data/gphotos/_staging/takeout-004" ]] && ok "no staging left" || bad "staging left behind"
[[ "$(cat "$lib/Album A/a.jpg")" == v2 ]] && ok "library untouched" || bad "library changed"
dx "rm -f /data/gphotos/_incoming/takeout-004.tgz"

echo "== 5. duplicate download of an ingested archive"
make_archive takeout-001 v9
run_ingest >/dev/null 2>&1 || true
[[ "$(cat "$lib/Album A/a.jpg")" == v2 ]] && ok "not ingested twice" || bad "duplicate was ingested"
[[ "$(grep -c '^takeout-001.tgz' "$W/data/gphotos/_ingested.tsv")" == 1 ]] && ok "ledger has one entry" || bad "ledger duplicated"

echo
echo "passed $PASS, failed $FAIL"
exit $(( FAIL > 0 ))
