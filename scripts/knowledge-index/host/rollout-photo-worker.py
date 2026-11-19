#!/usr/bin/env python3
"""Host-side versioned deployment, backup, bounded smoke test and rollback (#217)."""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path("/opt/photo-enrichment")
STATE = Path("/local-3TB-backup/photo-enrichment")
PROM = Path("/var/lib/prometheus/node-exporter/photo_enrichment.prom")
UNIT = "photo-enrichment-worker.service"
UNIT_PATH = Path("/etc/systemd/system") / UNIT
ENV_PATH = Path("/etc/default/photo-enrichment-worker")


def command(*args: str, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def source_paths() -> tuple[Path, Path]:
    """Discover exact source paths from the existing caption worker, without exposing its environment."""
    pid = subprocess.check_output(["systemctl", "show", "knowledge-index-enrich", "-p", "MainPID", "--value"], text=True).strip()
    argv = Path("/proc", pid, "cmdline").read_bytes().decode().split("\0")
    index, library = (Path(argv[argv.index(flag)+1]).resolve() for flag in ("--index", "--library"))
    if not (index / "knowledge.duckdb").is_file() or not (library / "Google Photos").is_dir():
        raise RuntimeError("Source catalog/library paths failed validation")
    if STATE.is_relative_to(index) or STATE.is_relative_to(library):
        raise RuntimeError("State must be separate from source data")
    return index, library


def status() -> None:
    """Report only aggregate persisted output and heartbeat; no private paths or identities."""
    print(subprocess.run(["systemctl", "show", UNIT, "-p", "ActiveState", "-p", "SubState", "-p", "NRestarts", "-p", "MemoryCurrent", "-p", "CPUUsageNSec"], capture_output=True, text=True).stdout)
    if PROM.exists():
        print("Telemetry age seconds:", round(time.time()-PROM.stat().st_mtime, 1))
        for line in PROM.read_text().splitlines():
            if line.startswith(("photo_enrichment_inventory", "photo_enrichment_queue", "photo_enrichment_worker_stage", "photo_enrichment_running")):
                print(line)
    release = ROOT / "current"
    if (release / "venv/bin/python").exists():
        # Parquet can be read while the worker owns the DuckDB writer lock.
        check = """import duckdb,json,sys; from pathlib import Path
root=Path(sys.argv[1]); db=duckdb.connect(); result={}
for name in ('extracted','faces','photo_groups'):
 p=root/'parquet'/(name+'.parquet')
 if p.exists(): result[name]=db.execute('SELECT count(*) FROM read_parquet(?)',[str(p)]).fetchone()[0]
print('Durable Parquet rows:',json.dumps(result))
"""
        command(str(release / "venv/bin/python"), "-c", check, str(STATE))


def main() -> None:
    payload = json.load(sys.stdin)
    os.umask(0o077)
    if payload["mode"] == "status":
        status()
        return
    index, library = source_paths()
    print("Host Python:", sys.version.split()[0])
    print("Source index:", index, "Library:", library)
    print("State parent free GiB:", round(shutil.disk_usage(STATE.parent).free / 2**30, 1))
    print("Existing enrichment state:", STATE.exists(), "Textfile directory:", PROM.parent.is_dir())
    if payload["mode"] == "inspect":
        return
    if sys.version_info[:2] not in ((3,11),(3,12),(3,13)) or not PROM.parent.is_dir():
        raise RuntimeError("Expected Python 3.11–3.13 and existing node exporter textfile directory")
    ROOT.mkdir(parents=True, exist_ok=True)
    release = ROOT / "releases" / payload["release"]
    release.mkdir(parents=True, exist_ok=True)
    for name, content in payload["files"].items():
        path = release / name
        if not path.resolve().is_relative_to(release.resolve()):
            raise ValueError("Invalid source path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    if not (release / "venv/bin/python").exists():
        command(sys.executable, "-m", "venv", "--without-pip", str(release / "venv"))
    python = str(release / "venv/bin/python")
    # Match install-duckdb.sh: Debian host lacks ensurepip; system pip targets only this venv.
    command(sys.executable, "-m", "pip", "--python", python, "install", "--disable-pip-version-check", "-r", str(release / "photo_enrichment/requirements.txt"))
    current = ROOT / "current"
    previous = current.resolve() if current.exists() else None
    active = subprocess.run(["systemctl", "is-active", "--quiet", UNIT]).returncode == 0
    enabled = subprocess.run(["systemctl", "is-enabled", "--quiet", UNIT], stderr=subprocess.DEVNULL).returncode == 0
    backup = ROOT / "backups" / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup.mkdir(parents=True)
    originals = {path: path.read_bytes() if path.exists() else None for path in (UNIT_PATH, ENV_PATH, PROM)}
    for path, data in originals.items():
        if data is not None:
            (backup / path.name).write_bytes(data)
    print("Deployment backup:", backup, flush=True)
    command("systemctl", "stop", UNIT) if UNIT_PATH.exists() else None
    STATE.mkdir(parents=True, exist_ok=True)
    # Quiesced backup also preserves WAL recovery if a previous process was interrupted.
    for path in STATE.glob("enrichment.duckdb*"):
        shutil.copy2(path, backup / path.name)
    try:
        command(python, str(release / "photo-enrich.py"), "--state", str(STATE), "models")
        env = dict(os.environ, OPENBLAS_NUM_THREADS="2", OMP_NUM_THREADS="2")
        command(python, str(release / "photo-enrich.py"), "--index", str(index), "--library", str(library),
                "--state", str(STATE), "worker", "--batch-size", "3", "--max-batches", "1", env=env, timeout=300)
        temporary = ROOT / "current.new"
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(release)
        temporary.replace(current)
        UNIT_PATH.write_text(payload["unit"])
        # JSON quoting produces systemd-compatible double-quoted path values (reject newlines).
        if any('\n' in str(p) for p in (index, library, STATE)):
            raise ValueError("Unexpected newline in source paths")
        ENV_PATH.write_text('\n'.join(k+'='+json.dumps(str(v)) for k,v in
            (("PHOTO_INDEX",index),("PHOTO_LIBRARY",library),("PHOTO_STATE",STATE)))+'\n')
        command("systemctl", "daemon-reload")
        command("systemd-analyze", "verify", str(UNIT_PATH))
        command("systemctl", "enable", UNIT)
        started = time.time()
        command("systemctl", "start", UNIT)
        for _ in range(60):
            if PROM.exists() and PROM.stat().st_mtime >= started and "photo_enrichment_inventory" in PROM.read_text():
                command("systemctl", "is-active", UNIT)
                status()
                return
            time.sleep(1)
        raise RuntimeError("Worker did not publish fresh inventory telemetry")
    except BaseException:
        subprocess.run(["systemctl", "stop", UNIT])
        if not enabled:
            subprocess.run(["systemctl", "disable", UNIT])
        for path, content in originals.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        current.unlink(missing_ok=True)
        if previous:
            current.symlink_to(previous)
        subprocess.run(["systemctl", "daemon-reload"])
        if active:
            subprocess.run(["systemctl", "start", UNIT])
        # Keep new committed enrichment facts; source catalog/originals were never written.
        print("Previous service restored; enrichment facts retained. Backup:", backup, file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
