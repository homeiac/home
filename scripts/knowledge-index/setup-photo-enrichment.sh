#!/bin/bash
# Install the isolated photo-review toolchain without changing system Python (#217).
# Usage: setup-photo-enrichment.sh /path/to/venv ; PYTHON=python3.12 is also supported.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${1:?provide a virtualenv directory outside the photo library}"
PYTHON="${PYTHON:-python3.13}"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install -r "$HERE/photo_enrichment/requirements.txt"
