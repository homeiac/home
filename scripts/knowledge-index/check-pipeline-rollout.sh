#!/bin/bash
# Read-only rollout check: Flux source, dashboard owner/panels, worker instrumentation.
# Usage: CB_HOST=root@<inventory-host> bash scripts/knowledge-index/check-pipeline-rollout.sh
# Uses existing kubeconfig and SSH authentication; never prints service credentials.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/../backup/cloud-backup-common.sh"
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
kubectl get gitrepository flux-system -n flux-system -o json | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("Flux source:", d["spec"]["ref"])
print("Flux revision:", d.get("status", {}).get("artifact", {}).get("revision", "unknown"))'
kubectl get configmap grafana-dashboard-knowledge-index -n monitoring -o json | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("Dashboard Flux owner:", d["metadata"].get("labels", {}).get("kustomize.toolkit.fluxcd.io/name", "not labelled"))
j = json.loads(d["data"]["knowledge-index.json"])
titles = {p["title"] for p in j["panels"]}
for title in ("Summary progress over time", "Pipeline bottlenecks", "Value stream map"):
    print(title + ":", "present" if title in titles else "absent")'
cb_ssh "python3 -" <<'PY'
from pathlib import Path
import hashlib
import sys
import subprocess
print("Host Python:", sys.version.split()[0])
print(subprocess.run(["systemctl", "show", "knowledge-index-enrich", "-p", "Transient", "-p", "FragmentPath", "-p", "DropInPaths", "-p", "User", "-p", "Nice", "-p", "IOSchedulingClass"], capture_output=True, text=True).stdout.strip())
print("Worker source SHA256:", hashlib.sha256(Path("/opt/knowledge-index/enrichers/media_summary.py").read_bytes()).hexdigest())
print("Worker unit:", subprocess.run(["systemctl", "is-active", "knowledge-index-enrich"], capture_output=True, text=True).stdout.strip())
for path in ("/opt/knowledge-index/enrichers/pipeline_metrics.py", "/var/lib/prometheus/node-exporter/knowledge_index_pipeline.prom"):
    print(path + ":", "present" if Path(path).exists() else "absent")
for entry in Path("/proc").glob("[0-9]*/cmdline"):
    try:
        argv = entry.read_bytes().split(b"\0")
    except OSError:
        continue
    if b"/opt/knowledge-index/enrichers/media_summary.py" in argv:
        print("Worker PID:", entry.parent.name, "--prom:", b"--prom" in argv)
        for flag in (b"--model", b"--enricher", b"--batch-size", b"--api", b"--num-ctx", b"--frames"):
            if flag in argv:
                print(flag.decode() + ":", argv[argv.index(flag) + 1].decode())
PY
