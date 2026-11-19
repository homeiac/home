"""Private-data-free timing and queue telemetry for the independent photo worker."""
from collections import defaultdict
from contextlib import contextmanager
import json
import logging
from pathlib import Path
import threading
import time

TITLES = {"queue": "Photo: catalog / queue", "exif": "Photo: read EXIF", "faces": "Photo: CPU faces",
          "persist": "Photo: PostgreSQL commit", "review": "Photo: save human labels",
          "frigate": "Photo: optional Frigate", "export": "Photo: export Parquet", "match": "Photo: match saved faces",
          "auto_accept": "Photo: automatically accept suggestions"}
STATES = {"idle": 0, **{stage: i for i, stage in enumerate(TITLES, 1)}, "complete": 8, "failed": 9, "match": 10, "auto_accept": 11}
EDGES = [("queue", "exif"), ("exif", "faces"), ("exif", "persist"), ("faces", "persist"),
         ("persist", "review"), ("persist", "export"), ("faces", "frigate"), ("frigate", "review"), ("review", "export"), ("faces", "match"), ("match", "review"), ("match", "auto_accept"), ("auto_accept", "export")]
HELP = {
    "jobs": ("gauge", "PostgreSQL jobs by state and oldest unfinished job age in seconds"),
    "stage_seconds_total": ("counter", "Wall time including in-flight work; shares are local to this worker, not GPU utilization"),
    "stage_completed_seconds_total": ("counter", "Duration of completed operations including failures"),
    "stage_operations_total": ("counter", "Completed operations by stage and result"),
    "worker_stage": ("gauge", "idle=0 queue=1 exif=2 faces=3 persist=4 review=5 frigate=6 export=7 complete=8 failed=9 match=10 auto_accept=11"),
    "heartbeat_timestamp_seconds": ("gauge", "Last telemetry publication Unix time"),
    "stage_started_timestamp_seconds": ("gauge", "Current stage start Unix time"),
    "running": ("gauge", "Process alive; check heartbeat to detect abrupt termination"),
    "queue": ("gauge", "Snapshot of indexed photos pending extraction or unnamed detected faces; not queue wait time"),
    "inventory": ("gauge", "Snapshot of authoritative enrichment facts; counts may decrease after correction"),
    "edge_info": ("gauge", "Possible workflow transitions; face recognition, review and export are optional"),
}


class Metrics:
    """Publish bounded stage labels atomically, with a heartbeat independent of DB locks."""
    def __init__(self, path: Path | None = None):
        self.prefix = "photo_enrichment"
        self.stages = tuple(TITLES)
        self.path = path
        self.seconds = defaultdict(float, {s: 0.0 for s in TITLES})
        self.operations = defaultdict(int)
        self.stage = "idle"
        self.started = time.time()
        self.active = None
        self.active_operations = {}
        self.running = 1
        self.jobs = {}
        self.queues = {}
        self.inventory = {}
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None

    def __enter__(self):
        if self.path:
            self.publish()
            self.thread = threading.Thread(target=self._heartbeat, daemon=True)
            self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.stop.set()
        if self.thread:
            self.thread.join()
        with self.lock:
            self.running = 0
            self.stage = "failed" if exc_type else "complete"
            self.publish()

    def _heartbeat(self) -> None:
        while not self.stop.wait(5):
            self.publish()

    @contextmanager
    def measure(self, stage: str):
        """Time operations, including background matching concurrent with review."""
        if stage not in TITLES:
            raise ValueError("Unknown telemetry stage")
        with self.lock:
            key=object()
            started=time.monotonic()
            self.active_operations[key]=(stage,started,time.time())
            self.stage, self.started, self.active = stage, time.time(), started
        status = "ok"
        try:
            yield
        except BaseException:
            status = "error"
            raise
        finally:
            with self.lock:
                self.seconds[stage] += max(0, time.monotonic() - started)
                self.operations[stage, status] += 1
                self.active_operations.pop(key)
                if self.active_operations:
                    self.stage,self.active,self.started=next(iter(self.active_operations.values()))
                else:
                    self.active = None
                    self.stage, self.started = "idle", time.time()
                self.publish()

    def snapshot(self, queues: dict, inventory: dict) -> None:
        """Store aggregate numbers only; caller owns source-DB serialization."""
        with self.lock:
            self.queues = {k: int(queues[k]) for k in ("exif", "faces", "review")}
            self.inventory = {k: int(inventory[k]) for k in ("photos", "exif", "gps", "exif_errors", "faces", "named_faces", "groups")}
            self.publish()

    def render(self) -> str:
        """Render Prometheus samples; no names, paths, locations or identities are labels."""
        with self.lock:
            rows = defaultdict(list)
            def add(name: str, value: float, **labels) -> None:
                label = "{" + ",".join(f"{k}={json.dumps(v)}" for k, v in sorted(labels.items())) + "}" if labels else ""
                rows[name].append(f"{self.prefix}_{name}{label} {value}")
            for stage, seconds in self.seconds.items():
                if stage not in self.stages: continue
                add("stage_completed_seconds_total", seconds, stage=stage)
                live = sum(max(0,time.monotonic()-start) for name,start,_ in self.active_operations.values() if name==stage)
                add("stage_seconds_total", seconds + live, stage=stage, id="photo_"+stage, title=TITLES[stage])
                for status in ("ok", "error"):
                    add("stage_operations_total", self.operations[stage, status], stage=stage, status=status)
            for name, value in (("worker_stage", STATES[self.stage]), ("heartbeat_timestamp_seconds", time.time()),
                                ("stage_started_timestamp_seconds", self.started), ("running", self.running)):
                add(name, value)
            for kind,value in self.jobs.items():
                add("jobs",float(value),kind=kind)
            for stage, value in self.queues.items():
                add("queue", value, stage=stage)
            for kind, value in self.inventory.items():
                add("inventory", value, kind=kind)
            for source, target in EDGES:
                add("edge_info", 1, id=f"photo_{source}-{target}", source="photo_"+source, target="photo_"+target)
            return "\n".join(line for name in sorted(rows) for line in
                [f"# HELP {self.prefix}_{name} {HELP[name][1]}", f"# TYPE {self.prefix}_{name} {HELP[name][0]}", *rows[name]]) + "\n"

    def publish(self) -> None:
        """Telemetry failure must not abort photo enrichment."""
        if not self.path:
            return
        with self.lock:
            temporary = self.path.with_suffix(".prom.tmp")
            try:
                temporary.write_text(self.render())
                temporary.chmod(0o644)
                temporary.replace(self.path)
            except OSError:
                logging.warning("Photo telemetry could not be published")
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
