#!/bin/bash
# Phase 0: measure Google Drive / OneDrive / Google storage before any download (read-only)
#
# Usage: ./cloud-backup-measure.sh [remote ...]
#   default remotes: $CB_GDRIVE_REMOTE and $CB_ONEDRIVE_REMOTE (whichever exist on the host)
#
# For each remote, on the host:
#   - `rclone about`: quota total / used / trash / other. For Google, "other" includes
#     Google Photos and Gmail, which share the same quota.
#   - one recursive listing (`rclone lsjson -R`), summarised into: total bytes and files,
#     Google-native Docs count (no real size, exported on backup), size and file count per folder,
#     the largest files, and any Takeout archives already on the drive.
# Then evaluates the capacity gate in §10 of the design (primary 170G free, SSK ~220G usable).
#
# Nothing is downloaded and nothing is modified. The report is saved on the host under $CB_REPORT_DIR.
# Design: docs/plans/cloud-drive-backup-and-reclaim.md (Phase 0)

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

REMOTES=("$@")
if [[ ${#REMOTES[@]} -eq 0 ]]; then
  for r in "$CB_GDRIVE_REMOTE" "$CB_ONEDRIVE_REMOTE"; do
    cb_ssh "rclone listremotes --config '$CB_RCLONE_CONF' | grep -qx '$r:'" && REMOTES+=("$r") \
      || echo "NOTE: remote '$r' not configured on $CB_HOST - skipping"
  done
fi
[[ ${#REMOTES[@]} -gt 0 ]] || { echo "ERROR: no remotes to measure"; exit 1; }

cb_ssh "CONF='$CB_RCLONE_CONF' OUT='$CB_REPORT_DIR' REMOTES='${REMOTES[*]}' OD='$CB_ONEDRIVE_REMOTE' OD_EXCLUDE='$CB_ONEDRIVE_EXCLUDE' bash -s" <<'EOF'
set -euo pipefail
mkdir -p "$OUT"
REPORT="$OUT/measure-$(date +%Y%m%d-%H%M%S).txt"
TOTAL_FILE="$(mktemp)"; trap 'rm -f "$TOTAL_FILE"' EXIT
{
for r in $REMOTES; do
  echo "================ $r ================"
  rclone about "$r:" --config "$CONF" || echo "(about failed)"
  echo
  echo "Listing $r: (recursive, may take a few minutes)..." >&2
  EXCL=(); [[ "$r" == "$OD" ]] && EXCL=(--exclude "$OD_EXCLUDE")
  rclone lsjson -R --files-only --fast-list "${EXCL[@]}" "$r:" --config "$CONF" \
    | R="$r" TOTAL_FILE="$TOTAL_FILE" python3 -c '
import json, os, sys, collections
items = json.load(sys.stdin)
# rclone lists Google-native files under their export format (e.g. .docx) with Size -1
is_gdoc = lambda i: i.get("Size", 0) < 0 or i.get("MimeType", "").startswith("application/vnd.google-apps.")
gdocs = [i for i in items if is_gdoc(i)]
real = [i for i in items if not is_gdoc(i) and i.get("Size", 0) > 0]
total = sum(i["Size"] for i in real)
gb = lambda b: "%8.2f GB" % (b / 1e9)
print("Files with data : %d   total %s" % (len(real), gb(total)))
print("Google-native   : %d Docs/Sheets/Slides (no quota size; exported on backup)" % len(gdocs))
by_top = collections.Counter()
for i in real:
    by_top[i["Path"].split("/", 1)[0] if "/" in i["Path"] else "(root files)"] += i["Size"]
print("\nTop-level folders by size:")
for k, v in by_top.most_common(25):
    print("  %s  %s" % (gb(v), k))
by_count = collections.Counter()
for i in real:
    by_count[i["Path"].split("/", 1)[0] if "/" in i["Path"] else "(root files)"] += 1
print("\nTop-level folders by file count:")
for k, v in by_count.most_common(15):
    print("  %7d files  %s  %s" % (v, gb(by_top[k]), k))
# Second level, so a folder full of small files (code checkouts, caches) is easy to spot
by_count2 = collections.Counter("/".join(i["Path"].split("/")[:2]) for i in real if i["Path"].count("/") >= 2)
print("\nSecond-level folders by file count:")
for k, v in by_count2.most_common(15):
    print("  %7d files  %s" % (v, k))
print("\nLargest 30 files:")
for i in sorted(real, key=lambda i: -i["Size"])[:30]:
    print("  %s  %s" % (gb(i["Size"]), i["Path"]))
takeout = [i for i in real if i["Path"].startswith("Takeout/")]
if takeout:
    print("\nTakeout archives: %d, %s" % (len(takeout), gb(sum(i["Size"] for i in takeout))))
with open(os.environ["TOTAL_FILE"], "a") as f:
    f.write("%s %d\n" % (os.environ["R"], total))
'
  echo
done

echo "================ capacity gate (design §10) ================"
python3 - "$TOTAL_FILE" <<'PY'
import sys
rows = [l.split() for l in open(sys.argv[1]) if l.strip()]
total = sum(int(b) for _, b in rows)
for r, b in rows:
    print("  %-16s %8.2f GB" % (r, int(b) / 1e9))
print("  %-16s %8.2f GB   (Google Photos not included: measured from the first Takeout)" % ("TOTAL", total / 1e9))
for name, cap in (("primary (SMB zvol, free)", 170e9), ("secondary (SSK, usable)", 220e9)):
    print("  %-26s %6.0f GB  -> %s" % (name, cap / 1e9, "fits" if total <= cap else "DOES NOT FIT"))
PY
} | tee "$REPORT"
echo
echo "Report saved on host: $REPORT"
EOF
