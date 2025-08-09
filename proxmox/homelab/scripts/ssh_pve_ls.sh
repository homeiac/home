#!/usr/bin/env bash
set -euo pipefail

# Wrapper script to reliably run SSH command to pve.maas with timeout and retries
key="$HOME/.ssh/id_ed25519_pve"
opts=(
  -i "$key"
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/dev/null
  -o ConnectTimeout=10
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=3
  -o PubkeyAcceptedAlgorithms=+ssh-ed25519
  -o HostKeyAlgorithms=+ssh-ed25519
  -vvv
)

echo "Starting SSH connection to pve.maas (root) with timeout and retries..."

# Parse --once option (single-shot mode)
once=0
if [[ ${1:-} == --once ]]; then
  once=1
  shift
fi

# Allow arbitrary command (default to 'ls' if none provided)
cmd=( "${@:-ls}" )

if (( once )); then
  exec timeout 15 ssh "${opts[@]}" -t root@pve.maas "${cmd[@]}"
fi

while true; do
  if timeout 15 ssh "${opts[@]}" -t root@pve.maas "${cmd[@]}"; then
    exit 0
  else
    echo "SSH command failed or timed out; retrying in 5 seconds..."
    sleep 5
  fi
done
