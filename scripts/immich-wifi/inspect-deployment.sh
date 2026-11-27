#!/usr/bin/env bash
# Read only: inspect GitOps ownership and the Google Wi-Fi path.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/load-network.sh"
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
kubectl --request-timeout=15s -n flux-system get gitrepository photo-enrichment-preview
kubectl --request-timeout=15s -n flux-system get kustomization photo-enrichment-preview
kubectl --request-timeout=15s -n monitoring get secret nut-deploy-ssh-key -o go-template='{{range $k,$v := .data}}{{$k}}{{"\n"}}{{end}}'
curl --interface "${WIFI_INTERFACE:-en0}" --connect-timeout 5 --max-time 10 -sS -o /dev/null -w 'HA status=%{http_code} local=%{local_ip} remote=%{remote_ip}\n' "http://$RELAY_ADDRESS:8123/"
curl --interface "${WIFI_INTERFACE:-en0}" --connect-timeout 3 --max-time 5 -sS "http://$GOOGLE_GATEWAY_ADDRESS/api/v1/status"
