#!/usr/bin/env bash
# Read-only checks of the encrypted inventory's Wi-Fi -> PVE -> Traefik path.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/load-network.sh"
export KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
ifconfig | awk '/^[a-zA-Z0-9]/ || /inet /'
route -n get "$RELAY_ADDRESS"
route -n get "$GOOGLE_GATEWAY_ADDRESS"
scutil --dns | awk '/resolver|nameserver|domain|if_index/'
dig +time=2 +tries=1 @"$GOOGLE_GATEWAY_ADDRESS" "$IMMICH_HOSTNAME" A
ssh -o Hostname="$PVE_ADDRESS" -o BatchMode=yes -o ConnectTimeout=8 "root@$PVE_HOSTNAME" "bash -s -- $IMMICH_HOSTNAME" <<'REMOTE'
set -eu
ip -br -4 addr
ip -4 route
ss -lntup
systemctl show ha-proxy.service -p ActiveState -p ExecStart
iptables -S INPUT
curl --connect-timeout 3 --max-time 10 -sS -o /dev/null -w 'Immich HTTPS: %{http_code}\n' "https://$1/"
REMOTE
kubectl --request-timeout=15s -n immich-pilot get ingressroute,middleware,svc,pods -o wide
kubectl --request-timeout=15s -n kube-system get svc traefik -o wide
kubectl --request-timeout=15s -n flux-system get gitrepositories,kustomizations -o wide
