#!/bin/bash
# Install / rebuild / query / backfill the knowledge index on the Proxmox host (issue #212)
#
# Usage (needs CB_HOST like the other backup scripts, e.g. CB_HOST=root@<host> from the laptop):
#   ./knowledge-index-ctl.sh install                 copy adapter + SQL + helpers to the host, create the dataset (idempotent)
#   ./knowledge-index-ctl.sh rebuild                 recreate knowledge.duckdb (views only) from knowledge.sql
#   ./knowledge-index-ctl.sh query "<sql>"           run SQL on the host, TSV output (never run queries inside VM 105)
#   ./knowledge-index-ctl.sh status                  row counts, parquet files, units waiting in _index_pending.tsv
#   ./knowledge-index-ctl.sh backfill start|status   index the whole existing Photos library as unit backfill-<date>
#                                                    (systemd unit knowledge-index-backfill, nice + idle I/O); clears _index_pending.tsv
#   ./knowledge-index-ctl.sh quota-diff              diff `SELECT path FROM gphotos_quota` against gphotos-quota-list.py on the real library
# Prerequisite: scripts/knowledge-index/install-duckdb.sh (pinned DuckDB venv).
# Layout on the host: /opt/knowledge-index/{venv,adapters/gphotos.py,kidx.py,knowledge.sql,index-unit.sh}; data in the dataset
#   local-3TB-backup/knowledge-index (recordsize 1M, lz4) mounted at /local-3TB-backup/knowledge-index.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/../backup/cloud-backup-common.sh"
IDX_DATASET="${IDX_DATASET:-local-3TB-backup/knowledge-index}"
PHOTOS_DATASET="${PHOTOS_DATASET:-local-3TB-backup/gphotos}"
KI=/opt/knowledge-index
# resolve mount points on the host
MOUNTS="IDX=\$(zfs get -H -o value mountpoint $IDX_DATASET); PH=\$(zfs get -H -o value mountpoint $PHOTOS_DATASET)"

install_files() {
  cb_ssh "mkdir -p $KI/adapters $KI/oracle"
  ( cd "$HERE" && tar -cf - adapters/gphotos.py kidx.py knowledge.sql index-unit.sh ) | cb_ssh "tar -xf - -C $KI && chmod 0755 $KI/index-unit.sh $KI/kidx.py $KI/adapters/gphotos.py"
  cb_ssh "cat > $KI/oracle/gphotos-quota-list.py" < "$HERE/../backup/host/gphotos-quota-list.py"
}

case "${1:-}" in
  install)
    install_files
    cb_ssh "zfs list -H $IDX_DATASET >/dev/null 2>&1 || zfs create -o recordsize=1M -o compression=lz4 -o atime=off $IDX_DATASET; \
            $MOUNTS; echo \"installed in $KI; index dataset at \$IDX\"; $KI/venv/bin/python -c 'import duckdb; print(\"duckdb\", duckdb.__version__)'"
    ;;
  rebuild) install_files; cb_ssh "$MOUNTS; $KI/venv/bin/python $KI/kidx.py rebuild \"\$IDX\"";;
  query)   [[ -n "${2:-}" ]] || { echo 'usage: query "<sql>"'; exit 1; }
           cb_ssh "$MOUNTS; $KI/venv/bin/python $KI/kidx.py query \"\$IDX\" $(printf '%q' "$2")";;
  status)  cb_ssh "$MOUNTS; $KI/venv/bin/python $KI/kidx.py status \"\$IDX\"; echo; \
                   echo \"index_pending units: \$(cat \"\$PH/_index_pending.tsv\" 2>/dev/null | wc -l)\"; cat \"\$PH/_index_pending.tsv\" 2>/dev/null || true; \
                   echo \"backfill unit: \$(systemctl is-active knowledge-index-backfill 2>/dev/null || true)\"; zfs list -o name,used,avail $IDX_DATASET";;
  backfill)
    case "${2:-}" in
      start)
        install_files
        cb_ssh "systemctl is-active -q knowledge-index-backfill && { echo 'already running'; exit 0; }; systemctl reset-failed knowledge-index-backfill 2>/dev/null; \
                $MOUNTS; UNIT=backfill-\$(date +%Y%m%d); \
                systemd-run --unit=knowledge-index-backfill --collect -p Nice=10 -p IOSchedulingClass=idle bash -c \
                  \"set -e; $KI/venv/bin/python $KI/adapters/gphotos.py emit \$UNIT \$PH/library \$IDX --versions \$PH/.versions \
                    && $KI/venv/bin/python $KI/kidx.py rebuild \$IDX && rm -f \$PH/_index_pending.tsv\" && echo \"started \$UNIT\""
        ;;
      status) cb_ssh "systemctl is-active knowledge-index-backfill 2>/dev/null || true; journalctl -u knowledge-index-backfill --no-pager -n 8 2>/dev/null || true";;
      *) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 1;;
    esac
    ;;
  quota-diff)
    # the oracle wants <root>/gphotos/library: build that with a symlink in a temp dir
    cb_ssh "$MOUNTS; T=\$(mktemp -d); trap 'rm -rf \$T' EXIT; mkdir \$T/gphotos; ln -s \$PH/library \$T/gphotos/library; \
            python3 $KI/oracle/gphotos-quota-list.py \$T 2>/dev/null | sed 's|^gphotos/library/||' | sort > \$T/want; \
            time $KI/venv/bin/python $KI/kidx.py query \"\$IDX\" 'SELECT path FROM gphotos_quota ORDER BY path' | tail -n +2 | sort > \$T/got; \
            echo \"oracle \$(wc -l < \$T/want) paths, index \$(wc -l < \$T/got) paths\"; diff \$T/want \$T/got | head -20 && echo 'diff: empty (equal)'"
    ;;
  *) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 1;;
esac
