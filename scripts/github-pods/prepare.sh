#!/usr/bin/env bash
# Build a local test image and create two credential-free Rancher Desktop pods.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Rancher Desktop's credential helper may not be on a non-interactive shell PATH.
RD_BIN="/Applications/Rancher Desktop.app/Contents/Resources/resources/darwin/bin"
[[ ! -d "$RD_BIN" ]] || export PATH="$RD_BIN:$PATH"
docker --context rancher-desktop build -t gh-auth-pod-test:1 "$SCRIPT_DIR"
python3 "$SCRIPT_DIR/pod-test.py" prepare
