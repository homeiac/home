#!/usr/bin/env bash
# Read only the verifier's non-secret result; never reads the PFX or password.
set -euo pipefail
ssh -o BatchMode=yes "root@${1:-pumped-piglet.maas}" \
  'if test -f /run/filebrowser-efs-verification/result.json; then cat /run/filebrowser-efs-verification/result.json; else echo "Verification has not started."; fi'
