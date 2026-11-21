#!/usr/bin/env python3
"""Replay the private 10-photo, 2-video pilot, storing each backend in its own DuckDB table.

The first photo warms the backend. Use --slots to label the configured Metal server.
Two requests are issued concurrently in the timed pass, as in the RTX slot trial.
Luna runs through Codex sign-in. Usage counts include its CLI context and aren't an API bill.
"""
import argparse
import base64
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent / "enrichers"))
from media_summary import build_prompt, parse_answer


def prepare(root: Path) -> list[dict]:
    """Build identical prompts and fingerprint the ordered frames and metadata."""
    items = json.loads((root / "manifest.json").read_text())["items"]
    if [i["kind"] for i in items] != ["photo"] * 10 + ["video"] * 2:
        raise ValueError("Expected the 12-item paired pilot")
    for item in items:
        meta = item["metadata"]
        names = [p if isinstance(p, str) else p.get("name") for p in
                 meta["saved_unlocalized_names"] + meta["confirmed_photo_faces"]]
        row = dict(taken_ts=None, album=None, has_geo=bool(meta["gps"]), people=list(filter(None, names)))
        files = [(root / f).resolve() for f in item["files"]]
        if not files or any(not f.is_relative_to(root.resolve()) for f in files):
            raise ValueError("Invalid frame path")
        prompt = build_prompt(row, item["kind"] == "video", len(files), "")
        hashes = [hashlib.sha256(f.read_bytes()).hexdigest() for f in files]
        item.update(paths=files, prompt=prompt, digest=hashlib.sha256(json.dumps([prompt, hashes]).encode()).hexdigest())
    return items


def luna(item: dict, root: Path) -> tuple:
    """Read the CLI's response and provider-reported usage for one request."""
    with tempfile.TemporaryDirectory() as folder:
        last = Path(folder) / "caption.json"
        command = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
                   "--cd", folder, "--sandbox", "read-only", "--json", "--output-schema", str(root / "schema.json"),
                   "--output-last-message", str(last), "-m", "gpt-6-luna", "-c", 'model_reasoning_effort="low"']
        for path in item["paths"]:
            command.extend(["--image", str(path)])
        run = subprocess.run(command + ["-"], input=item["prompt"], capture_output=True, text=True, timeout=160, check=True)
        events = [json.loads(line) for line in run.stdout.splitlines() if line.startswith("{")]
        usage = next(e["usage"] for e in reversed(events) if e.get("type") == "turn.completed")
        return last.read_text(), usage["input_tokens"], usage.get("cached_input_tokens", 0), usage["output_tokens"]


def metal(item: dict) -> tuple:
    """Call the loopback-only PrismML server and retain actual token usage."""
    content = [dict(type="text", text=item["prompt"])]
    for path in item["paths"]:
        jpeg = base64.b64encode(path.read_bytes()).decode()
        content.append(dict(type="image_url", image_url=dict(url="data:image/jpeg;base64," + jpeg)))
    body = dict(messages=[dict(role="user", content=content)], temperature=0.2, max_tokens=384,
                stream=False, chat_template_kwargs=dict(enable_thinking=False))
    request = urllib.request.Request("http://127.0.0.1:19475/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    usage = result["usage"]
    return result["choices"][0]["message"]["content"], usage["prompt_tokens"], None, usage["completion_tokens"]


def main() -> None:
    """Commit each response on one writer connection and record total wall time."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--backend", choices=["bonsai_metal", "luna_codex"], required=True)
    parser.add_argument("--slots", type=int, choices=[1, 2])
    args = parser.parse_args()
    if (args.backend == "bonsai_metal") != (args.slots is not None):
        parser.error("--slots applies only to the local Metal server")
    os.umask(0o077)
    root = args.input.resolve()
    items = prepare(root)
    if len({item["digest"] for item in items}) != len(items):
        raise ValueError("Expected distinct pilot inputs")
    run_id = str(uuid.uuid4())
    table = args.backend + "_captions"
    with duckdb.connect(str(args.db)) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS summary_eval_runs (
            run_id VARCHAR PRIMARY KEY, backend VARCHAR, slots INTEGER, started_at TIMESTAMPTZ,
            timed_seconds DOUBLE, valid_timed INTEGER)""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS {table} (
            run_id VARCHAR, item_id VARCHAR, kind VARCHAR, warmup BOOLEAN, input_sha256 VARCHAR,
            seconds DOUBLE, summary VARCHAR, tags VARCHAR[], input_tokens BIGINT, cached_input_tokens BIGINT,
            output_tokens BIGINT, error VARCHAR, PRIMARY KEY(run_id,item_id))""")
        db.execute("INSERT INTO summary_eval_runs VALUES (?,?,?,?,NULL,NULL)",
                   [run_id, args.backend, args.slots, datetime.datetime.now(datetime.timezone.utc)])

        def infer(item: dict) -> list:
            start = time.monotonic()
            summary = tags = inp = cached = output = error = None
            try:
                raw, inp, cached, output = luna(item, root) if args.backend == "luna_codex" else metal(item)
                summary, tags = parse_answer(raw)
            except Exception as exc:
                error = type(exc).__name__
            return [run_id, item["id"], item["kind"], item is items[0], item["digest"],
                    time.monotonic() - start, summary, tags, inp, cached, output, error]

        def save(row: list) -> bool:
            db.execute(f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", row)
            print(args.backend, row[1], round(row[5], 2), row[-1] or "ok", flush=True)
            return row[-1] is None

        if not save(infer(items[0])):
            raise RuntimeError("Warmup failed")
        start = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            valid = sum(save(row) for row in pool.map(infer, items[1:]))
        elapsed = time.monotonic() - start
        db.execute("UPDATE summary_eval_runs SET timed_seconds=?,valid_timed=? WHERE run_id=?", [elapsed, valid, run_id])
        print(f"{valid}/{len(items)-1} valid in {elapsed:.1f}s, {valid*60/elapsed:.2f}/min", flush=True)
        if valid != len(items) - 1:
            raise RuntimeError("Incomplete benchmark")


if __name__ == "__main__":
    main()
