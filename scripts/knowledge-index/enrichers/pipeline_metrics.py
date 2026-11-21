"""Bounded-label, live textfile telemetry for the media summary pipeline.

The worker writes this independently of the expensive five-minute index exporter.
Counters reset on process restart; Prometheus rate/increase handles the reset.
No media paths, prompts, transcripts, or summaries enter these metrics.
"""
from collections import OrderedDict, defaultdict
import hashlib
from contextlib import contextmanager
import json
import logging
import math
import os
import threading
import time

STAGES = {"idle": 0, "queue": 1, "decode": 2, "transcribe": 3,
          "prompt": 4, "inference": 5, "parse": 6, "write": 7,
          "complete": 8, "failed": 9}
TITLES = {"queue": "Select batch", "decode": "Read / decode", "transcribe": "Audio transcript",
          "prompt": "Build prompt", "inference": "Model request", "parse": "Parse answer", "write": "Write Parquet"}
EDGES = [("queue", "decode"), ("decode", "transcribe"), ("transcribe", "prompt"),
         ("decode", "prompt"), ("prompt", "inference"), ("inference", "parse"),
         ("parse", "decode"), ("parse", "write"), ("write", "queue")]
PIPELINE_HELP = {
    "media_pipeline_backend_in_flight": ("gauge", "HTTP model requests currently awaiting a response, by backend"),
    "media_pipeline_mac_request_limit": ("gauge", "Mac request capacity discovered at the latest batch selection"),
    "media_pipeline_mac_candidate_bytes_total": ("counter", "Base64 JPEG bytes offered to Metal after caption cache misses"),
    "media_pipeline_mac_cache_reusable_bytes_total": ("counter", "Base64 bytes reusable under a bounded simulated LRU of successful frame transfers"),
    "media_pipeline_mac_phase_seconds_total": ("counter", "Seconds by Mac request phase; round trip includes upload, queue, compute and return"),
    "media_pipeline_mac_phase_observations_total": ("counter", "Responses reporting the corresponding Mac request phase"),
    "media_pipeline_backend_saved_total": ("counter", "Successful Parquet writes by execution backend or cache hit"),
    "media_pipeline_cache_hits_total": ("counter", "Successful captions reused for identical model inputs; inference requests avoided"),
    "media_pipeline_stage_seconds_total": ("counter", "Wall seconds in each stage, including in-flight work; inference includes transport and server time"),
    "media_pipeline_stage_completed_seconds_total": ("counter", "Wall seconds in completed stage operations, including failed attempts"),
    "media_pipeline_stage_operations_total": ("counter", "Completed stage operations including failed attempts; queue/write operate on batches"),
    "media_pipeline_items_total": ("counter", "Attempted items by kind and result, before batch persistence"),
    "media_pipeline_persisted_items_total": ("counter", "Items successfully written to Parquet by kind and result"),
    "media_pipeline_worker_stage": ("gauge", "Worker state code: idle=0 queue=1 decode=2 transcribe=3 prompt=4 inference=5 parse=6 write=7 complete=8 failed=9"),
    "media_pipeline_stage_started_timestamp_seconds": ("gauge", "Unix time the current stage started"),
    "media_pipeline_heartbeat_timestamp_seconds": ("gauge", "Unix time the worker last published telemetry"),
    "media_pipeline_running": ("gauge", "1 while the instrumented worker runs; check heartbeat for abrupt termination"),
    "media_pipeline_queue": ("gauge", "Pending items from the last worker queue scan less subsequent successful writes"),
    "media_pipeline_in_flight": ("gauge", "Operations currently running in each stage and media type"),
    "media_pipeline_ollama_seconds_total": ("counter", "Ollama response timings converted from nanoseconds; total overlaps load/prompt/generation"),
    "media_pipeline_ollama_observations_total": ("counter", "Responses containing each Ollama duration field"),
    "media_pipeline_ollama_tokens_total": ("counter", "Ollama reported prompt or generated token count"),
    "media_pipeline_edge_info": ("gauge", "Pipeline topology; decode to prompt skips transcription for photos; parse loops for the next item"),
}


class MediaCacheProbe:
    """Simulate a bounded JPEG cache. Store only digests and sizes on the queue host."""

    def __init__(self, capacity):
        self.capacity = capacity
        self.entries = OrderedDict()
        self.used = self.reusable = 0

    def observe(self, frames):
        for digest, size in frames:
            if digest in self.entries:
                self.reusable += 4 * ((size + 2) // 3)
                self.entries.move_to_end(digest)

    def delivered(self, frames):
        for digest, size in frames:
            if digest in self.entries:
                self.entries.move_to_end(digest)
                continue
            if size > self.capacity:
                continue
            while self.used + size > self.capacity:
                _, dropped = self.entries.popitem(last=False)
                self.used -= dropped
            self.entries[digest] = size
            self.used += size


class PipelineMetrics:
    """Measure stages with a monotonic clock and publish atomically every five seconds."""

    def __init__(self, path: str | None, enricher: str, every: float = 5.0):
        self.path, self.enricher, self.every = path, enricher, every
        self.seconds = defaultdict(float)
        self.operations = defaultdict(int)
        self.items = defaultdict(int)
        self.persisted = defaultdict(int)
        self.mac_cache = {mib: MediaCacheProbe(mib * 1024**2) for mib in (64, 256, 1024)}
        self.mac_bytes = 0
        self.mac_seconds = defaultdict(float)
        self.mac_counts = defaultdict(int)
        self.backend_active = {"primary": 0, "metal": 0}
        self.mac_limit = 0
        self.backend_saved = dict.fromkeys(("primary", "metal", "cache"), 0)
        self.ollama_seconds = defaultdict(float)
        self.ollama_observations = defaultdict(int)
        self.tokens = defaultdict(int)
        self.cache_hits = {"photo": 0, "video": 0}
        for stage in TITLES:
            for kind in (("batch",) if stage in ("queue", "write") else ("photo", "video")):
                self.seconds[stage, kind] = 0.0
                self.operations[stage, kind] = 0
        for kind in ("photo", "video"):
            for status in ("ok", "error"):
                self.items[kind, status] = self.persisted[kind, status] = 0
        self.active = {}
        self.stage = "idle"
        self.pending = None
        self.started = time.time()
        self.running = 1
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.warned = False

    def __enter__(self):
        if self.path:
            self.publish()
            self.thread = threading.Thread(target=self._heartbeat, daemon=True)
            self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop.set()
        if self.thread:
            self.thread.join()
        with self.lock:
            self.running = 0
            self.stage = "failed" if exc_type else "complete"
            self.started = time.time()
            self.publish()

    def _heartbeat(self) -> None:
        while not self.stop.wait(self.every):
            self.publish()

    @contextmanager
    def measure(self, stage: str, kind: str = "batch"):
        """Account for successful and failed work, including a currently blocked operation."""
        operation = object()
        with self.lock:
            self.active[operation] = stage, kind, time.time(), time.monotonic()
            self.publish()
        try:
            yield
        finally:
            with self.lock:
                _, _, _, started = self.active.pop(operation)
                self.seconds[stage, kind] += max(0, time.monotonic() - started)
                self.operations[stage, kind] += 1
                self.stage, self.started = "idle", time.time()
                self.publish()

    def queue_size(self, count: int) -> None:
        """Record a fresh queue snapshot."""
        with self.lock:
            self.pending = count

    def item(self, kind: str, status: str, persisted: bool = False, backend: str = "primary") -> None:
        """Distinguish completed inference from durable Parquet output."""
        with self.lock:
            (self.persisted if persisted else self.items)[kind, status] += 1
            if persisted and status == "ok":
                self.backend_saved[backend] += 1
            if persisted and status == "ok" and self.pending is not None:
                self.pending = max(0, self.pending - 1)

    def cache_hit(self, kind: str) -> None:
        """Count a caption reused from the local cache."""
        with self.lock:
            self.cache_hits[kind] += 1

    @contextmanager
    def backend_request(self, backend):
        with self.lock:
            self.backend_active[backend] += 1
        try:
            yield
        finally:
            with self.lock:
                self.backend_active[backend] -= 1

    def mac_capacity(self, offered):
        with self.lock:
            self.mac_limit = offered

    def mac_request(self, jpegs):
        frames = [(hashlib.sha256(jpeg).digest(), len(jpeg)) for jpeg in jpegs]
        with self.lock:
            self.mac_bytes += sum(4 * ((size + 2) // 3) for _, size in frames)
            for cache in self.mac_cache.values():
                cache.observe(frames)
        return frames

    def mac_response(self, frames, kind, elapsed, response):
        timings = response.get("timings") or {}
        with self.lock:
            for cache in self.mac_cache.values():
                cache.delivered(frames)
            self.mac_seconds["round_trip", kind] += elapsed
            self.mac_counts["round_trip", kind] += 1
            for phase, key in (("prompt", "prompt_ms"), ("generation", "predicted_ms")):
                value = timings.get(key)
                if isinstance(value, (float, int)) and math.isfinite(value) and value >= 0:
                    self.mac_seconds[phase, kind] += value / 1000
                    self.mac_counts[phase, kind] += 1

    def ollama(self, response: dict, kind: str) -> None:
        """Keep only numeric timing and token fields; missing fields remain absent."""
        with self.lock:
            for phase, field in (("load", "load_duration"), ("prompt", "prompt_eval_duration"),
                                 ("generation", "eval_duration"), ("total", "total_duration")):
                value = response.get(field)
                if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
                    self.ollama_seconds[phase, kind] += value / 1e9
                    self.ollama_observations[phase, kind] += 1
            # Pair token counts with their durations so throughput excludes incomplete observations.
            for phase, field, duration in (("prompt", "prompt_eval_count", "prompt_eval_duration"),
                                           ("generation", "eval_count", "eval_duration")):
                value, seconds = response.get(field), response.get(duration)
                if (isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
                        and isinstance(seconds, (int, float)) and math.isfinite(seconds) and seconds > 0):
                    self.tokens[phase, kind] += value

    def render(self) -> str:
        """Render Prometheus exposition with bounded labels and no explicit sample timestamps."""
        with self.lock:
            rows = defaultdict(list)

            def add(name, value, **labels):
                labels["enricher"] = self.enricher
                lab = ",".join(f"{k}={json.dumps(str(v), ensure_ascii=False)}" for k, v in sorted(labels.items()))
                rows[name].append(f"{name}{{{lab}}} {value}")

            active_seconds = defaultdict(float)
            active_counts = defaultdict(int)
            stage_now, stage_started = self.stage, self.started
            if self.active:
                stage_now, _, stage_started, _ = next(iter(self.active.values()))
                now = time.monotonic()
                for stage, kind, _, started in self.active.values():
                    active_seconds[stage, kind] += max(0, now - started)
                    active_counts[stage, kind] += 1
            for (stage, kind), value in sorted(self.seconds.items()):
                add("media_pipeline_stage_completed_seconds_total", value, stage=stage, kind=kind)
                add("media_pipeline_stage_seconds_total", value + active_seconds[stage, kind],
                    stage=stage, kind=kind, id=stage, title=TITLES[stage])
                add("media_pipeline_stage_operations_total", self.operations[stage, kind], stage=stage, kind=kind)
                add("media_pipeline_in_flight", active_counts[stage, kind], stage=stage, kind=kind)
            for name, values in (("media_pipeline_items_total", self.items), ("media_pipeline_persisted_items_total", self.persisted)):
                for (kind, status), value in sorted(values.items()):
                    add(name, value, kind=kind, status=status)
            for backend, count in self.backend_active.items():
                add("media_pipeline_backend_in_flight", count, backend=backend)
            add("media_pipeline_mac_request_limit", self.mac_limit)
            add("media_pipeline_mac_candidate_bytes_total", self.mac_bytes)
            for mib, cache in self.mac_cache.items():
                add("media_pipeline_mac_cache_reusable_bytes_total", cache.reusable, capacity_mib=mib)
            for (phase, kind), seconds in self.mac_seconds.items():
                add("media_pipeline_mac_phase_seconds_total", seconds, phase=phase, kind=kind)
                add("media_pipeline_mac_phase_observations_total", self.mac_counts[phase, kind], phase=phase, kind=kind)
            for backend, count in self.backend_saved.items():
                add("media_pipeline_backend_saved_total", count, backend=backend)
            if self.pending is not None:
                add("media_pipeline_queue", self.pending)
            for name, value in (("worker_stage", STAGES[stage_now]), ("stage_started_timestamp_seconds", stage_started),
                                ("heartbeat_timestamp_seconds", time.time()), ("running", self.running)):
                add("media_pipeline_" + name, value)
            for name, values in (("seconds", self.ollama_seconds), ("observations", self.ollama_observations), ("tokens", self.tokens)):
                for (phase, kind), value in sorted(values.items()):
                    add(f"media_pipeline_ollama_{name}_total", value, phase=phase, kind=kind)
            for kind, count in self.cache_hits.items():
                add("media_pipeline_cache_hits_total", count, kind=kind)
            for source, target in EDGES:
                add("media_pipeline_edge_info", 1, id=source + "-" + target, source=source, target=target)
            lines = []
            for name, samples in sorted(rows.items()):
                typ, help_text = PIPELINE_HELP[name]
                lines.extend([f"# HELP {name} {help_text}", f"# TYPE {name} {typ}", *samples])
            return "\n".join(lines) + "\n"

    def publish(self) -> None:
        """A telemetry failure must not discard summaries or abort a batch."""
        if not self.path:
            return
        with self.lock:
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(self.render())
                os.chmod(tmp, 0o644)
                os.replace(tmp, self.path)
                self.warned = False
            except OSError:
                if not self.warned:
                    logging.exception("Could not publish pipeline telemetry")
                    self.warned = True
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
