#!/usr/bin/env bash
# Run in your own terminal: the password is entered directly on piglet, never here.
set -euo pipefail
ssh -t "root@${1:-pumped-piglet.maas}" python3 /usr/local/sbin/filebrowser-verify-efs-certificate.py
