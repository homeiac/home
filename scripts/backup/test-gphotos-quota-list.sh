#!/bin/bash
# Test host/gphotos-quota-list.py on a fake Takeout library (local, python3 only)
#
# Usage: ./test-gphotos-quota-list.sh
#
# Builds a library with: an old upload (2019), a new upload (2023), a new upload with a truncated
# "supplemental-metadata" sidecar, a duplicate-numbered file "IMG(1).jpg", an "-edited" variant, a
# media file with no sidecar, and an album copy of the new photo. Asserts what is listed.

set -euo pipefail
PY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/host/gphotos-quota-list.py"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
L="$W/gphotos/library/Google Photos"
mkdir -p "$L/Photos from 2019" "$L/Photos from 2023" "$L/Trip Album"
side() { printf '{"title": "%s", "creationTime": {"timestamp": "%s"}}' "$2" "$3" > "$1"; }
OLD=1546300800   # 2019-01-01
NEW=1672531200   # 2023-01-01
echo old  > "$L/Photos from 2019/old.jpg";  side "$L/Photos from 2019/old.jpg.json" old.jpg $OLD
echo new  > "$L/Photos from 2023/new.jpg";  side "$L/Photos from 2023/new.jpg.supplemental-metadata.json" new.jpg $NEW
echo trunc > "$L/Photos from 2023/a_long_name.mp4"; side "$L/Photos from 2023/a_long_name.mp4.supplemental-me.json" a_long_name.mp4 $NEW
echo dup1 > "$L/Photos from 2023/IMG(1).jpg"; side "$L/Photos from 2023/IMG.jpg.supplemental-metadata(1).json" IMG.jpg $NEW
echo edit > "$L/Photos from 2023/new-edited.jpg"
echo none > "$L/Photos from 2019/nosidecar.png"
cp "$L/Photos from 2023/new.jpg" "$L/Trip Album/new.jpg"; side "$L/Trip Album/new.jpg.json" new.jpg $NEW
echo oldalb > "$L/Trip Album/oldalbum.jpg"; side "$L/Trip Album/oldalbum.jpg.json" oldalbum.jpg $OLD

out="$(python3 "$PY" "$W" 2>"$W/summary")"
cat "$W/summary"
P=0 F=0
has()  { grep -qxF "gphotos/library/Google Photos/$1" <<<"$out" && { echo "  PASS: lists $1"; P=$((P+1)); } || { echo "  FAIL: missing $1"; F=$((F+1)); }; }
hasnt(){ grep -qxF "gphotos/library/Google Photos/$1" <<<"$out" && { echo "  FAIL: should not list $1"; F=$((F+1)); } || { echo "  PASS: skips $1"; P=$((P+1)); }; }
has   "Photos from 2023/new.jpg"
has   "Photos from 2023/new.jpg.supplemental-metadata.json"
has   "Photos from 2023/a_long_name.mp4"
has   "Photos from 2023/IMG(1).jpg"
has   "Photos from 2023/new-edited.jpg"
has   "Photos from 2019/nosidecar.png"
hasnt "Photos from 2019/old.jpg"
hasnt "Trip Album/new.jpg"
hasnt "Trip Album/oldalbum.jpg"
echo "passed $P, failed $F"
exit $(( F > 0 ))
