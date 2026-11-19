#!/usr/bin/env bash
# Isolated PostgreSQL integration tests; never connect to the homelab database.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_PYTHON="${TEST_PYTHON:-python3}"
container="photo-pipeline-test-$$"
scratch="$(mktemp -d)"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true; rm -rf "$scratch"' EXIT
docker run --rm -d --name "$container" -e POSTGRES_HOST_AUTH_METHOD=trust \
  -p 127.0.0.1::5432 postgres:16.11 >/dev/null
for _ in $(seq 1 60); do
  if docker exec "$container" pg_isready -U postgres >/dev/null 2>&1; then break; fi
  sleep 1
done
port="$(docker port "$container" 5432/tcp | cut -d: -f2)"
cat > "$scratch/pg_service.conf" <<EOF
[photo_pipeline]
host=127.0.0.1
port=$port
dbname=postgres
user=postgres
sslmode=disable
EOF
export PGSERVICEFILE="$scratch/pg_service.conf"
export PHOTO_PG_SERVICE=photo_pipeline
"$TEST_PYTHON" "$SCRIPT_DIR/test-photo-postgres.py"
