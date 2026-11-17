#!/bin/bash
# Test export-metrics.py, the dashboard generator and the alert rules against a fake Takeout library (local)
#
# Usage: ./test-metrics.sh          needs python3 with duckdb and pyyaml (PYTHON=... to override)
#
# Asserts: exposition format is valid, the numbers match the index, a missing index reports exporter_success 0 (and still writes),
# the committed dashboard ConfigMap equals what gen-dashboard.py generates, and every metric used by the dashboard and the
# alert rules is one this exporter (or an allow-listed external exporter) provides.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PYTHON="${PYTHON:-python3}"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
LIB="$W/ds/library"; L="$LIB/Google Photos"; IDX="$W/idx"; PH="$W/ds"
mkdir -p "$L/Photos from 2019" "$L/Photos from 2023" "$L/Trip Album" "$IDX"
side() { printf '{"title": "%s", "creationTime": {"timestamp": "%s"}, "photoTakenTime": {"timestamp": "%s"}}' "$2" "$3" "$3" > "$1"; }
OLD=1546300800; NEW=1672531200
echo old > "$L/Photos from 2019/old.jpg"; side "$L/Photos from 2019/old.jpg.json" old.jpg $OLD
echo new > "$L/Photos from 2023/new.jpg"; side "$L/Photos from 2023/new.jpg.json" new.jpg $NEW
echo none > "$L/Photos from 2019/nosidecar.png"
cp "$L/Photos from 2023/new.jpg" "$L/Trip Album/new.jpg"; side "$L/Trip Album/new.jpg.json" new.jpg $NEW
echo '{bad' > "$L/Photos from 2023/broken.jpg.json"
printf 'a.tgz\t1\tx\t3\t2026-01-01\nb.tgz\t1\tx\t3\t2026-01-02\n' > "$PH/_ingested.tsv"
printf 'takeout-x\t2026-11-17\n' > "$PH/_index_pending.tsv"
echo '{"finished": "2026-11-16T16:09:35+00:00", "status": "ok"}' > "$PH/_last-run.json"
"$PYTHON" "$HERE/adapters/gphotos.py" emit u1 "$LIB" "$IDX" >/dev/null
"$PYTHON" "$HERE/kidx.py" rebuild "$IDX" >/dev/null

P=0 F=0
ok()   { echo "  PASS: $1"; P=$((P+1)); }
bad()  { echo "  FAIL: $1"; F=$((F+1)); }
check() { [[ "$2" == "$3" ]] && ok "$1" || bad "$1 (got '$2', want '$3')"; }
m() { grep -E "^$1( |\{)" "$W/out.prom" | sed -E 's/^[^ ]+ //' | head -1; }    # value of first sample of metric $1
ml() { grep -F "$1" "$W/out.prom" | head -1 | sed -E 's/^[^ ]+ //'; }          # value of the sample containing label text $1

echo "-- exporter"
"$PYTHON" "$HERE/export-metrics.py" --index "$IDX" --photos "$PH" --out "$W/out.prom" --enrichers e1
check "success"                          "$(m knowledge_index_exporter_success)" 1
check "media files"                      "$(ml 'knowledge_index_files{kind="media"')" 4
check "sidecar files"                    "$(ml 'knowledge_index_files{kind="sidecar"')" 4
check "sidecar rows"                     "$(m knowledge_index_sidecars)" 4
check "sidecar parse errors"             "$(m knowledge_index_sidecar_parse_errors)" 1
check "units"                            "$(m knowledge_index_units)" 1
check "pending units"                    "$(m knowledge_index_pending_units)" 1
check "ingest archives"                  "$(m gphotos_ingest_archives)" 2
check "ingest last ok"                   "$(m gphotos_ingest_last_ok)" 1
check "media without sidecar"            "$(m gphotos_media_without_sidecar)" 1
check "album duplicate"                  "$(m gphotos_album_dup_files)" 1
check "quota media (2023 + nosidecar)"   "$(ml 'gphotos_quota_files{kind="media"')" 2
check "quota 2023 by year"               "$(ml 'gphotos_quota_media_files_by_year{year="2023"')" 1
check "queue for requested enricher"     "$(ml 'media_summaries_queue{enricher="e1"')" 4
check "parquet files counted"            "$(ml 'knowledge_index_parquet_files{table="gphotos_sidecars"')" 1
check "valid exposition format"          "$(grep -vE '^(#|[a-z_]+(\{[^}]*\})? -?[0-9.e+-]+$)' "$W/out.prom" | wc -l | tr -d ' ')" 0
check "every metric has HELP and TYPE"   "$(grep -c '^# HELP' "$W/out.prom")" "$(grep -c '^# TYPE' "$W/out.prom")"
check "no .tmp left"                     "$(ls "$W" | grep -c '\.tmp$' || true)" 0

echo "-- missing index still writes a health metric"
"$PYTHON" "$HERE/export-metrics.py" --index "$W/nonexistent" --photos "$PH" --out "$W/out2.prom" 2>/dev/null
check "success 0"                        "$(grep '^knowledge_index_exporter_success ' "$W/out2.prom" | cut -d' ' -f2)" 0

echo "-- summaries rows appear"
mkdir -p "$IDX/summaries/e1"
"$PYTHON" - "$IDX" <<'PY'
import duckdb, sys
c = duckdb.connect()
c.execute("""CREATE TABLE s AS SELECT 'gphotos' AS source, 'Google Photos/Photos from 2023/new.jpg' AS path, size_bytes, 'e1' AS enricher, 'm' AS model, 'p1' AS prompt_version,
  'x' AS summary, ['t'] AS tags, NULL::INTEGER AS frames_sampled, NULL::DOUBLE AS duration_s, 'ok' AS status, NULL::VARCHAR AS error, now()::TIMESTAMP AS created_at
  FROM read_parquet('%s/files/gphotos/u1.parquet') WHERE name = 'new.jpg' AND path NOT LIKE '%%Trip%%'""" % sys.argv[1])
c.execute("COPY s TO '%s/summaries/e1/b1.parquet' (FORMAT parquet)" % sys.argv[1])
PY
"$PYTHON" "$HERE/kidx.py" rebuild "$IDX" >/dev/null
"$PYTHON" "$HERE/export-metrics.py" --index "$IDX" --photos "$PH" --out "$W/out.prom"
check "ok rows"                          "$(ml 'media_summaries_rows{enricher="e1",status="ok"')" 1
check "queue shrinks"                    "$(ml 'media_summaries_queue{enricher="e1"')" 3
check "last batch time present"          "$(grep -c '^media_summaries_last_batch_timestamp_seconds' "$W/out.prom")" 1

echo "-- dashboard and alerts (as code)"
"$PYTHON" "$HERE/gen-dashboard.py" > "$W/dash.yaml"
D="$REPO/gitops/clusters/homelab/infrastructure/monitoring/dashboards/knowledge-index.yaml"
diff -q "$W/dash.yaml" "$D" >/dev/null && ok "committed dashboard == generated" || bad "committed dashboard differs (run: gen-dashboard.py > $D)"
"$PYTHON" - "$HERE" "$REPO" "$W" <<'PY' && ok "dashboard + alert metrics all exist" || bad "unknown metric in dashboard/alerts"
import json, re, subprocess, sys, yaml
here, repo, w = sys.argv[1:4]
have = set(subprocess.check_output([sys.executable, here + "/export-metrics.py", "--list-metrics"], text=True).split())
external = {"node_boot_time_seconds", "nvme_power_cycles_total", "nvme_media_errors_total", "up"}
mon = repo + "/gitops/clusters/homelab/infrastructure/monitoring/"
exprs = []
d = yaml.safe_load(open(mon + "dashboards/knowledge-index.yaml"))
j = json.loads(list(d["data"].values())[0])
for p in j["panels"]:
    exprs += [t["expr"] for t in p.get("targets", [])]
r = yaml.safe_load(open(mon + "knowledge-index-alerting-rules.yaml"))
exprs += [x["expr"] for g in r["spec"]["groups"] for x in g["rules"]]
names = {n for e in exprs for n in re.findall(r"[a-zA-Z_:][a-zA-Z0-9_:]*(?=\s*[{\[(]|\s|$|\)|,)", e)}
metrics = {n for n in names if re.match(r"^(knowledge_index_|gphotos_|media_summaries_|smart_|node_|nvme_|up$)", n)}
missing = metrics - have - external
if missing:
    print("  missing:", sorted(missing)); sys.exit(1)
PY

echo "passed $P, failed $F"
exit $(( F > 0 ))
