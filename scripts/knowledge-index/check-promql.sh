#!/bin/bash
# Run every dashboard and alert expression of the knowledge index against the LIVE Prometheus (syntax + data check)
#
# Usage: ./check-promql.sh            needs KUBECONFIG (scripts/k3s/get-kubeconfig.sh), python3 + pyyaml
# Port-forwards svc/kube-prometheus-stack-prometheus, substitutes the dashboard variables ($instance -> .*, prices/baseline -> defaults),
# and prints per expression: ERROR (invalid PromQL: fix it), ok(n) = n series, or empty (valid, no data yet, e.g. before the first backfill).
# Exit 1 if any expression is invalid. Read-only.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MON="$HERE/../../gitops/clusters/homelab/infrastructure/monitoring"
PORT="${LOCAL_PORT:-29090}"
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus "$PORT:9090" >/dev/null 2>&1 & PF=$!
trap 'kill $PF 2>/dev/null || true' EXIT
for _ in $(seq 1 20); do curl -sf "http://127.0.0.1:$PORT/-/ready" >/dev/null 2>&1 && break; sleep 0.5; done
python3 - "$MON" "$PORT" <<'PY'
import json, sys, urllib.parse, urllib.request, yaml
mon, port = sys.argv[1:3]
exprs = []
j = json.loads(list(yaml.safe_load(open(mon + "/dashboards/knowledge-index.yaml"))["data"].values())[0])
for p in j["panels"]:
    for t in p.get("targets", []):
        exprs.append(("panel: " + p["title"], t["expr"]))
for g in yaml.safe_load(open(mon + "/knowledge-index-alerting-rules.yaml"))["spec"]["groups"]:
    for r in g["rules"]:
        exprs.append(("alert: " + r["alert"], r["expr"]))
subs = {"$instance": ".*", "$price_photo": "0.002", "$price_video_min": "0.02", "$baseline_s": "2280"}
bad = 0
for name, e in exprs:
    for k, v in subs.items():
        e = e.replace(k, v)
    url = "http://127.0.0.1:%s/api/v1/query?%s" % (port, urllib.parse.urlencode({"query": e}))
    try:
        r = json.load(urllib.request.urlopen(url, timeout=30))
        n = len(r["data"]["result"])
        print("%-8s %s" % ("ok(%d)" % n if n else "empty", name))
    except urllib.error.HTTPError as ex:
        bad += 1
        print("ERROR    %s\n         %s\n         %s" % (name, e[:160], json.load(ex).get("error", "")[:200]))
print("%d expressions, %d invalid" % (len(exprs), bad))
sys.exit(1 if bad else 0)
PY
