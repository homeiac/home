"""Live progress metrics for long index runs (backfill), written as a Prometheus textfile (issue #212).

Used by adapters/gphotos.py (`--prom FILE --expected N`). Rate-limited (default every 2 s), atomic (tmp + rename), never raises:
a metrics problem must not fail an index run. export-metrics.py imports BACKFILL_HELP so the dashboard/alert test knows these names.
"""
import os
import time

BACKFILL_HELP = {
    "knowledge_index_backfill_running": ("gauge", "1 while the run is in progress (0 when done or failed)"),
    "knowledge_index_backfill_phase": ("gauge", "current phase (listing, reading, writing, versions, done, failed): 1 for the active one"),
    "knowledge_index_backfill_expected_files": ("gauge", "files the ingest ledger says the library holds (for progress while listing)"),
    "knowledge_index_backfill_files_listed": ("gauge", "files found so far while listing the library"),
    "knowledge_index_backfill_files_total": ("gauge", "files to read (known once listing is done)"),
    "knowledge_index_backfill_files_done": ("gauge", "files read so far"),
    "knowledge_index_backfill_sidecars_done": ("gauge", "sidecars parsed so far"),
    "knowledge_index_backfill_bytes_done": ("gauge", "bytes of files seen so far"),
    "knowledge_index_backfill_parse_errors": ("gauge", "sidecars that failed to parse so far"),
    "knowledge_index_backfill_progress_ratio": ("gauge", "0..1: files read / total while reading, files listed / expected while listing"),
    "knowledge_index_backfill_rate_files_per_second": ("gauge", "files per second over the reading phase"),
    "knowledge_index_backfill_eta_seconds": ("gauge", "estimated seconds left in the reading phase"),
    "knowledge_index_backfill_started_timestamp_seconds": ("gauge", "unix time the run started"),
    "knowledge_index_backfill_updated_timestamp_seconds": ("gauge", "unix time of the last progress update"),
    "knowledge_index_backfill_finished_timestamp_seconds": ("gauge", "unix time the run finished (done or failed), 0 while running"),
    "knowledge_index_backfill_process_elapsed_seconds": ("gauge", "seconds the backfill process has been running (any run, instrumented or not)"),
    "knowledge_index_backfill_process_read_bytes": ("gauge", "bytes the backfill process read from disk so far"),
    "knowledge_index_backfill_process_cpu_seconds": ("gauge", "CPU seconds used by the backfill process"),
}
PHASES = ("listing", "reading", "writing", "versions", "done", "failed")


class Progress:
    def __init__(self, unit, prom_path=None, expected=0, every=2.0):
        self.unit, self.path, self.every = unit, prom_path, every
        self.s = {"phase": "listing", "listed": 0, "total": 0, "done": 0, "sidecars": 0, "bytes": 0, "errors": 0,
                  "expected": int(expected or 0), "started": time.time(), "read_start": None, "finished": 0}
        self._last = 0.0
        self.write(force=True)

    def update(self, force=False, **kw):
        s = self.s
        if kw.get("phase") == "reading" and s["read_start"] is None:
            s["read_start"] = time.time()
        s.update(kw)
        self.write(force)

    def finish(self, ok=True):
        self.s["finished"] = time.time()
        self.update(force=True, phase="done" if ok else "failed")

    def render(self):
        s, now = self.s, time.time()
        reading = s["phase"] in ("reading", "writing", "versions", "done")
        ratio = (s["done"] / s["total"]) if s["total"] and reading else (min(s["listed"] / s["expected"], 1.0) if s["expected"] else 0.0)
        if s["phase"] == "done":
            ratio = 1.0
        elapsed = max((s["finished"] or now) - (s["read_start"] or now), 1e-9)
        rate = s["done"] / elapsed if s["read_start"] and s["done"] else 0.0
        eta = (s["total"] - s["done"]) / rate if rate and s["total"] and s["phase"] == "reading" else 0.0
        vals = {"running": 0 if s["phase"] in ("done", "failed") else 1, "expected_files": s["expected"], "files_listed": s["listed"],
                "files_total": s["total"], "files_done": s["done"], "sidecars_done": s["sidecars"], "bytes_done": s["bytes"],
                "parse_errors": s["errors"], "progress_ratio": round(ratio, 5), "rate_files_per_second": round(rate, 2), "eta_seconds": round(eta),
                "started_timestamp_seconds": round(s["started"]), "updated_timestamp_seconds": round(now), "finished_timestamp_seconds": round(s["finished"])}
        lines = []
        for k, v in vals.items():
            n = "knowledge_index_backfill_" + k
            lines += ["# HELP %s %s" % (n, BACKFILL_HELP[n][1]), "# TYPE %s gauge" % n, '%s{unit="%s"} %s' % (n, self.unit, v)]
        n = "knowledge_index_backfill_phase"
        lines += ["# HELP %s %s" % (n, BACKFILL_HELP[n][1]), "# TYPE %s gauge" % n]
        lines += ['%s{unit="%s",phase="%s"} %d' % (n, self.unit, p, 1 if p == s["phase"] else 0) for p in PHASES]
        return "\n".join(lines) + "\n"

    def write(self, force=False):
        if not self.path or (not force and time.time() - self._last < self.every):
            return
        self._last = time.time()
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(self.render())
            os.chmod(tmp, 0o644)
            os.replace(tmp, self.path)
        except OSError:
            pass
