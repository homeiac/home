#!/usr/bin/env bash
# Run the shared-workload, Cricket publisher and life-stage tests on this checkout.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"
: "${ASAM_OPENLABEL_1_0_SCHEMA:?set this to the pinned ASAM OpenLABEL 1.0.0 schema file}"
export CRICKET_OPENLABEL_SCHEMA="$ASAM_OPENLABEL_1_0_SCHEMA"
export CRICKET_OPENLABEL_SHARED_MODULE="$root/scripts/knowledge-index/memory-acceptance"
export CRICKET_TEST_LOCAL_POSTGRES=1
exec "${PYTHON:-python3}" -m pytest -q scripts/perf/tests scripts/knowledge-index/test_media_observations.py \
    scripts/knowledge-index/cricket scripts/knowledge-index/memory-acceptance
