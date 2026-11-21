#!/usr/bin/env python3
"""Prometheus textfile metrics for the knowledge index (issue #212). Runs on the Proxmox host, scraped via node-exporter.

Usage: export-metrics.py [--index DIR] [--photos DIR] [--out FILE] [--enrichers a,b] [--list-metrics]
  --index    knowledge-index dataset mount (default: from `zfs get mountpoint local-3TB-backup/knowledge-index`)
  --photos   photos dataset mount            (default: from `zfs get mountpoint local-3TB-backup/gphotos`)
  --out      textfile (default /var/lib/prometheus/node-exporter/knowledge_index.prom; written atomically, tmp + rename)
  --enrichers  extra enricher ids to report queue size for (also KI_ENRICHERS env, comma separated); enrichers that already have rows are always reported
  --list-metrics  print the metric names this exporter can emit and exit (used by the dashboard/alert consistency test)

Metrics: ollama_* (loaded model, GPU share), knowledge_index_* (files, bytes, sidecars, units, parquet, pending units, exporter health), gphotos_* (quota, ingest ledger),
media_summaries_* (rows by status, queue, last batch time), knowledge_index_{backfill,enrich}_active, smart_* (USB/SATA disks: pending
sectors etc., since a failing disk showed up on 2026-11-17). Missing tools (zfs, systemctl, smartctl) only omit their metrics.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from progress import BACKFILL_HELP  # noqa: E402
from enrichers.pipeline_metrics import PIPELINE_HELP  # noqa: E402

OUT_DEFAULT = "/var/lib/prometheus/node-exporter/knowledge_index.prom"
INDEX_DATASET = "local-3TB-backup/knowledge-index"
PHOTOS_DATASET = "local-3TB-backup/gphotos"

HELP = {
    "knowledge_index_exporter_success": ("gauge", "1 if the last export read the index without error"),
    "knowledge_index_exporter_duration_seconds": ("gauge", "seconds the last export took"),
    "knowledge_index_last_run_timestamp_seconds": ("gauge", "unix time of the last export"),
    "knowledge_index_files": ("gauge", "library files in the index by source and kind (media/sidecar/other)"),
    "knowledge_index_bytes": ("gauge", "bytes of library files in the index by source and kind"),
    "knowledge_index_versions_files": ("gauge", "older replaced copies kept under .versions"),
    "knowledge_index_versions_bytes": ("gauge", "bytes of .versions copies"),
    "knowledge_index_sidecars": ("gauge", "Takeout sidecar rows"),
    "knowledge_index_sidecar_parse_errors": ("gauge", "sidecars that could not be parsed"),
    "knowledge_index_units": ("gauge", "distinct ingest/backfill units in the index"),
    "knowledge_index_parquet_files": ("gauge", "parquet files per table directory"),
    "knowledge_index_dataset_bytes": ("gauge", "bytes of index files (parquet + duckdb)"),
    "knowledge_index_pending_units": ("gauge", "ingested units whose indexing failed (index_pending)"),
    "knowledge_index_backfill_active": ("gauge", "1 while the backfill systemd unit runs"),
    "knowledge_index_enrich_active": ("gauge", "1 while the summary enricher systemd unit runs"),
    "gphotos_media_without_sidecar": ("gauge", "media files with no usable Takeout sidecar"),
    "gphotos_quota_files": ("gauge", "files counting against Google quota by kind"),
    "gphotos_quota_bytes": ("gauge", "bytes counting against Google quota by kind"),
    "gphotos_quota_media_files_by_year": ("gauge", "counted files (non-sidecar) per Photos-from-YYYY folder"),
    "gphotos_quota_media_bytes_by_year": ("gauge", "counted bytes (non-sidecar) per Photos-from-YYYY folder"),
    "gphotos_album_dup_files": ("gauge", "album copies skipped as duplicates"),
    "gphotos_album_dup_bytes": ("gauge", "bytes of skipped album duplicates"),
    "gphotos_ingest_archives": ("gauge", "Takeout archives in the ingest ledger"),
    "gphotos_ingest_last_ok": ("gauge", "1 if the last ingest run finished ok"),
    "gphotos_ingest_last_finished_timestamp_seconds": ("gauge", "unix time the last ingest run finished"),
    "knowledge_index_caption_coverage": ("gauge", "Current distinct media versions by published local and Luna caption coverage"),
    "knowledge_index_caption_first_saved_last_ten_minutes": ("gauge", "Current media versions whose earliest retained successful caption timestamp falls in the last ten minutes"),
    "media_summaries_rows": ("gauge", "summary rows by enricher and status (ok/error)"),
    "media_summaries_queue": ("gauge", "media files still to summarize per enricher"),
    "ollama_up": ("gauge", "1 if the Ollama API answered"),
    "ollama_models_pulled": ("gauge", "models stored in Ollama (/api/tags)"),
    "ollama_model_loaded": ("gauge", "1 for each model currently loaded (/api/ps)"),
    "ollama_model_size_bytes": ("gauge", "memory a loaded model uses in total"),
    "ollama_model_vram_bytes": ("gauge", "part of a loaded model that sits in GPU memory"),
    "ollama_model_gpu_fraction": ("gauge", "share of a loaded model in GPU memory (1 = fully on GPU; low = slow, runs on CPU)"),
    "ollama_model_expires_timestamp_seconds": ("gauge", "unix time Ollama will unload the model"),
    "knowledge_index_query_seconds": ("gauge", "seconds a representative question took against the index (quota = the Google-quota selection)"),
    "media_summaries_ok_items": ("gauge", "successfully summarized items by enricher and kind (photo/video)"),
    "media_summaries_video_seconds": ("gauge", "total duration of summarized videos by enricher"),
    "media_summaries_last_batch_timestamp_seconds": ("gauge", "unix time of the newest summary batch per enricher"),
    "smart_pending_sectors": ("gauge", "SMART Current_Pending_Sector per disk"),
    "smart_offline_uncorrectable": ("gauge", "SMART Offline_Uncorrectable per disk"),
    "smart_reallocated_sectors": ("gauge", "SMART Reallocated_Sector_Ct per disk"),
    "smart_power_cycles": ("gauge", "SMART Power_Cycle_Count per disk"),
    "smart_passed": ("gauge", "1 if the SMART overall health assessment passed"),
}

HELP.update({k: v for k, v in BACKFILL_HELP.items() if k.startswith("knowledge_index_backfill_process_")})
PROGRESS_HELP = BACKFILL_HELP   # written live by adapters/gphotos.py --prom (progress.py); listed here so --list-metrics covers them


class Out:
    def __init__(self):
        self.rows = {}

    def add(self, name, value, **labels):
        self.rows.setdefault(name, []).append((labels, value))

    def render(self):
        lines = []
        for name in sorted(self.rows):
            typ, hlp = HELP[name]
            lines += ["# HELP %s %s" % (name, hlp), "# TYPE %s %s" % (name, typ)]
            for labels, v in self.rows[name]:
                lab = ",".join('%s="%s"' % (k, str(x).replace("\\", "\\\\").replace('"', '\\"')) for k, x in sorted(labels.items()))
                lines.append("%s%s %s" % (name, "{%s}" % lab if lab else "", repr(float(v)) if isinstance(v, float) else int(v)))
        return "\n".join(lines) + "\n"


def run(cmd, timeout=30):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def mountpoint(dataset):
    out = run(["zfs", "get", "-H", "-o", "value", "mountpoint", dataset]).strip()
    return out if out.startswith("/") else None


def dir_bytes(path):
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(path) for f in fs if os.path.isfile(os.path.join(d, f)))


def collect_coverage(o, con, index, luna_dir):
    """Use published datasets only. A path and current byte size identify a library item."""
    local_files = os.path.join(index, "summaries", "*", "*.parquet")
    luna_files = os.path.join(luna_dir, "*.parquet")
    if not glob.glob(luna_files):
        return
    rows = con.execute("""
        WITH catalog AS (SELECT DISTINCT path, size_bytes FROM gphotos_files WHERE kind='media'),
        local_results AS (
            SELECT path, size_bytes, min(created_at) AS first_local
            FROM read_parquet(?, union_by_name=true)
            WHERE source='gphotos' AND status='ok' GROUP BY path, size_bytes
        ), cloud_results AS (
            SELECT source_path AS path, size_bytes, min(finished_at) AS first_cloud
            FROM read_parquet(?, union_by_name=true)
            WHERE state='ok' GROUP BY source_path, size_bytes
        ), assets AS (
            SELECT CASE WHEN l.path IS NOT NULL AND c.path IS NOT NULL THEN 'both'
                        WHEN l.path IS NOT NULL THEN 'local_only'
                        WHEN c.path IS NOT NULL THEN 'luna_only' ELSE 'neither' END AS coverage,
                   least(first_local, first_cloud) AS first_caption
            FROM catalog LEFT JOIN local_results l USING(path, size_bytes)
            LEFT JOIN cloud_results c USING(path, size_bytes)
        ) SELECT coverage, count(*), count(*) FILTER (WHERE
                 first_caption BETWEEN timezone('UTC', current_timestamp) - INTERVAL '10 minutes'
                                   AND timezone('UTC', current_timestamp))
          FROM assets GROUP BY coverage
    """, [local_files, luna_files]).fetchall()
    counts = {coverage: count for coverage, count, _ in rows}
    for coverage in ("local_only", "luna_only", "both", "neither"):
        o.add("knowledge_index_caption_coverage", counts.get(coverage, 0), coverage=coverage)
    o.add("knowledge_index_caption_first_saved_last_ten_minutes", sum(n for _, _, n in rows))


def collect_index(o, index, enrichers):
    db = os.path.join(index, "knowledge.duckdb")
    con = duckdb.connect(db, read_only=True)
    q = lambda sql, *p: con.execute(sql, list(p)).fetchall()
    for kind, n, b in q("SELECT kind, count(*), coalesce(sum(size_bytes),0) FROM gphotos_files GROUP BY 1"):
        o.add("knowledge_index_files", n, source="gphotos", kind=kind)
        o.add("knowledge_index_bytes", b, source="gphotos", kind=kind)
    n, b = q("SELECT count(*), coalesce(sum(size_bytes),0) FROM gphotos_versions")[0]
    o.add("knowledge_index_versions_files", n); o.add("knowledge_index_versions_bytes", b)
    n, e = q("SELECT count(*), coalesce(sum(CASE WHEN parse_error IS NOT NULL THEN 1 ELSE 0 END),0) FROM gphotos_sidecars")[0]
    o.add("knowledge_index_sidecars", n); o.add("knowledge_index_sidecar_parse_errors", e)
    o.add("knowledge_index_units", q("SELECT count(DISTINCT unit) FROM files")[0][0])
    o.add("gphotos_media_without_sidecar", q("SELECT count(*) FROM gphotos_media WHERE kind = 'media' AND upload_ts IS NULL")[0][0])
    for kind, n, b in q("SELECT kind, count(*), coalesce(sum(size_bytes),0) FROM gphotos_quota GROUP BY 1"):
        o.add("gphotos_quota_files", n, kind=kind); o.add("gphotos_quota_bytes", b, kind=kind)
    # per "Photos from YYYY" folder, every non-sidecar file (same definition as the owner's per-year table / gphotos-quota-by-year.sh)
    for y, n, b in q("SELECT regexp_extract(path, 'Photos from ([0-9]{4})', 1), count(*), sum(size_bytes) FROM gphotos_quota "
                     "WHERE kind <> 'sidecar' AND regexp_matches(path, '/Photos from [0-9]{4}/') GROUP BY 1"):
        o.add("gphotos_quota_media_files_by_year", n, year=y); o.add("gphotos_quota_media_bytes_by_year", b, year=y)
    t = time.time()   # value metric: how long the "what counts against Google quota" question takes now (it took ~38 min of reading sidecars before the index)
    q("SELECT count(*) FROM gphotos_quota")
    o.add("knowledge_index_query_seconds", round(time.time() - t, 3), query="quota")
    n, b = q("SELECT count(*), coalesce(sum(size_bytes),0) FROM gphotos_album_dup")[0]
    o.add("gphotos_album_dup_files", n); o.add("gphotos_album_dup_bytes", b)
    vids = "('mp4','mov','3gp','avi','mpg','m4v')"
    for enr, kind, n, secs in q("SELECT s.enricher, CASE WHEN f.ext IN %s THEN 'video' ELSE 'photo' END, count(*), coalesce(sum(s.duration_s), 0) "
                                "FROM media_summaries s JOIN gphotos_files f ON f.path = s.path WHERE s.status = 'ok' GROUP BY 1, 2" % vids):
        o.add("media_summaries_ok_items", n, enricher=enr, kind=kind)
        if kind == "video":
            o.add("media_summaries_video_seconds", secs, enricher=enr)
    seen = set()
    for enr, status, n in q("SELECT enricher, status, count(*) FROM media_summaries GROUP BY ALL"):
        o.add("media_summaries_rows", n, enricher=enr, status=status); seen.add(enr)
    for enr in sorted(seen | set(e for e in enrichers if e)):
        o.add("media_summaries_queue", q("SELECT count(*) FROM gphotos_to_summarize(?)", enr)[0][0], enricher=enr)
        batches = glob.glob(os.path.join(index, "summaries", enr, "*.parquet"))
        if batches:
            o.add("media_summaries_last_batch_timestamp_seconds", max(os.path.getmtime(b) for b in batches), enricher=enr)
    luna_dir = os.environ.get("KI_LUNA_PARQUET", os.path.join(os.path.dirname(index), "photo-enrichment", "luna-backfill", "luna_codex_captions"))
    collect_coverage(o, con, index, luna_dir)
    con.close()


def collect_files(o, index, photos):
    for table in sorted(os.listdir(index)) if os.path.isdir(index) else []:
        p = os.path.join(index, table)
        if os.path.isdir(p):
            n = len(glob.glob(os.path.join(p, "**", "*.parquet"), recursive=True))
            o.add("knowledge_index_parquet_files", n, table=table)
    o.add("knowledge_index_dataset_bytes", dir_bytes(index))
    if photos:
        pend = os.path.join(photos, "_index_pending.tsv")
        o.add("knowledge_index_pending_units", sum(1 for ln in open(pend) if ln.strip()) if os.path.exists(pend) else 0)
        ledger = os.path.join(photos, "_ingested.tsv")
        o.add("gphotos_ingest_archives", sum(1 for ln in open(ledger) if ln.strip()) if os.path.exists(ledger) else 0)
        last = os.path.join(photos, "_last-run.json")
        if os.path.exists(last):
            try:
                d = json.load(open(last))
                o.add("gphotos_ingest_last_ok", 1 if d.get("status") == "ok" else 0)
                o.add("gphotos_ingest_last_finished_timestamp_seconds", time.mktime(time.strptime(d["finished"][:19], "%Y-%m-%dT%H:%M:%S")))
            except (ValueError, KeyError, OSError):
                pass


def collect_units(o):
    for unit, metric in (("knowledge-index-backfill", "knowledge_index_backfill_active"), ("knowledge-index-enrich", "knowledge_index_enrich_active")):
        state = run(["systemctl", "is-active", unit]).strip()
        if state:
            o.add(metric, 1 if state == "active" else 0)


def collect_backfill_process(o):
    """Process-level stats of the running backfill (works for any run, instrumented or not): elapsed, bytes read from disk, CPU."""
    cg = run(["systemctl", "show", "-p", "ControlGroup", "--value", "knowledge-index-backfill"]).strip()
    procs = os.path.join("/sys/fs/cgroup", cg.lstrip("/"), "cgroup.procs") if cg else ""
    if not procs or not os.path.exists(procs):
        return
    tck = os.sysconf("SC_CLK_TCK")
    uptime = float(open("/proc/uptime").read().split()[0])
    for pid in open(procs).read().split():
        try:
            if b"gphotos.py" not in open("/proc/%s/cmdline" % pid, "rb").read():
                continue
            st = open("/proc/%s/stat" % pid).read().rsplit(")", 1)[1].split()
            io = dict(ln.split(": ") for ln in open("/proc/%s/io" % pid).read().splitlines())
        except OSError:
            continue
        o.add("knowledge_index_backfill_process_elapsed_seconds", round(uptime - int(st[19]) / tck))
        o.add("knowledge_index_backfill_process_read_bytes", int(io["read_bytes"]))
        o.add("knowledge_index_backfill_process_cpu_seconds", round((int(st[11]) + int(st[12])) / tck, 1))
        return


def collect_ollama(o, url):
    """Ollama has no /metrics: read /api/ps (loaded models, GPU share) and /api/tags (pulled models)."""
    import urllib.request
    get = lambda path: json.load(urllib.request.urlopen(url.rstrip("/") + path, timeout=5))
    try:
        ps, tags = get("/api/ps"), get("/api/tags")
    except Exception:
        o.add("ollama_up", 0)
        return
    o.add("ollama_up", 1)
    o.add("ollama_models_pulled", len(tags.get("models", [])))
    for m in ps.get("models", []):
        name, size, vram = m.get("name", "?"), int(m.get("size", 0)), int(m.get("size_vram", 0))
        o.add("ollama_model_loaded", 1, model=name)
        o.add("ollama_model_size_bytes", size, model=name)
        o.add("ollama_model_vram_bytes", vram, model=name)
        o.add("ollama_model_gpu_fraction", round(vram / size, 4) if size else 0, model=name)
        exp = m.get("expires_at", "")
        try:
            o.add("ollama_model_expires_timestamp_seconds", time.mktime(time.strptime(exp[:19], "%Y-%m-%dT%H:%M:%S")) if exp else 0, model=name)
        except ValueError:
            pass


def collect_smart(o):
    scan = run(["smartctl", "--scan", "-j"])
    try:
        devices = json.loads(scan).get("devices", [])
    except ValueError:
        return
    for dev in devices:
        if dev.get("type") == "nvme":      # nvme-metrics.prom already covers NVMe
            continue
        d = json.loads(run(["smartctl", "-A", "-H", "-i", "-j", "-d", dev["type"], dev["name"]]) or "{}")
        lab = {"device": os.path.basename(dev["name"]), "model": d.get("model_name", "unknown")}
        if "smart_status" in d:
            o.add("smart_passed", 1 if d["smart_status"].get("passed") else 0, **lab)
        want = {"Current_Pending_Sector": "smart_pending_sectors", "Offline_Uncorrectable": "smart_offline_uncorrectable",
                "Reallocated_Sector_Ct": "smart_reallocated_sectors", "Power_Cycle_Count": "smart_power_cycles"}
        for a in (d.get("ata_smart_attributes") or {}).get("table", []):
            if a["name"] in want:
                o.add(want[a["name"]], a["raw"]["value"], **lab)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index"); ap.add_argument("--photos"); ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--enrichers", default=os.environ.get("KI_ENRICHERS", ""))
    ap.add_argument("--ollama-url", default=os.environ.get("KI_OLLAMA_URL", ""), help="Ollama base URL (env KI_OLLAMA_URL); empty = skip Ollama metrics")
    ap.add_argument("--list-metrics", action="store_true")
    a = ap.parse_args(argv)
    if a.list_metrics:
        print("\n".join(sorted(set(HELP) | set(PROGRESS_HELP) | set(PIPELINE_HELP))))
        return 0
    t0 = time.time()
    index = a.index or mountpoint(INDEX_DATASET)
    photos = a.photos or mountpoint(PHOTOS_DATASET)
    o = Out()
    ok = 0
    try:
        if not index or not os.path.exists(os.path.join(index, "knowledge.duckdb")):
            raise RuntimeError("no knowledge.duckdb under %s" % index)
        collect_index(o, index, a.enrichers.split(","))
        ok = 1
    except Exception as exc:  # exporter must never fail the timer: report health instead
        print("export error: %s" % exc, file=sys.stderr)
    if index and os.path.isdir(index):
        collect_files(o, index, photos)
    collect_units(o)
    collect_backfill_process(o)
    if a.ollama_url:
        collect_ollama(o, a.ollama_url)
    collect_smart(o)
    o.add("knowledge_index_exporter_success", ok)
    o.add("knowledge_index_exporter_duration_seconds", round(time.time() - t0, 2))
    o.add("knowledge_index_last_run_timestamp_seconds", int(time.time()))
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(o.render())
    os.chmod(tmp, 0o644)
    os.replace(tmp, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
