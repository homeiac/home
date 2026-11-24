"""Publish a loopback-only Metal endpoint; keep the model awake on AC power."""

import json
import logging
import os
import signal
import subprocess
import time
import urllib.request

from runtime import ROOT, start

POLICY_URL = "https://raw.githubusercontent.com/homeiac/home/codex/photo-enrichment-217/scripts/knowledge-index/mac-bonsai/policy.json"
PORT = 19476


def policy():
    with urllib.request.urlopen(POLICY_URL, timeout=10) as response:
        doc = json.load(response)
    if type(doc["enabled"]) is not bool or type(doc["slots"]) is not int or not 1 <= doc["slots"] <= 20:
        raise ValueError("Invalid Mac worker policy")
    if type(doc["offered"]) is not int or not 1 <= doc["offered"] <= 20:
        raise ValueError("Invalid client concurrency")
    return (doc["slots"], doc["offered"]) if doc["enabled"] else (0, 0)


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    os.umask(0o077)
    server = tunnel = awake = None
    current = desired = (0, 0)
    refresh = 0
    try:
        while True:
            if time.monotonic() >= refresh:
                try:
                    desired = policy()
                except (OSError, ValueError, KeyError) as exc:
                    logging.warning("Git policy unavailable (%s)", type(exc).__name__)
                refresh = time.monotonic() + 60
            if current != desired or (server is not None and server.poll() is not None):
                stop(tunnel)
                stop(server)
                stop(awake)
                server = tunnel = awake = None
                current = desired
            slots, offered = current
            if slots and server is None:
                server = start(slots, PORT, subprocess.DEVNULL, ROOT / "server.key", offered)
                logging.info("Started Metal with %d slots and up to %d requests", slots, offered)
            if server is not None and (awake is None or awake.poll() is not None):
                awake = keep_awake(server)
                logging.info("Keeping the model awake on AC power; display sleep remains enabled")
            if server is not None and (tunnel is None or tunnel.poll() is not None):
                try:
                    probe = urllib.request.Request(
                        f"http://127.0.0.1:{PORT}/props",
                        headers={"Authorization": "Bearer " + (ROOT / "server.key").read_text().strip()},
                    )
                    with urllib.request.urlopen(probe, timeout=2) as response:
                        props = json.load(response)
                    if props.get("model_alias") != "bonsai-27b-metal" or props.get("total_slots") != slots:
                        raise ValueError("Model identity or capacity mismatch")
                    tunnel = subprocess.Popen(
                        [
                            "/usr/bin/ssh",
                            "-NT",
                            "-o",
                            "BatchMode=yes",
                            "-o",
                            "ExitOnForwardFailure=yes",
                            "-o",
                            "ConnectTimeout=8",
                            "-o",
                            "ServerAliveInterval=15",
                            "-o",
                            "ServerAliveCountMax=2",
                            "-R",
                            f"127.0.0.1:{PORT}:127.0.0.1:{PORT}",
                            os.environ["CB_HOST"],
                        ]
                    )
                except (OSError, ValueError):
                    pass
            time.sleep(5)
    finally:
        stop(tunnel)
        stop(server)
        stop(awake)


def keep_awake(server):
    """Release the AC-only assertion automatically when this model exits."""
    return subprocess.Popen(["/usr/bin/caffeinate", "-s", "-w", str(server.pid)])


def terminate(signum, frame):
    raise SystemExit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    main()
