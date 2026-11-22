#!/usr/bin/env bash
# Serve the article, slide deck and linked runbooks locally for visual review.
# Usage: scripts/blog/preview-photo-pipeline.sh [port]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PORT="${1:-8879}"
printf 'Slides: http://127.0.0.1:%s/docs/blog/local-photo-pipeline-slides.html\n' "$PORT"
exec python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$REPO_DIR"
