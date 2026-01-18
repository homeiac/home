#!/bin/bash
# Pre-push checks for frigate-health-checker
# Run this BEFORE pushing to avoid CI failures

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/../../apps/frigate-health-checker"

cd "$APP_DIR"

echo "=== Formatting ==="
poetry run ruff format src/ tests/

echo ""
echo "=== Linting ==="
poetry run ruff check src/ tests/

echo ""
echo "=== Type Checking ==="
poetry run mypy src/

echo ""
echo "=== Tests ==="
poetry run pytest

echo ""
echo "=== Docker Build ==="
docker build -t frigate-health-checker:local .

echo ""
echo "✅ All checks passed - safe to push"
