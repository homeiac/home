#!/usr/bin/env bash
# Read-only checks for CPU priority, duplicate VPA targets, and controller errors.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
kubectl -n ollama get vpa -o wide
kubectl -n ollama get vpa ollama-cpu -o jsonpath='{.spec.resourcePolicy}{"\n"}{.status.recommendation}{"\n"}'
kubectl -n ollama get pods -l app=ollama-gpu -o jsonpath='{range .items[*]}{.metadata.name}{" QoS="}{.status.qosClass}{"\n"}{range .spec.containers[*]}{.name}{" requests="}{.resources.requests}{" limits="}{.resources.limits}{"\n"}{end}{.status.containerStatuses[*].allocatedResources}{"\n"}{.status.conditions}{"\n"}{end}'
kubectl get vpa -A -o json | python3 -c '
import json, sys
from collections import Counter
items=json.load(sys.stdin)["items"]
counts=Counter((v["metadata"]["namespace"],v["spec"]["targetRef"]["kind"],v["spec"]["targetRef"]["name"]) for v in items)
duplicates=[target for target,count in counts.items() if count>1]
print("Duplicate VPA targets:", duplicates)
sys.exit(bool(duplicates))
'
for component in recommender updater; do
  kubectl -n kube-system rollout status "deployment/ollama-vpa-$component" --timeout=30s
  kubectl -n kube-system logs "deployment/ollama-vpa-$component" --since=5m --tail=30
done
kubectl top pod -n ollama
