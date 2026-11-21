#!/usr/bin/env bash
# Run in a private terminal. The password is sent directly to piglet's daemon.
set -euo pipefail
ssh -t "root@${1:-pumped-piglet.maas}" python3 /usr/local/sbin/filebrowser-efs-view.py unlock
