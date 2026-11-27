"""Add cricket to a versioned copy of the live private review app, retaining rollback data."""

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path("/opt/photo-enrichment")
STATE = Path("/local-3TB-backup/photo-enrichment/cricket")
UNIT = Path("/etc/systemd/system/photo-enrichment-gui.service")


def run(*args: str) -> None:
    """Run bounded service controls and stop on failure."""
    timeout = (
        750
        if args[:2] == ("systemctl", "restart")
        and args[-1].startswith("cricket-highlights")
        else 120
    )
    subprocess.run(args, check=True, timeout=timeout)


def main() -> None:
    """Verify preconditions, back up configuration, bootstrap private state, then health-check UI."""
    os.umask(0o077)
    value = json.load(sys.stdin)
    previous = (ROOT / "gui").resolve()
    if str(previous) != value["previous"] or UNIT.read_text() != value["unit"]:
        raise RuntimeError("Live release changed; inspect again before deployment")
    for name, expected in value["hashes"].items():
        if hashlib.sha256((previous / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Deployed source changed: " + name)
    stamp = str(time.time_ns())
    backup = ROOT / "backups" / ("cricket-" + stamp)
    backup.mkdir(parents=True)
    (backup / "previous-release.txt").write_text(str(previous))
    (backup / UNIT.name).write_text(value["unit"])
    STATE.mkdir(parents=True, exist_ok=True)
    # Never copy a bootstrap ledger over live corrections or an existing operator policy.
    for name, content in value["private"].items():
        path = STATE / name
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Invalid private path")
        if path.exists():
            continue
        if not path.resolve().is_relative_to(STATE):
            raise ValueError("Invalid private path")
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(content))
    with sqlite3.connect(STATE / "ledger.sqlite3") as db:
        with sqlite3.connect(backup / "ledger.sqlite3") as destination:
            db.backup(destination)
        owners = list(db.execute("SELECT DISTINCT owner FROM albums"))
    if len(owners) != 1:
        raise ValueError("Expected one owner")
    policy_path = STATE / "policy.json"
    policy = json.loads(policy_path.read_text())
    if not (STATE / "installed").exists():
        policy["enabled"] = False
        for name, backend in policy["backends"].items():
            backend["transport"] = "http"
            backend.pop("host", None)
            if name == "mac":
                backend["key_file"] = "/opt/knowledge-index/mac-bonsai.key"
        policy_path.write_text(json.dumps(policy))
    release = ROOT / "releases" / value["release"]
    if not release.exists():
        shutil.copytree(
            previous,
            release,
            symlinks=True,
            ignore=shutil.ignore_patterns("venv", "__pycache__"),
        )
        (release / "venv").symlink_to(previous / "venv")
    for name, content in value["files"].items():
        target = release / name
        if not target.resolve().is_relative_to(release):
            raise ValueError("Invalid release path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    run(
        str(release / "venv/bin/python"),
        "-m",
        "compileall",
        "-q",
        str(release / "cricket"),
        str(release / "photo_enrichment/server.py"),
    )
    updated = value["unit"]
    lines = []
    for line in updated.splitlines():
        if line.startswith("ExecStart=") and "--cricket-ledger" not in line:
            line += (
                " --cricket-ledger "
                + str(STATE / "ledger.sqlite3")
                + " --cricket-owner "
                + owners[0][0]
                + " --cricket-people "
                + str(STATE / "people.json")
            )
        lines.append(line)
    try:
        temporary = ROOT / "gui.cricket-new"
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(release)
        temporary.replace(ROOT / "gui")
        UNIT.write_text("\n".join(lines) + "\n")
        run("systemd-analyze", "verify", str(UNIT))
        run("systemctl", "daemon-reload")
        run("systemctl", "restart", UNIT.name)
        for _ in range(30):
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:8765/api/config", timeout=3
                ) as response:
                    if json.load(response).get("cricket"):
                        break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError("Cricket UI failed health check")
    except BaseException:
        UNIT.write_text(value["unit"])
        (ROOT / "gui").unlink()
        (ROOT / "gui").symlink_to(previous)
        run("systemctl", "daemon-reload")
        run("systemctl", "restart", UNIT.name)
        raise
    (STATE / "installed").write_text(stamp)
    authority = (STATE / "ledger.sqlite3").resolve().parent
    worker = UNIT.with_name(
        "cricket-highlights-ssd.service"
        if authority != STATE
        else "cricket-highlights.service"
    )
    if worker.exists():
        shutil.copy2(worker, backup / worker.name)
    worker.write_text(f"""[Unit]
Description=Best-effort cricket highlight analysis
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
WorkingDirectory={release}
ExecStart={release}/venv/bin/python -m cricket.worker --ledger {STATE}/ledger.sqlite3 --evidence {STATE}/evidence --state {STATE}/worker --policy {STATE}/policy.json --portrait {STATE}/reference.jpg --prom /var/lib/prometheus/node-exporter/cricket_highlights.prom
Restart=on-failure
RestartSec=30
TimeoutStopSec=700
Nice=15
IOSchedulingClass=idle
CPUQuota=200%
MemoryHigh=512M
MemoryMax=1G
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths={STATE} {authority} /var/lib/prometheus/node-exporter
[Install]
WantedBy=multi-user.target
""")
    run("systemd-analyze", "verify", str(worker))
    run("systemctl", "daemon-reload")
    # Policy is initially disabled; service persists queue state and reports readiness.
    run("systemctl", "enable", "--now", worker.name)
    run("systemctl", "restart", worker.name)
    sys.stdout.write(
        json.dumps(
            {
                "ui": "healthy",
                "worker": "enabled" if policy["enabled"] else "disabled",
                "backup": str(backup),
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
