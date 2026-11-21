#!/usr/bin/env python3
"""Explicitly approved preview only; normal deployment is Git + Flux.

Usage: CB_HOST=root@<inventory-host> python3 scripts/knowledge-index/deploy-pipeline-preview.py
         --expected-worker-sha SHA256 --confirm-preview
Backs up the dashboard locally and worker on-host. Preserves runtime model/settings.
Uses existing SSH/kubeconfig credentials; no credentials are embedded or printed.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

import yaml


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expected-worker-sha")
    ap.add_argument("--parallel", type=int, default=1, help="summaries in flight per worker")
    scope = ap.add_mutually_exclusive_group()
    scope.add_argument("--dashboard-only", action="store_true", help="refresh the preview without restarting the worker")
    scope.add_argument("--worker-only", action="store_true", help="deploy the host worker for a Flux-managed dashboard")
    ap.add_argument("--confirm-preview", action="store_true", required=True)
    args = ap.parse_args()
    if args.parallel < 1:
        ap.error("--parallel must be positive")
    if not args.dashboard_only and not args.expected_worker_sha:
        ap.error("--expected-worker-sha is required unless --dashboard-only is set")
    here = Path(__file__).resolve().parent
    env = dict(os.environ, KUBECONFIG=os.environ.get("KUBECONFIG", str(Path.home() / "kubeconfig")))
    command = ["kubectl", "get", "configmap", "grafana-dashboard-knowledge-index", "-n", "monitoring", "-o", "json"]
    if not args.worker_only:
        old = json.loads(subprocess.check_output(command, env=env))
        if old["metadata"].get("labels", {}).get("kustomize.toolkit.fluxcd.io/name"):
            raise RuntimeError("Dashboard is Flux-managed; deploy through Git instead")
        generated = yaml.safe_load(subprocess.check_output(["python3", str(here / "gen-dashboard.py")], text=True))
        backup = Path(tempfile.mkdtemp(prefix="knowledge-index-preview-"))
        (backup / "dashboard-before.json").write_text(json.dumps(old, indent=2))
        print("Dashboard backup:", backup / "dashboard-before.json", flush=True)
    if not args.dashboard_only:
        payload = {"expected_sha": args.expected_worker_sha, "parallel": args.parallel}
        for filename in ("media_summary.py", "pipeline_metrics.py", "summary_cache.py"):
            payload[filename] = (here / "enrichers" / filename).read_text()
        remote = (here / "host/rollout-pipeline-preview.py").read_text()
        subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", os.environ.get("CB_HOST", "root@pumped-piglet.maas"),
                        "python3 -c " + shlex.quote(remote)], input=json.dumps(payload), text=True, check=True)
    if args.worker_only:
        return
    # Keep resourceVersion: fail rather than overwrite a concurrently changed dashboard.
    old["data"].update(generated["data"])
    subprocess.run(["kubectl", "replace", "-f", "-"], input=json.dumps(old), text=True, check=True, env=env)
    print("Preview dashboard published. Source changes still need the normal PR/Flux rollout.")


if __name__ == "__main__":
    main()
