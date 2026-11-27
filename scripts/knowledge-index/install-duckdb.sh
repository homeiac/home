#!/bin/bash
# Install a pinned DuckDB into a venv on the Proxmox host (idempotent), then smoke-test Parquet round trip
#
# Usage: ./install-duckdb.sh [--status]          needs CB_HOST (e.g. root@<host ip>) like the other backup scripts
# Venv: /opt/knowledge-index/venv     pin: DUCKDB_VERSION below (PyPI release, >= 2 weeks old when pinned; see issue #212)
# Why on the host: index builds and queries must never run inside K3s VM 105 (bulk disk writes there stall etcd).
# Pin history: 1.5.6 (released 2026-09-28; chosen 2026-11-16 over the newer 2.0.0 major, 26 days old at the time).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../backup/cloud-backup-common.sh"
readonly DUCKDB_VERSION="${DUCKDB_VERSION:-1.5.6}"
readonly VENV=/opt/knowledge-index/venv
if [[ "${1:-}" == --status ]]; then
  cb_ssh "[ -x $VENV/bin/python ] && $VENV/bin/python -c 'import duckdb; print(\"duckdb\", duckdb.__version__)' || echo 'duckdb not installed'"
  exit 0
fi
cb_ssh "DUCKDB_VERSION=$DUCKDB_VERSION VENV=$VENV bash -s" <<'EOS'
set -euo pipefail
# The host has no python3-venv (ensurepip) package: build a pip-less venv and install with the system pip (--python, pip >= 22.3).
[[ -x $VENV/bin/python ]] || { rm -rf "$VENV"; mkdir -p "$(dirname "$VENV")"; python3 -m venv --without-pip "$VENV"; echo "created $VENV"; }
have=$($VENV/bin/python -c 'import duckdb; print(duckdb.__version__)' 2>/dev/null || true)
if [[ "$have" == "$DUCKDB_VERSION" ]]; then echo "duckdb $have already installed"
else python3 -m pip --python "$VENV/bin/python" install --quiet --disable-pip-version-check --no-cache-dir "duckdb==$DUCKDB_VERSION"; fi
python3 -m pip --python "$VENV/bin/python" install --quiet --disable-pip-version-check --only-binary=:all: 'Pillow==12.0.0' 'pillow-heif==1.1.1' 'rawpy==0.25.1'
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
$VENV/bin/python - "$T" <<'PY'
import duckdb, sys
t = sys.argv[1]
con = duckdb.connect()
con.execute(f"COPY (SELECT i AS id, 'f'||i AS name FROM range(1000) t(i)) TO '{t}/x.parquet' (FORMAT parquet)")
n, s = con.execute(f"SELECT count(*), sum(id) FROM read_parquet('{t}/*.parquet')").fetchone()
assert (n, s) == (1000, 499500), (n, s)
print(f"duckdb {duckdb.__version__}: parquet round trip OK ({n} rows)")
PY
EOS
