#!/usr/bin/env bash
# Run privately in your terminal to display the bootstrap FileBrowser login.
set -euo pipefail
echo 'Username: admin'
ssh "root@${1:-pumped-piglet.maas}" 'pct exec 104 -- cat /root/filebrowser-login.env'
