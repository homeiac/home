#!/usr/bin/env bash
# Use the existing personal GitHub login for the homelab, without changing the
# active enterprise login or writing authentication material to the repository.
set -euo pipefail
export GH_TOKEN="$(gh auth token --hostname github.com --user gshiva)"
case "${1:?gh or git}" in
  gh) shift; exec gh "$@" ;;
  git) shift; exec git -c credential.helper= -c 'credential.helper=!gh auth git-credential' "$@" ;;
  *) exit 2 ;;
esac
