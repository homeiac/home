#!/usr/bin/env python3
"""Photo/video summary enricher for the knowledge index (issue #212, OpenSpec change add-media-summaries-enricher).

Usage:
  media_summary.py run --index DIR --library DIR --endpoint URL --model NAME --enricher ID
                       [--limit N] [--batch-size 50] [--parallel 1] [--frames 8] [--min-free-mib 3000] [--dry-run]

  --index      knowledge-index dataset mount (reads knowledge.duckdb, writes summaries/<enricher>/<batch>.parquet)
  --library    photos library root, read-only: the folder that holds "Google Photos/" (<dataset>/library)
  --endpoint   OpenAI-compatible server on the home network, e.g. http://<gpu-vm>:11434 (Ollama) or a llama.cpp server
  --enricher   id of this model+prompt combination, e.g. qwen25vl-3b-p1 (bump it to re-summarize with a new model/prompt)
  --api ollama       use Ollama native /api/chat (recommended with Ollama: honors think:false; --num-ctx sets the context)
  --extra-json JSON  extra chat-request fields, e.g. '{"think": false}' (thinking models: 10x slower and wasteful otherwise)
  --dry-run    summarize --limit files, print them, write nothing (the "sample" mode)
  --prom FILE  publish live stage / Ollama timings for node-exporter (ignored in sample mode)
  --min-free-mib  refuse to start when the GPU has less free memory (nvidia-smi); 0 disables; --smi-cmd overrides the binary

Queue: SELECT ... FROM gphotos_to_summarize(<enricher>): media with no `ok` row for their current bytes (errors are retried).
Photo: one image (long edge 1024). Video: --frames frames across the clip + audio transcript (faster-whisper, if installed).
Reads media read-only, writes summaries below <index>/summaries and optional telemetry to --prom,
sends nothing outside the given endpoint. Telemetry never contains media paths or contents.
"""
import argparse
import base64
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import copy
from contextlib import nullcontext
from functools import partial

import duckdb
from pipeline_metrics import PipelineMetrics
from summary_cache import SummaryCache

VIDEO_EXTS = {"mp4", "mov", "3gp", "avi", "mpg", "m4v"}
SCHEMA = ("source VARCHAR, path VARCHAR, size_bytes BIGINT, enricher VARCHAR, model VARCHAR, prompt_version VARCHAR, "
          "summary VARCHAR, tags VARCHAR[], frames_sampled INTEGER, duration_s DOUBLE, status VARCHAR, error VARCHAR, "
          "created_at TIMESTAMP")
PROMPT_VERSION = "p1"


def free_gpu_mib(smi_cmd):
    """Free GPU memory in MiB (minimum over GPUs), or None when nvidia-smi is unavailable."""
    try:
        out = subprocess.run([smi_cmd, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20, check=True).stdout
        return min(int(x) for x in out.split())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _ffmpeg(args, timeout=120):
    return subprocess.run(["ffmpeg", "-v", "error", "-nostdin"] + args, capture_output=True, timeout=timeout)


def jpeg_frame(path, t=None):
    """One JPEG (long edge <= 1024) from an image or from second `t` of a video; raises RuntimeError when undecodable."""
    if t is None and os.path.splitext(path)[1].lower() in {'.heic', '.heif', '.hif'}:
        import io
        from PIL import Image, ImageOps
        from pillow_heif import register_heif_opener

        register_heif_opener()
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            result = io.BytesIO()
            image.convert('RGB').save(result, 'JPEG', quality=88)
            return result.getvalue()
    scale = "scale='if(gt(iw,ih),min(1024,iw),-2)':'if(gt(iw,ih),-2,min(1024,ih))'"
    pre = ["-ss", "%.2f" % t] if t is not None else []
    r = _ffmpeg(pre + ["-i", path, "-vf", scale, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"])
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("cannot decode %s: %s" % (os.path.basename(path), " ".join(r.stderr.decode(errors="replace").split())[:200]))
    return r.stdout


def video_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
                       capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise RuntimeError("cannot read duration of %s" % os.path.basename(path))


def transcript(path):
    """Speech transcript via faster-whisper when installed and the video has audio; '' otherwise."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return ""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path],
                       capture_output=True, text=True, timeout=60)
    if not r.stdout.strip():
        return ""
    model = WhisperModel(os.environ.get("KI_WHISPER_MODEL", "small"), compute_type="int8")
    segs, _ = model.transcribe(path)
    return " ".join(s.text.strip() for s in segs)[:4000]


def build_prompt(row, is_video, nframes, speech):
    ctx = []
    if row["taken_ts"]:
        ctx.append("taken " + datetime.datetime.fromtimestamp(row["taken_ts"], datetime.timezone.utc).strftime("%Y-%m-%d"))
    if row["album"]:
        ctx.append("album '%s'" % row["album"])
    if row["has_geo"]:
        ctx.append("it has GPS location")
    if row["people"]:
        ctx.append("people tagged: " + ", ".join(row["people"]))
    what = ("%d frames sampled evenly across a video clip" % nframes) if is_video else "a photo"
    p = ["You are given %s. Context: %s." % (what, "; ".join(ctx) or "none"),
         "Describe what is happening: who or what is shown, the setting, the activity" + (", and how it changes over the clip" if is_video else "") + ".",
         "Be factual; say 'unclear' instead of guessing."]
    if speech:
        p.append("Audio transcript: " + speech)
    p.append('Answer ONLY with JSON: {"summary": "<2-3 sentences>", "tags": ["<up to 8 short keywords>"]}')
    return "\n".join(p)


def parse_answer(text):
    """Extract {"summary","tags"} from a model reply (tolerates code fences / chatter around the JSON)."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in model reply")
    d = json.loads(m.group(0))
    summary = str(d.get("summary", "")).strip()
    if not summary:
        raise ValueError("empty summary")
    tags = [str(t).strip() for t in (d.get("tags") or []) if str(t).strip()][:8]
    return summary, tags


def ask_model(endpoint, model, prompt, jpegs, timeout=600, extra=None, api="openai", num_ctx=8192, keep_alive="30m", metrics=None, kind="photo", headers=None):
    """One chat request with all images. api="ollama" uses Ollama's native /api/chat: it honors `think: false`
    (the OpenAI-compatible /v1 endpoint did not on 2026-11-16: reasoning models then spent ~500 hidden tokens, 18-45 s/item instead of ~2-5 s)."""
    b64 = [base64.b64encode(j).decode() for j in jpegs]
    if api == "ollama":
        body = {"model": model, "stream": False, "keep_alive": keep_alive, "options": {"num_ctx": num_ctx, "temperature": 0.2},
                "messages": [{"role": "user", "content": prompt, "images": b64}]}
        body.update(extra or {})
        url = endpoint.rstrip("/") + "/api/chat"
    else:
        content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + x}} for x in b64]
        body = {"model": model, "messages": [{"role": "user", "content": content}], "temperature": 0.2, **(extra or {})}
        url = endpoint.rstrip("/") + "/v1/chat/completions"
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})})
    mac_frames = metrics.mac_request(jpegs) if endpoint == MAC_ENDPOINT and metrics is not None else None
    started = time.monotonic()
    backend = "metal" if endpoint == MAC_ENDPOINT else "primary"
    tracking = metrics.backend_request(backend) if metrics is not None else nullcontext()
    with tracking, urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.load(resp)
    if mac_frames is not None:
        metrics.mac_response(mac_frames, kind, time.monotonic() - started, out)
    if api == "ollama" and metrics is not None:
        metrics.ollama(out, kind)
    return out["message"]["content"] if api == "ollama" else out["choices"][0]["message"]["content"]


def summarize(row, library, a, metrics=None, cache=None):
    """-> dict of result columns for one queue row; never raises (errors become status='error' rows)."""
    base = {"source": "gphotos", "path": row["path"], "size_bytes": row["size_bytes"], "enricher": a.enricher, "model": a.model,
            "prompt_version": PROMPT_VERSION, "summary": None, "tags": None, "frames_sampled": None, "duration_s": None,
            "status": "error", "error": None, "inference_backend": getattr(a, "backend", "primary")}
    ap = os.path.join(library, row["path"])
    metrics = metrics or PipelineMetrics(None, a.enricher)
    kind = "video" if row["ext"] in VIDEO_EXTS else "photo"
    try:
        with metrics.measure("decode", kind):
            if kind == "video":
                dur = video_duration(ap)
                n = max(1, min(a.frames, int(dur) or 1))
                jpegs = [jpeg_frame(ap, dur * (i + 0.5) / n) for i in range(n)]
            else:
                jpegs = [jpeg_frame(ap)]
        speech = ""
        if kind == "video":
            with metrics.measure("transcribe", kind):
                speech = transcript(ap)
            base.update(frames_sampled=n, duration_s=dur)
        with metrics.measure("prompt", kind):
            prompt = build_prompt(row, kind == "video", len(jpegs), speech)
        cache_key = SummaryCache.key(prompt, jpegs, {
            "endpoint": a.endpoint, "enricher": a.enricher, "model": a.model,
            "prompt_version": PROMPT_VERSION, "api": a.api, "num_ctx": a.num_ctx, "extra": a.extra,
        }) if cache is not None else None
        cached = cache.get(cache_key) if cache is not None else None
        if cached is None:
            base["_model_failure"] = True
            with metrics.measure("inference", kind):
                answer = ask_model(a.endpoint, a.model, prompt, jpegs, extra=a.extra, api=a.api,
                                   num_ctx=a.num_ctx, metrics=metrics, kind=kind, timeout=getattr(a, "request_timeout", 600),
                                   headers=getattr(a, "model_headers", None))
            with metrics.measure("parse", kind):
                summary, tags = parse_answer(answer)
            base.pop("_model_failure", None)
            if cache is not None:
                cache.put(cache_key, summary, tags)
        else:
            summary, tags = cached
            metrics.cache_hit(kind)
            base["inference_backend"] = "cache"
        base.update(summary=summary, tags=tags, status="ok")
    except Exception as exc:  # one bad file must not stop the run
        base["error"] = ("%s: %s" % (type(exc).__name__, exc))[:500]
    metrics.item(kind, base["status"])
    return base


def write_batch(rows, out_dir, enricher):
    d = os.path.join(out_dir, "summaries", enricher)
    os.makedirs(d, exist_ok=True)
    target = os.path.join(d, "b%s-%04d.parquet" % (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%f"), len(os.listdir(d))))
    tmp = target + ".tmp"
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    con = duckdb.connect()
    con.execute("CREATE TABLE t (%s)" % SCHEMA)
    cols = ["source", "path", "size_bytes", "enricher", "model", "prompt_version", "summary", "tags", "frames_sampled",
            "duration_s", "status", "error"]
    con.executemany("INSERT INTO t VALUES (%s)" % ",".join("?" * 13), [tuple(r[c] for c in cols) + (now,) for r in rows])
    con.execute("COPY t TO '%s' (FORMAT parquet, COMPRESSION zstd)" % tmp.replace("'", "''"))
    os.replace(tmp, target)
    return target


def queue(index, enricher, limit, seen=(), metrics=None, *, photos_first=False):
    """Select pending work while skipping paths already attempted in this run."""
    priority = "coalesce(list_contains(?, lower(ext)), false), " if photos_first else ""
    params = [enricher, sorted(VIDEO_EXTS), limit + len(seen)] if photos_first else [enricher, limit + len(seen)]
    with duckdb.connect(os.path.join(index, "knowledge.duckdb"), read_only=True) as con:
        cur = con.execute("SELECT *, count(*) OVER () AS pending_count FROM gphotos_to_summarize(?) "
                          f"ORDER BY {priority}taken_ts DESC NULLS LAST, path LIMIT ?", params)
        names = [column[0] for column in cur.description[:-1]]
        rows = cur.fetchall()
    if metrics is not None:
        metrics.queue_size(rows[0][-1] if rows else 0)
    return [r for r in (dict(zip(names, row[:-1])) for row in rows) if r["path"] not in seen][:limit]


MAC_ENDPOINT = "http://127.0.0.1:19476"


def mac_headers():
    with open("/opt/knowledge-index/mac-bonsai.key", encoding="ascii") as file:
        return {"Authorization": "Bearer " + file.read().strip()}


def mac_route(args):
    """Discover the authenticated Mac server's Git-configured request limit."""
    if not getattr(args, "mac_assist", False) or args.model != "bonsai-27b" or args.dry_run:
        return 0, None
    try:
        headers = mac_headers()
        probe = urllib.request.Request(MAC_ENDPOINT + "/v1/models", headers=headers)
        with urllib.request.urlopen(probe, timeout=1) as response:
            models = json.load(response)["data"]
        for model in models:
            if model["id"] == "bonsai-27b-metal":
                for tag in model["tags"]:
                    match = re.fullmatch(r"backfill-parallel=([1-9]|1[0-9]|20)", tag)
                    if match:
                        return int(match[1]), headers
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return 0, None


def split_batch(rows, primary_slots, mac_slots, primary, metal, *, refill=None, prefer_photos=False):
    """Keep slots fed across queue reads. Retry interrupted Mac work on the RTX."""
    pending = deque(rows)
    retry = deque()
    disabled = False
    with ThreadPoolExecutor(max_workers=primary_slots + mac_slots) as pool:
        active = {}

        def submit(backend):
            nonlocal refill
            if backend == "metal" and disabled:
                return
            if not pending and not retry and refill is not None and not disabled:
                pending.extend(refill())
                if not pending:
                    refill = None
            candidates = retry if backend == "primary" and retry else pending
            if candidates:
                if backend == "metal" and prefer_photos:
                    # Long visual prompts take substantially longer on the Mac.
                    photo = next((i for i, row in enumerate(candidates) if row["ext"] not in VIDEO_EXTS), 0)
                    row = candidates[photo]
                    del candidates[photo]
                else:
                    row = candidates.popleft()
                task = metal if backend == "metal" else primary
                active[pool.submit(task, row)] = (backend, row)

        for backend, count in (("primary", primary_slots), ("metal", mac_slots)):
            for _ in range(count):
                submit(backend)
        while active:
            completed, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in completed:
                backend, row = active.pop(future)
                result = future.result()
                if backend == "metal" and result["status"] != "ok" and result.get("_model_failure"):
                    disabled = True
                    retry.append(row)
                    submit(backend)
                else:
                    submit(backend)
                    yield row, result
            # Primary slots may already have drained when a late Mac request fails.
            primary_active = sum(backend == "primary" for backend, _ in active.values())
            for _ in range(min(len(retry), primary_slots - primary_active)):
                submit("primary")


def persist(batch, args, metrics, seen):
    """Only the host writes Parquet and advances durable counters."""
    with metrics.measure("write"):
        write_batch([result for _, result in batch], args.index, args.enricher)
    for row, result in batch:
        kind = "video" if row["ext"] in VIDEO_EXTS else "photo"
        metrics.item(kind, result["status"], persisted=True, backend=result.get("inference_backend", "primary"))
        if result["status"] == "ok":
            seen.discard(row["path"])


class DispatchPolicy:
    """Poll the deployed Git policy and retain the last valid settings during outages."""

    def __init__(self, args):
        self.current = (getattr(args, "dispatch_mode", "continuous"),
                        getattr(args, "dispatch_size", 0),
                        getattr(args, "mac_routing", "photo-first"))
        self.url = os.environ.get("KI_GPU_DISPATCH_POLICY_URL") if not args.dry_run else None
        self.ref = os.environ.get("KI_GPU_DISPATCH_GIT_REF")
        self.revision = None
        self.queue_order = "newest"
        self.next_poll = 0

    def poll(self):
        now = time.monotonic()
        if self.url and self.ref and now >= self.next_poll:
            self.next_poll = now + 30
            try:
                result = subprocess.check_output(
                    ["git", "ls-remote", "--exit-code", "https://github.com/homeiac/home.git", self.ref],
                    timeout=3, stderr=subprocess.DEVNULL, text=True,
                )
                revision, _ = result.strip().split("\t")
                if not re.fullmatch(r"[0-9a-f]{40}", revision):
                    raise ValueError("Invalid Git dispatch revision")
                if revision == self.revision:
                    return self.current
                with urllib.request.urlopen(self.url.format(revision=revision), timeout=2) as response:
                    policy = json.load(response)
                mode, size, routing = policy["mode"], policy["page_size"], policy["mac_routing"]
                order = policy.get("queue_order", "newest")
                if (mode not in ("batch", "continuous") or type(size) is not int or not 0 <= size <= 512
                        or routing not in ("fifo", "photo-first") or order not in ("newest", "photos-first")):
                    raise ValueError("Invalid Git dispatch policy")
                self.current = mode, size, routing
                self.queue_order = order
                self.revision = revision
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
                print("WARN: keeping the last valid Git dispatch policy", file=sys.stderr)
        return self.current


def run(a):
    if a.min_free_mib > 0:
        free = free_gpu_mib(a.smi_cmd)
        if free is None:
            print("WARN: cannot read GPU memory (%s unavailable); continuing" % a.smi_cmd, file=sys.stderr)
        elif free < a.min_free_mib:
            print("not starting: free GPU memory %d MiB < %d MiB (Frigate needs it)" % (free, a.min_free_mib), file=sys.stderr)
            return 3
    done = errors = 0
    t0 = time.time()
    remaining = a.limit
    policy = DispatchPolicy(a)
    seen = set()
    cache_context = nullcontext(None) if a.dry_run else SummaryCache(os.path.join(a.index, "summary-cache.sqlite3"))
    with cache_context as cache, PipelineMetrics(None if a.dry_run else getattr(a, "prom", None), a.enricher) as metrics:
        primary = partial(summarize, library=a.library, a=a, metrics=metrics, cache=cache)
        metal_args = copy(a)
        metal_args.model = "bonsai-27b-metal"
        metal_args.endpoint = MAC_ENDPOINT
        metal_args.api = "openai"
        metal_args.extra = {"max_tokens": 384, "chat_template_kwargs": {"enable_thinking": False}}
        metal_args.backend = "metal"
        metal_args.request_timeout = 180
        metal = partial(summarize, library=a.library, a=metal_args, metrics=metrics, cache=cache)
        while remaining > 0:
            settings = policy.poll()
            queue_order = policy.queue_order
            dispatch_mode, dispatch_size, mac_routing = settings
            metrics.dispatch_policy(*settings, queue_order=queue_order)
            mac_slots, metal_args.model_headers = mac_route(a)
            metrics.mac_capacity(mac_slots)
            fetch_size = a.batch_size
            if mac_slots:
                fetch_size = dispatch_size or max(a.batch_size, 4 * (a.parallel + mac_slots))
            def fetch():
                nonlocal remaining
                if remaining <= 0:
                    return []
                with metrics.measure("queue"):
                    rows = queue(a.index, a.enricher, min(fetch_size, remaining), seen, metrics,
                                 photos_first=queue_order == "photos-first")
                seen.update(r["path"] for r in rows)
                remaining -= len(rows)
                return rows

            rows = fetch()
            if not rows:
                break
            previous_errors = errors
            batch = []
            # Keep the existing single-write cadence while refilling slots independently.
            def refill():
                # Finish outstanding requests before activating a changed policy.
                return [] if (policy.poll() != settings or policy.queue_order != queue_order
                              or (errors and not done)) else fetch()

            for row, result in split_batch(
                rows, a.parallel, mac_slots, primary, metal,
                refill=refill if mac_slots and dispatch_mode == "continuous" else None,
                prefer_photos=mac_routing == "photo-first",
            ):
                done += result["status"] == "ok"
                errors += result["status"] != "ok"
                if a.dry_run:
                    print("%s\t%s\t%s\t%s" % (result["status"], row["path"], result["summary"] or result["error"], ",".join(result["tags"] or [])))
                    continue
                batch.append((row, result))
                if len(batch) == a.batch_size:
                    persist(batch, a, metrics, seen)
                    batch.clear()
            if a.dry_run:
                break
            if batch:
                persist(batch, a, metrics, seen)
            if errors > previous_errors and not done:   # no working backend
                print("whole batch failed; stopping", file=sys.stderr)
                break
    n = done + errors
    print("ok=%d errors=%d seconds=%.1f per_item=%.1f" % (done, errors, time.time() - t0, (time.time() - t0) / max(n, 1)))
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--index", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--enricher", required=True)
    ap.add_argument("--limit", type=int, default=10 ** 9)
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--parallel", type=int, default=os.environ.get("KI_SUMMARY_PARALLEL", "1"),
                    help="Maximum summaries in flight, sharing a single Parquet writer")
    ap.add_argument("--mac-assist", action="store_true", default=os.environ.get("KI_MAC_BONSAI") == "1",
                    help="Share pending Bonsai summaries with the authenticated Mac worker while it is available")
    ap.add_argument("--dispatch-mode", choices=("batch", "continuous"),
                    default=os.environ.get("KI_GPU_DISPATCH_MODE", "continuous"))
    ap.add_argument("--dispatch-size", type=int, default=os.environ.get("KI_GPU_DISPATCH_SIZE", "0"),
                    help="Items per queue read with the Mac available. Zero chooses a size from the slot count.")
    ap.add_argument("--mac-routing", choices=("fifo", "photo-first"),
                    default=os.environ.get("KI_MAC_ROUTING", "photo-first"))
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--min-free-mib", type=int, default=3000)
    ap.add_argument("--smi-cmd", default="nvidia-smi")
    ap.add_argument("--api", choices=["openai", "ollama"], default="openai", help="openai = /v1/chat/completions; ollama = native /api/chat (honors think:false)")
    ap.add_argument("--num-ctx", type=int, default=8192, help="context length for --api ollama (8 frames x ~300 tokens + transcript)")
    ap.add_argument("--extra-json", default="{}", help='extra request fields merged into the chat body, e.g. \'{"think": false}\' to stop reasoning models burning tokens')
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prom", default=os.environ.get("KI_PIPELINE_PROM"),
                    help="live pipeline metrics textfile for node-exporter (or KI_PIPELINE_PROM); ignored by --dry-run")
    args = ap.parse_args(argv)
    if args.parallel < 1:
        ap.error("--parallel must be positive")
    if not 0 <= args.dispatch_size <= 512:
        ap.error("--dispatch-size must be between 0 and 512")
    args.extra = json.loads(args.extra_json)
    return run(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
