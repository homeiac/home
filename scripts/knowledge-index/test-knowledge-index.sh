#!/bin/bash
# Test the knowledge index (adapters/gphotos.py + knowledge.sql + kidx.py) on a fake Takeout library (local)
#
# Usage: ./test-knowledge-index.sh        needs python3 with duckdb (PYTHON=/path/to/python to override)
#
# Same fixture as scripts/backup/test-gphotos-quota-list.sh plus: a corrupt sidecar, a sidecar delivered by
# a different archive than its photo, a re-run of a unit (no duplicate rows) and a .versions copy. The quota
# view must select exactly what the oracle (scripts/backup/host/gphotos-quota-list.py) selects.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
ORACLE="$HERE/../backup/host/gphotos-quota-list.py"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
LIB="$W/ds/library"; L="$LIB/Google Photos"; IDX="$W/idx"
mkdir -p "$L/Photos from 2019" "$L/Photos from 2023" "$L/Trip Album" "$IDX" "$W/ds/.versions/2026-11-16/Google Photos/Photos from 2023"
side() { printf '{"title": "%s", "creationTime": {"timestamp": "%s"}, "photoTakenTime": {"timestamp": "%s"}, "geoData": {"latitude": %s, "longitude": %s}}' "$2" "$3" "$3" "${4:-0.0}" "${5:-0.0}" > "$1"; }
OLD=1546300800   # 2019-01-01
NEW=1672531200   # 2023-01-01
echo old  > "$L/Photos from 2019/old.jpg";  side "$L/Photos from 2019/old.jpg.json" old.jpg $OLD
echo new  > "$L/Photos from 2023/new.jpg";  side "$L/Photos from 2023/new.jpg.supplemental-metadata.json" new.jpg $NEW 37.5 -122.1
echo trunc > "$L/Photos from 2023/a_long_name.mp4"; side "$L/Photos from 2023/a_long_name.mp4.supplemental-me.json" a_long_name.mp4 $NEW
echo dup1 > "$L/Photos from 2023/IMG(1).jpg"; side "$L/Photos from 2023/IMG.jpg.supplemental-metadata(1).json" IMG.jpg $NEW
echo edit > "$L/Photos from 2023/new-edited.jpg"
echo none > "$L/Photos from 2019/nosidecar.png"
echo doc  > "$L/Photos from 2019/notes.txt"
cp "$L/Photos from 2023/new.jpg" "$L/Trip Album/new.jpg"; side "$L/Trip Album/new.jpg.json" new.jpg $NEW
echo oldalb > "$L/Trip Album/oldalbum.jpg"; side "$L/Trip Album/oldalbum.jpg.json" oldalbum.jpg $OLD
echo orphan > "$L/Photos from 2023/late.jpg"                     # its sidecar arrives with another archive
echo '{not json' > "$L/Photos from 2023/broken.jpg.json"
echo ver > "$W/ds/.versions/2026-11-16/Google Photos/Photos from 2023/new.jpg"

P=0 F=0
ok()   { echo "  PASS: $1"; P=$((P+1)); }
bad()  { echo "  FAIL: $1"; F=$((F+1)); }
check() { [[ "$2" == "$3" ]] && ok "$1" || bad "$1 (got '$2', want '$3')"; }
q() { "$PYTHON" "$HERE/kidx.py" query "$IDX" "$1" | tail -n +2; }

# archive A delivers everything except late.jpg's sidecar; archive B delivers that sidecar
LATE="Google Photos/Photos from 2023/late.jpg.json"
side "$LIB/$LATE" late.jpg $NEW
( cd "$LIB" && find . -type f | sed 's|^\./||' | grep -vxF "$LATE" ) > "$W/paths-a"
echo "$LATE" > "$W/paths-b"

"$PYTHON" "$HERE/adapters/gphotos.py" emit takeout-a "$LIB" "$IDX" --paths-from "$W/paths-a" --versions "$W/ds/.versions" | sed 's/^/  adapter A: /'
"$PYTHON" "$HERE/adapters/gphotos.py" emit takeout-b "$LIB" "$IDX" --paths-from "$W/paths-b" | sed 's/^/  adapter B: /'
"$PYTHON" "$HERE/kidx.py" rebuild "$IDX" | sed 's/^/  /'

NJSON="$(find "$LIB" -name '*.json' | wc -l | tr -d ' ')"
echo "-- schema and counts"
check "files rows (library, no versions)"  "$(q "SELECT count(*) FROM gphotos_files")" "$(find "$LIB" -type f | wc -l | tr -d ' ')"
check "versions accounted separately"      "$(q "SELECT count(*) FROM gphotos_versions")" 1
check "sidecar rows = .json files"         "$(q "SELECT count(*) FROM gphotos_sidecars")" "$NJSON"
check "kind sidecar"                       "$(q "SELECT count(*) FROM gphotos_files WHERE kind='sidecar'")" "$NJSON"
check "kind other (txt)"                   "$(q "SELECT count(*) FROM gphotos_files WHERE kind='other'")" 1
check "corrupt sidecar -> parse_error row" "$(q "SELECT count(*) FROM gphotos_sidecars WHERE parse_error IS NOT NULL AND title IS NULL")" 1
check "ext lower-case no dot"              "$(q "SELECT ext FROM gphotos_files WHERE path LIKE '%2023/new.jpg'")" jpg
check "path relative to source root"       "$(q "SELECT count(*) FROM files WHERE path='Google Photos/Photos from 2023/new.jpg'")" 1

echo "-- sidecar matching across archives"
check "late.jpg sidecar from other archive" "$(q "SELECT upload_ts FROM gphotos_media WHERE name='late.jpg'")" $NEW
check "-edited shares original's sidecar"   "$(q "SELECT upload_ts FROM gphotos_media WHERE name='new-edited.jpg'")" $NEW
check "is_edited"                           "$(q "SELECT is_edited FROM gphotos_media WHERE name='new-edited.jpg'")" True
check "(n) duplicate sidecar"               "$(q "SELECT upload_ts FROM gphotos_media WHERE name='IMG(1).jpg'")" $NEW
check "has_geo true / false"                "$(q "SELECT has_geo FROM gphotos_media WHERE path LIKE '%2023/new.jpg'")/$(q "SELECT has_geo FROM gphotos_media WHERE name='old.jpg'")" True/False
check "album name"                          "$(q "SELECT album FROM gphotos_media WHERE path LIKE '%Trip Album/oldalbum.jpg'")" "Trip Album"

echo "-- quota view == oracle"
mkdir -p "$W/oracle/gphotos" && ln -s "$LIB" "$W/oracle/gphotos/library"
python3 "$ORACLE" "$W/oracle" 2>/dev/null | sed 's|^gphotos/library/||' | sort > "$W/want"
q "SELECT path FROM gphotos_quota ORDER BY path" | sort > "$W/got"
if diff "$W/want" "$W/got" >/dev/null; then ok "quota set equals gphotos-quota-list.py ($(wc -l < "$W/got" | tr -d ' ') paths)"; else bad "quota set differs"; diff "$W/want" "$W/got" | head; fi
check "album dup in gphotos_album_dup"      "$(q "SELECT count(*) FROM gphotos_album_dup")" 1
check "no-sidecar reason"                   "$(q "SELECT count(*) FROM gphotos_quota WHERE quota_reason='no-sidecar'")" 2
check "copies view exists (empty, typed)"   "$(q "SELECT count(*) FROM copies")" 0

echo "-- idempotent re-run replaces its parquet"
before="$(q "SELECT count(*) FROM files")"
"$PYTHON" "$HERE/adapters/gphotos.py" emit takeout-a "$LIB" "$IDX" --paths-from "$W/paths-a" --versions "$W/ds/.versions" >/dev/null
"$PYTHON" "$HERE/kidx.py" rebuild "$IDX" >/dev/null
check "row count unchanged after re-emit"   "$(q "SELECT count(*) FROM files")" "$before"
check "parquet files: a, a.versions, b"     "$(ls "$IDX/files/gphotos/"*.parquet | wc -l | tr -d ' ')" 3
check "no .tmp left behind"                 "$(find "$IDX" -name '*.tmp' | wc -l | tr -d ' ')" 0

echo "-- a path re-delivered by a later unit wins (no duplicate rows)"
sleep 1
echo "Google Photos/Photos from 2023/new.jpg" > "$W/paths-c"
"$PYTHON" "$HERE/adapters/gphotos.py" emit takeout-c "$LIB" "$IDX" --paths-from "$W/paths-c" >/dev/null
"$PYTHON" "$HERE/kidx.py" rebuild "$IDX" >/dev/null
check "one row per path"                    "$(q "SELECT count(*) FROM files WHERE path='Google Photos/Photos from 2023/new.jpg'")" 1
check "latest unit"                         "$(q "SELECT unit FROM files WHERE path='Google Photos/Photos from 2023/new.jpg'")" takeout-c

echo "-- enrichment hook: GPU summaries slot in without touching the facts"
check "summaries view empty and typed"     "$(q "SELECT count(*) FROM media_summaries")" 0
Q0="$(q "SELECT count(*) FROM gphotos_to_summarize('vlm-v1')")"
check "queue = all media (kind media)"     "$Q0" "$(q "SELECT count(*) FROM gphotos_media WHERE kind='media'")"
"$PYTHON" - "$IDX" <<'PY'
import duckdb, sys
idx = sys.argv[1]
import os; os.makedirs(idx + "/summaries/vlm-v1", exist_ok=True)
c = duckdb.connect()
c.execute("""CREATE TABLE s AS SELECT 'gphotos' AS source, 'Google Photos/Photos from 2023/new.jpg' AS path, size_bytes, 'vlm-v1' AS enricher,
  'test-model' AS model, 'p1' AS prompt_version, 'a red car' AS summary, ['car'] AS tags, 1 AS frames_sampled, NULL::DOUBLE AS duration_s,
  'ok' AS status, NULL::VARCHAR AS error, now()::TIMESTAMP AS created_at FROM read_parquet('%s/files/gphotos/takeout-c.parquet')""" % idx)
c.execute("COPY s TO '%s/summaries/vlm-v1/batch1.parquet' (FORMAT parquet)" % idx)
PY
"$PYTHON" "$HERE/kidx.py" rebuild "$IDX" >/dev/null
check "summary stored and readable"        "$(q "SELECT summary FROM media_summaries")" "a red car"
check "summarized file leaves the queue"   "$(q "SELECT count(*) FROM gphotos_to_summarize('vlm-v1')")" "$((Q0 - 1))"

echo "-- ingest hook (index-unit.sh): success clears pending, failure never touches library/ledger"
H="$W/hook"; mkdir -p "$H/ds" "$H/idx" "$H/ki/adapters"
cp -R "$LIB" "$H/ds/library"; echo "ledger-line" > "$H/ds/_ingested.tsv"
cp "$HERE/kidx.py" "$HERE/knowledge.sql" "$H/ki/"; cp "$HERE/adapters/gphotos.py" "$H/ki/adapters/"
printf 'takeout-x\told\n' > "$H/ds/_index_pending.tsv"
( cd "$H/ds/library" && find . -type f | sed 's|^\./||' ) > "$H/moved"
before_lib="$(find "$H/ds/library" -type f | wc -l | tr -d ' ')"
KI_DIR="$H/ki" KI_PYTHON="$PYTHON" "$HERE/index-unit.sh" takeout-x "$H/moved" "$H/ds" "$H/idx" >/dev/null 2>&1 && rc=0 || rc=$?
check "success: exit 0"                      "$rc" 0
check "success: unit removed from pending"   "$(grep -c '^takeout-x' "$H/ds/_index_pending.tsv" || true)" 0
check "success: parquet written"             "$(ls "$H/idx/files/gphotos/" | grep -c 'takeout-x.parquet')" 1
KI_DIR="$H/ki" KI_PYTHON=/nonexistent/python "$HERE/index-unit.sh" takeout-y "$H/moved" "$H/ds" "$H/idx" >/dev/null 2>&1 && rc=0 || rc=$?
check "forced failure: exit 3"               "$rc" 3
check "forced failure: marked index_pending" "$(cut -f1 "$H/ds/_index_pending.tsv")" takeout-y
check "forced failure: ledger intact"        "$(cat "$H/ds/_ingested.tsv")" ledger-line
check "forced failure: library intact"       "$(find "$H/ds/library" -type f | wc -l | tr -d ' ')" "$before_lib"

echo "passed $P, failed $F"
exit $(( F > 0 ))
