#!/bin/bash
# Index one ingested unit (Takeout archive) into the knowledge index; never lose data on failure (issue #212)
#
# Usage (on the Proxmox host; called by gphotos-ingest-host.sh after the rename step):
#   index-unit.sh <unit> <moved-file> <photos-dataset-mount> <index-dataset-mount>
#     moved-file: library-relative paths the archive delivered, one per line
# Success: writes the unit's Parquet, rebuilds the views, removes the unit from <photos>/_index_pending.tsv.
# Failure: leaves library and ledger alone, appends "<unit><TAB><time>" to <photos>/_index_pending.tsv, exits 3.
#   Fix pending units with: knowledge-index-ctl.sh backfill start   (re-indexes the whole library, clears the list)
# Env: KI_DIR (default /opt/knowledge-index), KI_PYTHON (default $KI_DIR/venv/bin/python)
set -uo pipefail
unit="${1:?unit}"; moved="${2:?moved-file}"; lib="${3:?photos dataset mount}"; idx="${4:?index dataset mount}"
KI_DIR="${KI_DIR:-/opt/knowledge-index}"; PY="${KI_PYTHON:-$KI_DIR/venv/bin/python}"
pending="$lib/_index_pending.tsv"
if "$PY" "$KI_DIR/adapters/gphotos.py" emit "$unit" "$lib/library" "$idx" --paths-from "$moved" \
   && "$PY" "$KI_DIR/kidx.py" rebuild "$idx"; then
  if [[ -f "$pending" ]]; then
    awk -F'\t' -v u="$unit" '$1 != u' "$pending" > "$pending.tmp" && mv "$pending.tmp" "$pending"
  fi
  exit 0
fi
printf '%s\t%s\n' "$unit" "$(date -Iseconds)" >> "$pending"
echo "index step failed for $unit: listed in $pending" >&2
exit 3
