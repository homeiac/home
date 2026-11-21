#!/usr/bin/env bash
# Proxy the host socket into the LXC network namespace; no container IP/DNS needed.
set -euo pipefail
container_pid=$(lxc-info -n 104 -pH)
[[ $container_pid =~ ^[0-9]+$ ]] && [[ -e /proc/$container_pid/ns/net ]]
exec nsenter --no-fork -t "$container_pid" -n \
    setpriv --reuid=nobody --regid=nogroup --clear-groups \
    /lib/systemd/systemd-socket-proxyd localhost:8080
