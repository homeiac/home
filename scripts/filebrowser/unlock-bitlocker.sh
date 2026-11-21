#!/usr/bin/env bash
# Run in your own terminal; SSH provides a private password prompt on piglet.
set -euo pipefail
ssh -t "root@${1:-pumped-piglet.maas}" /usr/local/sbin/filebrowser-unlock-bitlocker
