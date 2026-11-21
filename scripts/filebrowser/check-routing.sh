#!/usr/bin/env bash
# Read-only Flux/Traefik status and HTTPS reachability.
set -euo pipefail
export KUBECONFIG=${KUBECONFIG:-$HOME/kubeconfig}
kubectl -n flux-system get kustomizations flux-system cert-manager-config traefik-config
kubectl -n flux-system get kustomization cert-manager-config -o jsonpath='{.status.conditions}{"\n"}'
kubectl -n kube-system get service filebrowser-external -o wide
kubectl -n kube-system get ingressroute filebrowser -o yaml
curl -fsS --max-time 15 -o /dev/null -w 'HTTPS status=%{http_code} certificate_verify=%{ssl_verify_result}\n' https://files.app.home.panderosystems.com/
