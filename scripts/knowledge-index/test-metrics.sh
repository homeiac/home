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
check "ok items by kind (photo)"         "$(ml 'media_summaries_ok_items{enricher="e1",kind="photo"')" 1
check "query seconds measured"           "$([[ "$(ml 'knowledge_index_query_seconds{query="quota"')" != "" ]] && echo yes)" yes
check "last batch time present"          "$(grep -c '^media_summaries_last_batch_timestamp_seconds' "$W/out.prom")" 1

echo "-- Ollama metrics from a stub /api/ps"
cat > "$W/ollama_stub.py" <<'PY'
import http.server, json, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = {"/api/ps": {"models": [{"name": "gemma4:e2b", "size": 7800000000, "size_vram": 2000000000, "expires_at": "2026-11-17T21:00:00-08:00"}]},
                "/api/tags": {"models": [{"name": "a"}, {"name": "gemma4:e2b"}]}}.get(self.path, {})
        out = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass
s = http.server.HTTPServer(("127.0.0.1", 0), H)
open(sys.argv[1], "w").write(str(s.server_port)); s.serve_forever()
PY
"$PYTHON" "$W/ollama_stub.py" "$W/oport" & echo $! >> "$W/ollama.pid"
for _ in $(seq 1 50); do [[ -s "$W/oport" ]] && break; sleep 0.1; done
"$PYTHON" "$HERE/export-metrics.py" --index "$IDX" --photos "$PH" --out "$W/oll.prom" --ollama-url "http://127.0.0.1:$(cat "$W/oport")"
og() { grep -E "^$1(\{| )" "$W/oll.prom" | head -1 | sed -E 's/^[^ ]+ //'; }
check "ollama up"                        "$(og ollama_up)" 1
check "models pulled"                    "$(og ollama_models_pulled)" 2
check "loaded model present"             "$(og ollama_model_loaded)" 1
check "gpu fraction = vram/size"         "$(og ollama_model_gpu_fraction)" 0.2564
"$PYTHON" "$HERE/export-metrics.py" --index "$IDX" --photos "$PH" --out "$W/oll2.prom" --ollama-url "http://127.0.0.1:1"
check "unreachable ollama -> up 0"       "$(grep '^ollama_up ' "$W/oll2.prom" | cut -d' ' -f2)" 0
kill "$(cat "$W/ollama.pid")" 2>/dev/null || true

echo "-- backfill progress metrics (progress.py via adapter --prom)"
PROM="$W/backfill.prom"
"$PYTHON" "$HERE/adapters/gphotos.py" emit bf1 "$LIB" "$W/idx2" --prom "$PROM" --expected 20 >/dev/null
pm() { grep -E "^$1(\{| )" "$PROM" | grep -F "$2" | head -1 | sed -E 's/^[^ ]+ //'; }
check "finished: phase done"             "$(pm knowledge_index_backfill_phase 'phase="done"')" 1
check "finished: not running"            "$(pm knowledge_index_backfill_running '')" 0
check "finished: files done = total"     "$(pm knowledge_index_backfill_files_done '')" "$(pm knowledge_index_backfill_files_total '')"
check "files total matches library"      "$(pm knowledge_index_backfill_files_total '')" "$(find "$LIB" -type f | wc -l | tr -d ' ')"
check "progress ratio 1"                 "$(pm knowledge_index_backfill_progress_ratio '')" 1.0
check "parse errors counted"             "$(pm knowledge_index_backfill_parse_errors '')" 1
check "expected passed through"          "$(pm knowledge_index_backfill_expected_files '')" 20
check "finished timestamp set"           "$([[ "$(pm knowledge_index_backfill_finished_timestamp_seconds '')" -gt 0 ]] && echo yes)" yes
check "progress file format valid"       "$(grep -vE '^(#|[a-z_]+(\{[^}]*\})? -?[0-9.e+-]+$)' "$PROM" | wc -l | tr -d ' ')" 0
mkdir -p "$W/ro"; chmod 555 "$W/ro"
"$PYTHON" "$HERE/adapters/gphotos.py" emit bf2 "$LIB" "$W/ro/idx" --prom "$W/fail.prom" >/dev/null 2>&1 || true
chmod 755 "$W/ro"
check "failed run: phase failed"         "$(grep -E '^knowledge_index_backfill_phase.*phase="failed"' "$W/fail.prom" | sed -E 's/^[^ ]+ //')" 1
check "failed run: not running"          "$(grep -E '^knowledge_index_backfill_running' "$W/fail.prom" | sed -E 's/^[^ ]+ //')" 0
"$PYTHON" - "$HERE" "$W" <<'PY' && ok "live render: reading phase, ratio, rate, eta" || bad "live render wrong"
import sys, time
sys.path.insert(0, sys.argv[1])
from progress import Progress
p = Progress("u", sys.argv[2] + "/live.prom", expected=1000, every=0)
p.update(phase="reading", total=100, done=0)
p.s["read_start"] = time.time() - 10
p.update(done=50)
txt = p.render()
g = lambda k: float([l for l in txt.splitlines() if l.startswith("knowledge_index_backfill_" + k + "{")][0].split()[-1])
assert g("progress_ratio") == 0.5 and g("running") == 1 and 4.5 < g("rate_files_per_second") < 5.5 and 8 <= g("eta_seconds") <= 12, txt
assert 'phase="reading"} 1' in txt and 'phase="listing"} 0' in txt
q = Progress("u", None)   # no file: must not raise
q.update(phase="reading", total=1, done=1); q.finish()
PY

echo "-- dashboard and alerts (as code)"
"$PYTHON" "$HERE/gen-dashboard.py" > "$W/dash.yaml"
D="$REPO/gitops/clusters/homelab/apps/photo-enrichment/knowledge-index-dashboard.yaml"
diff -q "$W/dash.yaml" "$D" >/dev/null && ok "committed dashboard == generated" || bad "committed dashboard differs (run: gen-dashboard.py > $D)"
"$PYTHON" - "$HERE" "$REPO" "$W" <<'PY' && ok "dashboard + alert metrics all exist" || bad "unknown metric in dashboard/alerts"
import json, re, runpy, subprocess, sys, yaml
here, repo, w = sys.argv[1:4]
have = set(subprocess.check_output([sys.executable, here + "/export-metrics.py", "--list-metrics"], text=True).split())
sys.path.insert(0, here)
import pathlib
from photo_enrichment.metrics import HELP as PHOTO_HELP
have.update("photo_enrichment_" + name for name in PHOTO_HELP)
have.update("photo_review_" + name for name in PHOTO_HELP)
have.update(re.findall(r"# HELP (photo_[a-z_]+) ", pathlib.Path(here + "/photo_enrichment/snapshots.py").read_text()))
have.update(re.findall(r"# HELP (photo_[a-z_]+) ", pathlib.Path(here + "/photo_enrichment/triage.py").read_text()))
have.update({"immich_queue_jobs", "immich_jobs_asset_generate_thumbnails_success_total", "immich_jobs_ocr_success_total", "immich_jobs_ocr_failed_total"})
have.update({"immich_jobs_asset_encode_video_success_total", "immich_jobs_asset_encode_video_failed_total"})
have.update({"immich_sync_available_summaries", "immich_sync_assets"})
have.add("photo_app_db_duration_seconds_bucket")  # OTel histogram, checked against the live collector.
have.update("photo_frigate_" + name for name in runpy.run_path(here + "/export-frigate-metrics.py")["HELP"])
external = {"node_boot_time_seconds", "nvme_power_cycles_total", "nvme_media_errors_total", "up", "kube_deployment_spec_replicas", "kube_deployment_status_replicas_available"}
external.update(re.findall(r"f'((?:knowledge_index_luna_)[a-z_]+)(?: |\{)", pathlib.Path(here + "/luna-backfill/host.py").read_text()))
external.update({"node_systemd_unit_state", "node_cpu_seconds_total", "node_disk_io_time_seconds_total",
                 "node_memory_MemAvailable_bytes", "node_memory_MemTotal_bytes",
                 "node_uname_info", "node_textfile_mtime_seconds"})
external.update(f"node_pressure_{resource}_waiting_seconds_total" for resource in ("cpu", "memory", "io"))
external.update(f"node_network_{direction}_{kind}_total" for direction in ("receive", "transmit") for kind in ("drop", "errs"))
mon = repo + "/gitops/clusters/homelab/infrastructure/monitoring/"
exprs = []
d = yaml.safe_load(open(repo + "/gitops/clusters/homelab/apps/photo-enrichment/knowledge-index-dashboard.yaml"))
j = json.loads(list(d["data"].values())[0])
for p in j["panels"]:
    exprs += [t["expr"] for t in p.get("targets", [])]
r = yaml.safe_load(open(mon + "knowledge-index-alerting-rules.yaml"))
exprs += [x["expr"] for g in r["spec"]["groups"] for x in g["rules"]]
names = {n for e in exprs for n in re.findall(r"[a-zA-Z_:][a-zA-Z0-9_:]*(?=\s*[{\[(]|\s|$|\)|,)", e)}
metrics = {n for n in names if re.match(r"^(immich_|knowledge_index_|gphotos_|media_summaries_|media_pipeline_|photo_enrichment_|photo_review_|photo_snapshot_|photo_pipeline_|photo_frigate_|photo_app_|smart_|node_|nvme_|ollama_|DCGM_|kube_|up$)", n)}
missing = {m for m in metrics - have - external if not m.startswith("DCGM_FI_DEV_")}   # DCGM names come from the NVIDIA exporter (checked live by check-promql.sh)
if missing:
    print("  missing:", sorted(missing)); sys.exit(1)
PY

echo "passed $P, failed $F"
exit $(( F > 0 ))
