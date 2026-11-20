#!/usr/bin/env python3
"""Read live pipeline timing, output and scrape cadence via a temporary Prometheus port-forward."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request


def main() -> None:
    port = int(os.environ.get("LOCAL_PORT", "29091"))
    env = dict(os.environ, KUBECONFIG=os.environ.get("KUBECONFIG", str(Path.home() / "kubeconfig")))
    pf = subprocess.Popen(["kubectl", "port-forward", "-n", "monitoring", "svc/kube-prometheus-stack-prometheus", f"{port}:9090"],
                          env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"

    def get(path):
        with urllib.request.urlopen(base + path, timeout=15) as response:
            return json.load(response)

    try:
        for _ in range(30):
            try:
                get("/api/v1/status/buildinfo")
                break
            except OSError:
                time.sleep(0.2)
        for target in get("/api/v1/targets")["data"]["activeTargets"]:
            if target["labels"].get("job") == "proxmox-node-exporter" and target["labels"].get("instance") == "pumped-piglet":
                print("Scrape:", target["health"], "interval", target.get("scrapeInterval"), "last", target["lastScrape"])
        for query in ("media_pipeline_worker_stage", "time() - media_pipeline_stage_started_timestamp_seconds",
                      "time() - media_pipeline_heartbeat_timestamp_seconds", "sum by(stage)(media_pipeline_stage_seconds_total)",
                      "sum by(kind,status)(media_pipeline_persisted_items_total)",
                      "sum by(stage)(rate(media_pipeline_stage_seconds_total[5m]))",
                      "sum by(phase)(media_pipeline_ollama_seconds_total)"):
            result = get("/api/v1/query?" + urllib.parse.urlencode({"query": query}))["data"]["result"]
            print(query)
            for item in result:
                print(" ", {k: v for k, v in item["metric"].items() if k != "__name__"}, item["value"][1])
    finally:
        pf.terminate()
        pf.wait(timeout=5)


if __name__ == "__main__":
    main()
