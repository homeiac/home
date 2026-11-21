#!/usr/bin/env python3
"""Install approved preview telemetry; JSON payload on stdin, no credentials printed.

Invoked by deploy-pipeline-preview.py. Preserves the transient unit command, model,
resource scheduling and data. Rolls back code/drop-in if the worker fails to start.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def main() -> None:
    payload = json.load(sys.stdin)
    os.umask(0o077)
    root = Path("/opt/knowledge-index")
    source = root / "enrichers/media_summary.py"
    unit = "knowledge-index-enrich.service"
    dropin = Path("/run/systemd/system") / (unit + ".d") / "90-pipeline-preview.conf"
    metrics = Path("/var/lib/prometheus/node-exporter/knowledge_index_pipeline.prom")
    if hashlib.sha256(source.read_bytes()).hexdigest() != payload["expected_sha"]:
        raise RuntimeError("Worker source changed since inspection; refusing to overwrite")
    subprocess.run(["systemctl", "is-active", "--quiet", unit], check=True)
    if not metrics.parent.is_dir():
        raise RuntimeError("node-exporter textfile directory is missing")
    files = {root / "enrichers" / name: payload[name]
             for name in ("media_summary.py", "pipeline_metrics.py", "summary_cache.py")}
    parallel = int(payload.get("parallel", 1))
    mac_assist = int(payload.get("mac_assist") is True)
    if parallel < 1:
        raise ValueError("Parallel summary count must be positive")
    for path, text in files.items():
        compile(text, str(path), "exec")
    backup = root / "backups" / ("pipeline-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    backup.mkdir(parents=True, mode=0o700)
    originals = {}
    for path in [*files, dropin, metrics]:
        originals[path] = path.read_bytes() if path.exists() else None
        if path.exists():
            shutil.copy2(path, backup / path.name)
    # May contain runtime settings; retained only in the root-owned backup, never printed.
    (backup / "unit.txt").write_bytes(subprocess.check_output(["systemctl", "cat", unit]))
    print("Worker backup:", backup, flush=True)

    def replace(path: Path, content: bytes, mode: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".preview-tmp")
        tmp.write_bytes(content)
        tmp.chmod(mode)
        tmp.replace(path)

    try:
        for path, text in files.items():
            replace(path, text.encode(), 0o755 if path == source else 0o644)
        replace(dropin, ("[Service]\n"
                         "Environment=KI_PIPELINE_PROM=/var/lib/prometheus/node-exporter/knowledge_index_pipeline.prom\n"
                         f"Environment=KI_MAC_BONSAI={mac_assist}\n"
                         f"Environment=KI_SUMMARY_PARALLEL={parallel}\n").encode(), 0o644)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        started = time.time()
        subprocess.run(["systemctl", "restart", unit], check=True, timeout=45)
        for _ in range(30):
            if metrics.exists() and metrics.stat().st_mtime >= started:
                text = metrics.read_text()
                if "media_pipeline_worker_stage" in text and subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0:
                    print("Worker restarted with existing settings; live pipeline telemetry is publishing.")
                    return
            time.sleep(1)
        raise RuntimeError("No fresh telemetry from restarted worker")
    except Exception:
        for path, content in originals.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                replace(path, content, 0o755 if path == source else 0o644)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "restart", unit], check=True, timeout=45)
        print("Restored previous worker code and settings.", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
