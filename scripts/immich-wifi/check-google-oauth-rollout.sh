#!/usr/bin/env bash
# Compact read-only rollout evidence without rendering Helm values or secrets.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
kubectl --request-timeout=20s -n immich-pilot get helmrelease immich -o jsonpath='{range .status.conditions[*]}{.type}{": "}{.status}{" "}{.message}{"\n"}{end}'
kubectl --request-timeout=20s -n immich-pilot get pods -l app.kubernetes.io/instance=immich
bash "$(dirname "${BASH_SOURCE[0]}")/inspect-auth.sh"
