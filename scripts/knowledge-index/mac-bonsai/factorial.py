"""Blocked 2x2 Mac GPU trial plus an intermediate configuration. No library writes."""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import random
import re
import sqlite3
import statistics
import subprocess
import threading
import time
import urllib.request

from runtime import start


def request(path_list):
    video = len(path_list) > 1
    task = (
        "The images are ordered video frames. Describe the setting, action and changes."
        if video
        else "Describe the people, setting and activity in this photograph."
    )
    content = [
        dict(
            type="text",
            text=task + " Return only JSON with summary (2–3 sentences) and up to eight short tags.",
        )
    ]
    for file in path_list:
        jpeg = base64.b64encode(file.read_bytes()).decode()
        content.append(dict(type="image_url", image_url=dict(url="data:image/jpeg;base64," + jpeg)))
    return json.dumps(
        dict(
            temperature=0.2,
            seed=217,
            max_tokens=384,
            cache_prompt=False,
            chat_template_kwargs=dict(enable_thinking=False),
            messages=[dict(role="user", content=content)],
        )
    ).encode()


def infer(body, port):
    start_at = time.monotonic()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions", body, {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.load(resp)
    cap = json.loads(re.search(r"\{.*\}", result["choices"][0]["message"]["content"], re.S)[0])
    if not isinstance(cap["summary"], str) or not cap["summary"].strip() or not isinstance(cap["tags"], list):
        raise ValueError("Invalid structured caption")
    u = result["usage"]
    return time.monotonic() - start_at, u["prompt_tokens"], u["completion_tokens"]


def pressure():
    return int(
        subprocess.check_output(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], text=True).strip()
    )


def cell(db, output, block, slots, offered, items, warm):
    key = (block, slots, offered)
    if db.execute("SELECT 1 FROM mac_factorial_runs WHERE block=? AND slots=? AND offered=?", key).fetchone():
        return
    refused = db.execute(
        "SELECT 1 FROM mac_factorial_runs WHERE slots<=? AND peak_pressure>1 AND error IS NOT NULL", (slots,)
    ).fetchone()
    if refused:
        with db:
            db.execute(
                "INSERT INTO mac_factorial_runs(block,slots,offered,valid,error) VALUES(?,?,?,0,?)",
                (*key, "Not run: allocation already exceeded memory guard"),
            )
        return
    port = 19475
    for _ in range(30):
        before = pressure()
        if before == 1:
            break
        time.sleep(2)
    else:
        raise RuntimeError("Memory pressure is elevated without the benchmark server")
    print("Testing", key, flush=True)
    path = output / f"block-{block}-{slots}-{offered}.log"
    with path.open("w") as log:
        proc = start(slots, port, log)
    stop = threading.Event()
    timed = threading.Event()
    pressures = []
    gpu = []
    rss = []

    def guard():
        warning = 0
        while not stop.wait(2):
            level = pressure()
            pressures.append(level)
            warning = warning + 1 if level > 1 else 0
            if level >= 4 or warning >= 3:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return
            if timed.is_set():
                regs = subprocess.check_output(["ioreg", "-r", "-d", "1", "-c", "AGXAccelerator", "-w", "0"])
                util = re.search(rb'"Device Utilization %"\s*=\s*(\d+)', regs)
                if util:
                    gpu.append(int(util[1]))
                value = subprocess.run(
                    ["ps", "-o", "rss=", "-p", str(proc.pid)], capture_output=True, text=True
                ).stdout.strip()
                if value:
                    rss.append(int(value) / 1024)

    thread = threading.Thread(target=guard)
    thread.start()
    error = None
    rows = []
    elapsed = None
    try:
        for _ in range(180):
            if proc.poll() is not None:
                raise RuntimeError("Server stopped during load")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as resp:
                    if json.load(resp).get("status") == "ok":
                        break
            except OSError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Server not ready")
        infer(warm, port)
        timed.set()
        started = time.monotonic()
        with ThreadPoolExecutor(offered) as pool:
            jobs = [(label, kind, pool.submit(infer, body, port)) for label, kind, body in items]
            for label, kind, job in jobs:
                try:
                    rows.append((label, kind, *job.result()))
                except Exception as exc:
                    error = type(exc).__name__
        elapsed = time.monotonic() - started
    except Exception as exc:
        error = type(exc).__name__
    finally:
        stop.set()
        thread.join()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    p95 = sorted(r[2] for r in rows)[math.ceil(0.95 * len(rows)) - 1] if rows else None
    with db:
        db.execute(
            "INSERT INTO mac_factorial_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                *key,
                len(rows),
                elapsed,
                60 * len(rows) / elapsed if elapsed else None,
                p95,
                statistics.mean(gpu) if gpu else None,
                max(rss or [0]),
                before,
                max(pressures or [before]),
                error,
            ),
        )
        db.executemany(
            "INSERT INTO mac_factorial_items VALUES (?,?,?,?,?,?,?,?)", [(*key, *row) for row in rows]
        )
    print(
        "Result",
        key,
        "valid",
        len(rows),
        "per minute",
        round(60 * len(rows) / elapsed, 2) if elapsed else None,
        "p95",
        round(p95, 1) if p95 else None,
        "GPU",
        round(statistics.mean(gpu)) if gpu else None,
        "error",
        error,
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    # This assertion ends with the benchmark process. Normal backfill follows the user's sleep policy.
    subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())])
    args.output.mkdir(parents=True, exist_ok=True)
    meta = json.loads((args.inputs / "manifest.json").read_text())["items"]
    photos = [
        (item["id"], "photo", request([args.inputs / p for p in item["files"]]))
        for item in meta
        if item["kind"] == "photo"
    ]
    videos = [
        (item["id"], "video", request([args.inputs / p for p in item["files"]]))
        for item in meta
        if item["kind"] == "video"
    ]
    # Eight individual stills supplement the 10 photos and two complete clips
    # so the largest cell can genuinely offer 20 independent requests.
    stills = [
        (f"{i}-{j}", "still", request([args.inputs / f"item-{i}-{j:02}.jpg"]))
        for i in (11, 12)
        for j in (1, 3, 5, 8)
    ]
    warm = request([args.inputs / "item-12-07.jpg"])
    with sqlite3.connect(args.output / "factorial.sqlite3") as db:
        db.executescript("""CREATE TABLE IF NOT EXISTS mac_factorial_runs(block INTEGER,slots INTEGER,offered INTEGER,
            valid INTEGER,seconds REAL,per_minute REAL,p95_seconds REAL,mean_gpu_percent REAL,peak_rss_mib REAL,
            starting_pressure INTEGER,peak_pressure INTEGER,error TEXT,PRIMARY KEY(block,slots,offered));
            CREATE TABLE IF NOT EXISTS mac_factorial_items(block INTEGER,slots INTEGER,offered INTEGER,item TEXT,kind TEXT,
            seconds REAL,input_tokens INTEGER,output_tokens INTEGER,PRIMARY KEY(block,slots,offered,item));""")

        def run_blocks(order):
            for block in (1, 2):
                items = photos + videos + stills
                random.Random(216 + block).shuffle(items)
                for slots, offered in order if block == 1 else reversed(order):
                    cell(db, args.output, block, slots, offered, items, warm)

        run_blocks([(2, 20), (20, 2), (8, 8), (2, 2), (20, 20)])
        # Complete a feasible 2x2 after a high allocation trips the guard.
        for high in (8, 4):
            unsafe = db.execute(
                "SELECT min(slots) FROM mac_factorial_runs WHERE peak_pressure>1 AND error IS NOT NULL"
            ).fetchone()[0]
            if unsafe is None or unsafe <= high:
                continue
            run_blocks([(high, 2), (high, 20)])
            if not db.execute(
                "SELECT 1 FROM mac_factorial_runs WHERE slots=? AND peak_pressure>1 AND error IS NOT NULL",
                (high,),
            ).fetchone():
                # Compare one request per slot with oversubscription at the feasible upper level.
                run_blocks([(high, high)])
                break


if __name__ == "__main__":
    main()
