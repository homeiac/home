#!/bin/bash
# Fetch a working kubeconfig for the homelab K3s cluster into ~/kubeconfig (no SSH to the VMs needed)
#
# Usage: ./scripts/k3s/get-kubeconfig.sh [--force]      then: export KUBECONFIG=~/kubeconfig; kubectl get nodes
#
# How: K3s VM 105 (on pumped-piglet) holds /etc/rancher/k3s/k3s.yaml; we read it with `qm guest exec` (SSH to the VMs
# does not work) and point `server:` at the control-plane VIP (kube-vip). The file lives in $HOME, outside every git
# worktree, so all worktrees share it. It is a credential: mode 0600, NEVER commit it.
# Env: K3S_HOST (Proxmox host, default root@pumped-piglet.maas; from a laptop on the VPN use its IP: .maas DNS is hijacked),
#      K3S_VMID (default 105), K3S_API (default https://192.168.4.210:6443 = kube-vip VIP), KUBECONFIG_OUT (default ~/kubeconfig).
# Existing file is kept unless --force (then backed up to <file>.bak).
set -euo pipefail
HOST="${K3S_HOST:-root@pumped-piglet.maas}"; VMID="${K3S_VMID:-105}"
API="${K3S_API:-https://192.168.4.210:6443}"; OUT="${KUBECONFIG_OUT:-$HOME/kubeconfig}"
if [[ -s "$OUT" && "${1:-}" != --force ]]; then
  echo "$OUT exists; verifying (use --force to refetch)"
else
  [[ -s "$OUT" ]] && cp -p "$OUT" "$OUT.bak"
  TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
  RAW="$(ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" "qm guest exec $VMID -- cat /etc/rancher/k3s/k3s.yaml" 2>&1)" || {
    echo "ERROR: cannot reach $HOST: $RAW"
    echo "Hint: .maas names only resolve on the home network/Tailscale. Off the LAN, set K3S_HOST=root@<host address> (see CLAUDE.md > Cluster access)."; exit 1; }
  printf '%s' "$RAW" | python3 -c 'import json,sys; t=sys.stdin.read(); d=json.loads(t[t.index("{"):]); sys.stdout.write(d["out-data"])' > "$TMP" 2>/dev/null || true
  grep -q "^apiVersion: v1" "$TMP" || { echo "ERROR: did not get a kubeconfig from $HOST (VMID $VMID): is VM $VMID running?"; exit 1; }
  # K3s writes 127.0.0.1 (or, after the 2026-11 IPv6 incident, possibly [::1]:6444): replace whatever server it has
  sed -E "s#(server: ).*#\1$API#" "$TMP" > "$OUT"; chmod 600 "$OUT"
  echo "wrote $OUT (server $API)"
fi
KUBECONFIG="$OUT" kubectl get nodes
