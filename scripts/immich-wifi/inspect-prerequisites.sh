#!/usr/bin/env bash
# Read only: inspect packages and public host key; verify deploy image exists.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/load-network.sh"
ssh -o Hostname="$PVE_ADDRESS" -o BatchMode=yes -o ConnectTimeout=8 "root@$PVE_HOSTNAME" 'bash -s' <<'REMOTE'
set -eu
apt-cache policy haproxy dnsmasq-base
cat /etc/ssh/ssh_host_ed25519_key.pub
REMOTE
curl --fail --connect-timeout 5 --max-time 20 -sS https://hub.docker.com/v2/repositories/alpine/git/tags/v2.49.1 | python3 -c 'import json,sys; d=json.load(sys.stdin); print("Verified image:", d["name"], "digest:", d.get("digest"))'
