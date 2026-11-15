#!/bin/bash
# Coordinated restart of all K3s servers (embedded etcd), with an optional IPv6-loopback fix
#
# Usage:
#   ./restart-all-servers.sh --check                 # read-only: state of every server
#   ./restart-all-servers.sh --yes [--pin-ipv4]      # fix + restart, ONLY if a server is unhealthy
#   ./restart-all-servers.sh --yes --force           # restart even if everything is healthy
#   ./restart-all-servers.sh --help
#
# Idempotent: with --yes it exits without touching anything when every server is already
# `active` with /readyz ok. --pin-ipv4 only changes what is still wrong (node-ip missing,
# kubeconfigs on [::1]), so re-running it is safe.
#
# Symptom: k3s "activating" forever on the servers, NRestarts in the hundreds, journal shows
#   Shutdown request received: controller-manager exited: unable to load configmap based
#   request-header-client-ca-file: Get "https://[::1]:6444/...": connect: connection refused
#
# Cause (2026-11-15): after a power cut the VMs booted with IPv6 (router advertisements from the
# ISP router) but WITHOUT IPv4 (the DHCP server, an OPNsense VM, was still down). With no node-ip,
# k3s auto-detected an IPv6-only node and wrote its internal kubeconfigs
# (/var/lib/rancher/k3s/server/cred/*.kubeconfig) with server https://[::1]:6444. Those persist.
# Later starts have IPv4, so the API server listens on 127.0.0.1:6444 while the controller-manager
# still dials [::1]:6444, is refused, and k3s exits. Restarting alone never fixes it.
#
# --pin-ipv4 (applied while k3s is stopped on every server):
#   1. adds `node-ip: <eth0 IPv4>` to /etc/rancher/k3s/config.yaml (backup kept), so k3s can't
#      auto-detect IPv6-only again
#   2. if cred/*.kubeconfig point at [::1], copies them to cred/backup-ipv6-<timestamp>/ and rewrites
#      https://[::1]:6444 -> https://127.0.0.1:6444 in place. Deleting them does NOT work: k3s only
#      regenerates them when its certs change, and exits with "supervisor.kubeconfig: no such file".
#
# Why all servers together: with embedded etcd a lone server can't reach quorum and times out, so
# servers restarting on their own schedules keep the whole cluster down.
#
# Access: qm guest exec through each Proxmox host (SSH into K3s VMs doesn't work, see CLAUDE.md).
# Servers (proxmox-host:vmid) from proxmox/inventory.txt; override with K3S_SERVERS="host:vmid ...".
# pve is addressed by IP because pve.maas doesn't resolve while MAAS (a VM on pve) is down.
# Log: every run is tee'd to $K3S_LOG_DIR (default ~/.local/state/homelab/k3s/).
# Story: docs/blog/2026-11-15-k3s-restart-loop-ipv6-loopback.md

set -euo pipefail

readonly K3S_SERVERS="${K3S_SERVERS:-pumped-piglet.maas:105 still-fawn.maas:108 192.168.4.122:107 fun-bedbug.maas:114}"
readonly WAIT_SECONDS="${WAIT_SECONDS:-600}"
readonly POLL_SECONDS=15
readonly LOG_DIR="${K3S_LOG_DIR:-$HOME/.local/state/homelab/k3s}"
readonly CRED=/var/lib/rancher/k3s/server/cred
readonly CONF=/etc/rancher/k3s/config.yaml

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; }
log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { log "ERROR: $*"; exit 1; }

MODE="" PIN=0 FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) MODE=check;;
    --yes) MODE=restart;;
    --pin-ipv4) PIN=1;;
    --force) FORCE=1;;
    -h|--help) usage; exit 0;;
    *) usage; die "unknown option: $1";;
  esac
  shift
done
[[ -n "$MODE" ]] || { usage; exit 1; }
[[ "$MODE" == restart || ( $PIN -eq 0 && $FORCE -eq 0 ) ]] || die "--pin-ipv4/--force need --yes"
command -v python3 >/dev/null || die "python3 required (parses qm guest exec JSON)"

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/restart-all-servers-$(date +%Y%m%d-%H%M%S)-$MODE.log"
exec > >(tee -a "$LOG") 2>&1
log "restart-all-servers mode=$MODE pin-ipv4=$PIN force=$FORCE (log: $LOG)"

# guest <proxmox-host> <vmid> <timeout> <command>: run a bash command inside the VM.
# Prints the command's stdout+stderr; never fails the script (callers judge the output).
guest() {
  local host="$1" vmid="$2" t="$3" cmd="$4"
  ssh -o ConnectTimeout=10 -o BatchMode=yes "root@$host" \
      "qm guest exec $vmid --timeout $t -- bash -c $(printf '%q' "$cmd")" 2>&1 \
    | python3 -c 'import json,sys
t=sys.stdin.read()
try:
    d=json.loads(t); sys.stdout.write(d.get("out-data","")+d.get("err-data",""))
except ValueError:
    sys.stdout.write("qm guest exec failed: "+t.strip()[:200])' || true
}

# run_all <timeout> <command>: same command on every server in parallel, one line per server.
run_all() {
  local t="$1" cmd="$2" s out pids=()
  for s in $K3S_SERVERS; do
    ( out="$(guest "${s%:*}" "${s#*:}" "$t" "$cmd")"; out="${out%$'\n'}"; echo "  $s: ${out//$'\n'/ | }" ) &
    pids+=($!)
  done
  wait "${pids[@]}"
}

readonly STATE_CMD='echo "$(systemctl is-active k3s) restarts=$(systemctl show k3s -p NRestarts --value)" \
  "loopback=$(sed -n "s/.*server: //p" '"$CRED"'/controller.kubeconfig 2>/dev/null)" \
  "node-ip=$(sed -n "s/^node-ip: *//p" '"$CONF"' 2>/dev/null)" \
  "readyz=$(k3s kubectl get --raw /readyz 2>/dev/null || echo no)"'
readonly HEALTHY_RE='^  [^ ]+: active restarts=[0-9]+ .*readyz=ok$'

count_unhealthy() { grep -cvE "$HEALTHY_RE" <<<"$1" || true; }

# --- preflight: every Proxmox host reachable and its VM running
for s in $K3S_SERVERS; do
  st="$(ssh -o ConnectTimeout=10 -o BatchMode=yes "root@${s%:*}" "qm status ${s#*:}" 2>&1)" \
    || die "$s: Proxmox host unreachable ($st)"
  [[ "$st" == *running* ]] || die "$s: VM not running ($st) - start it first (qm start ${s#*:})"
done

log "State"
state="$(run_all 30 "$STATE_CMD")"; echo "$state"
unhealthy="$(count_unhealthy "$state")"
[[ "$MODE" == check ]] && { log "$unhealthy unhealthy server(s)"; exit 0; }

if [[ "$unhealthy" -eq 0 && $FORCE -eq 0 ]]; then
  log "All servers healthy - nothing to do (use --force to restart anyway)"
  exit 0
fi

log "Stopping k3s on all servers"
run_all 150 'systemctl stop k3s; systemctl is-active k3s || true'

if [[ $PIN -eq 1 ]]; then
  log "Pinning node-ip to IPv4 and fixing [::1] kubeconfigs (only where needed)"
  run_all 30 'set -e
    TS=$(date +%Y%m%d-%H%M%S)
    IP=$(ip -4 -o addr show eth0 | awk "{print \$4}" | cut -d/ -f1 | head -1)
    if [ -z "$IP" ]; then echo "NO IPv4 on eth0 yet - skipped (fix DHCP first)"; exit 0; fi
    mkdir -p "$(dirname '"$CONF"')"; touch '"$CONF"'
    if grep -q "^node-ip:" '"$CONF"'; then echo "node-ip ok ($(sed -n "s/^node-ip: *//p" '"$CONF"'))"
    else cp -a '"$CONF"' '"$CONF"'.bak-$TS; printf "node-ip: %s\n" "$IP" >> '"$CONF"'; echo "node-ip: $IP added"; fi
    # Restore if an earlier version of this script moved the kubeconfigs aside (cred/stale-ipv6-*)
    if [ ! -f '"$CRED"'/controller.kubeconfig ]; then
      OLD=$(ls -d '"$CRED"'/stale-ipv6-* 2>/dev/null | tail -1)
      if [ -n "$OLD" ]; then cp -a "$OLD"/*.kubeconfig '"$CRED"'/; echo "restored kubeconfigs from $OLD"; fi
    fi
    if grep -qF "[::1]" '"$CRED"'/*.kubeconfig 2>/dev/null; then
      mkdir -p '"$CRED"'/backup-ipv6-$TS; cp -a '"$CRED"'/*.kubeconfig '"$CRED"'/backup-ipv6-$TS/
      sed -i "s#https://\[::1\]:6444#https://127.0.0.1:6444#" '"$CRED"'/*.kubeconfig
      echo "kubeconfigs [::1] -> 127.0.0.1 (backup cred/backup-ipv6-$TS)"
    else echo "kubeconfigs ok"; fi'
fi

log "Starting k3s on all servers together"
run_all 30 'systemctl reset-failed k3s 2>/dev/null || true; systemctl start --no-block k3s; echo started'

log "Waiting until every server is active with /readyz ok (up to ${WAIT_SECONDS}s)"
for ((i = 1; i * POLL_SECONDS <= WAIT_SECONDS; i++)); do
  sleep "$POLL_SECONDS"
  state="$(run_all 30 "$STATE_CMD")"
  unhealthy="$(count_unhealthy "$state")"
  log "+$((i * POLL_SECONDS))s: $unhealthy unhealthy"; echo "$state"
  if [[ "$unhealthy" -eq 0 ]]; then
    first="${K3S_SERVERS%% *}"
    guest "${first%:*}" "${first#*:}" 30 'k3s kubectl get nodes -o wide'
    log "Cluster healthy"
    exit 0
  fi
  if (( i % 4 == 0 )); then   # every minute: last k3s error on each server, for diagnosis
    log "Last k3s error per server (90s window)"
    run_all 30 'journalctl -u k3s --since -90s --no-pager | grep -E "level=(error|fatal)|Shutdown request" | tail -1 | cut -c1-220'
  fi
done
die "not healthy after ${WAIT_SECONDS}s - see $LOG"
