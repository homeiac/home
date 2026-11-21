#!/usr/bin/env bash
# Inspect service failures, omitting any authentication-related log lines.
set -euo pipefail
ssh -o BatchMode=yes "root@${1:-pumped-piglet.maas}" 'bash -s' <<'REMOTE'
systemctl status filebrowser-proxy.socket filebrowser-proxy.service --no-pager || true
journalctl -u filebrowser-proxy.service -n 25 --no-pager
pct exec 104 -- bash -c 'systemctl show filebrowser -p ActiveState -p SubState -p Result -p ExecMainStatus; journalctl -u filebrowser -n 30 --no-pager | grep -viE "password|secret|token|credential"; ss -lnt; findmnt -M /srv/files/SSK; ls -ld /var/lib/filebrowser; systemctl --failed --no-pager; ls -l /var/log/journal /run/log/journal 2>/dev/null'
REMOTE
