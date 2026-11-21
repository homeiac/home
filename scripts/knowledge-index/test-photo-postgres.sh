#!/usr/bin/env bash
# Isolated PostgreSQL integration tests; never connect to the homelab database.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_PYTHON="${TEST_PYTHON:-python3}"
container="photo-pipeline-test-$$"
scratch="$(mktemp -d)"
# Use a disposable native server when a container engine is unavailable.
# TEST_PG_BIN must contain initdb and pg_ctl; never use a production PGDATA.
if [[ -n "${TEST_PG_BIN:-}" ]]; then
  trap '"$TEST_PG_BIN/pg_ctl" -D "$scratch/data" -m immediate stop >/dev/null 2>&1 || true; rm -rf "$scratch"' EXIT
  "$TEST_PG_BIN/initdb" -D "$scratch/data" -U postgres -A trust >/dev/null
  port="$("$TEST_PYTHON" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
  "$TEST_PG_BIN/pg_ctl" -D "$scratch/data" -l "$scratch/server.log" -o "-h 127.0.0.1 -p $port -k $scratch" -w start >/dev/null
else
  trap 'docker rm -f "$container" >/dev/null 2>&1 || true; rm -rf "$scratch"' EXIT
  docker run --rm -d --name "$container" -e POSTGRES_HOST_AUTH_METHOD=trust \
    -p 127.0.0.1::5432 postgres:16.11 >/dev/null
  for _ in $(seq 1 60); do
    if docker exec "$container" pg_isready -U postgres >/dev/null 2>&1; then break; fi
    sleep 1
  done
  port="$(docker port "$container" 5432/tcp | cut -d: -f2)"
fi
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
"$TEST_PYTHON" "$SCRIPT_DIR/test-photo-postgres.py" "$@"
