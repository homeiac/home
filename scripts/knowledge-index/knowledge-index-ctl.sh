#!/bin/bash
# Install / rebuild / query / backfill the knowledge index on the Proxmox host (issue #212)
#
# Usage (needs CB_HOST like the other backup scripts, e.g. CB_HOST=root@<host> from the laptop):
#   ./knowledge-index-ctl.sh install                 copy adapter + SQL + helpers to the host, create the dataset, enable the metrics timer (idempotent)
#   ./knowledge-index-ctl.sh metrics                 run the metrics export now and print what Prometheus will scrape (dashboard: Grafana > Homelab > Knowledge Index)
#   ./knowledge-index-ctl.sh rebuild                 recreate knowledge.duckdb (views only) from knowledge.sql
#   ./knowledge-index-ctl.sh query "<sql>"           run SQL on the host, TSV output (never run queries inside VM 105)
#   ./knowledge-index-ctl.sh status                  row counts, parquet files, units waiting in _index_pending.tsv
#   ./knowledge-index-ctl.sh backfill start|status   index the whole existing Photos library as unit backfill-<date>; status shows phase, files done/total, rate, ETA
#                                                    (also live in Grafana > Knowledge Index > Backfill progress)
#                                                    (systemd unit knowledge-index-backfill, nice + idle I/O); clears _index_pending.tsv
#   ./knowledge-index-ctl.sh enrich sample [N]       summarize N (default 10) queued photos/videos, print them, write nothing
#   ./knowledge-index-ctl.sh enrich status          inspect the GitOps-managed knowledge-index-enrich service
#                                                    needs KI_ENDPOINT (OpenAI-compatible vision server on the LAN, e.g. http://<gpu-vm>:11434);
#                                                    KI_API (ollama or openai), KI_MODEL, KI_ENRICHER id (default gemma4-e2b-p1)
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
  cb_ssh "mkdir -p $KI/adapters $KI/enrichers $KI/oracle"
  local worker_files=()
  # A metrics/index refresh must not overwrite the GitOps-managed worker.
  if ! cb_ssh "test -f $KI/caption-gitops/applied.json"; then
    worker_files=(enrichers/media_summary.py enrichers/pipeline_metrics.py enrichers/summary_cache.py)
  fi
  ( cd "$HERE" && tar -cf - adapters/gphotos.py "${worker_files[@]}" kidx.py progress.py export-metrics.py caption_completion.py knowledge.sql index-unit.sh ) | cb_ssh "tar -xf - -C $KI && chmod 0755 $KI/index-unit.sh $KI/kidx.py $KI/export-metrics.py $KI/adapters/gphotos.py $KI/enrichers/media_summary.py"
  cb_ssh "cat > $KI/oracle/gphotos-quota-list.py" < "$HERE/../backup/host/gphotos-quota-list.py"
  # Prometheus textfile exporter: systemd timer every 5 min (node-exporter on the host already reads /var/lib/prometheus/node-exporter)
  for u in knowledge-index-metrics.service knowledge-index-metrics.timer; do
    cb_ssh "install -m 0644 /dev/stdin /etc/systemd/system/$u" < "$HERE/host/$u"
  done
  # Ollama base URL for the exporter: looked up from the cluster here and kept ON THE HOST only (no addresses in Git)
  OLL="$(KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}" kubectl get svc ollama-lb -n ollama -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
  if [[ -n "$OLL" ]]; then cb_ssh "echo 'KI_OLLAMA_URL=http://$OLL' > /etc/default/knowledge-index"; else echo "note: no kubeconfig/ollama service: Ollama metrics skipped (set KI_OLLAMA_URL in /etc/default/knowledge-index on the host)"; fi
  cb_ssh "systemctl daemon-reload && systemctl enable --now knowledge-index-metrics.timer >/dev/null 2>&1"
}

case "${1:-}" in
  install)
    install_files
    cb_ssh "zfs list -H $IDX_DATASET >/dev/null 2>&1 || zfs create -o recordsize=1M -o compression=lz4 -o atime=off $IDX_DATASET; \
            $MOUNTS; echo \"installed in $KI; index dataset at \$IDX\"; $KI/venv/bin/python -c 'import duckdb; print(\"duckdb\", duckdb.__version__)'"
    ;;
  metrics) install_files; cb_ssh "systemctl start knowledge-index-metrics.service; grep -E '^(knowledge_index_exporter_success|knowledge_index_files|gphotos_quota_bytes|media_summaries|smart_pending)' /var/lib/prometheus/node-exporter/knowledge_index.prom";;
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
                $MOUNTS; UNIT=backfill-\$(date +%Y%m%d); EXP=\$(awk -F'\\t' '{s+=\$4} END {print s+0}' \$PH/_ingested.tsv); \
                systemd-run --unit=knowledge-index-backfill --collect -p Nice=10 -p IOSchedulingClass=idle bash -c \
                  \"set -e; $KI/venv/bin/python $KI/adapters/gphotos.py emit \$UNIT \$PH/library \$IDX --versions \$PH/.versions \
                    --prom /var/lib/prometheus/node-exporter/knowledge_index_backfill.prom --expected \$EXP \
                    && $KI/venv/bin/python $KI/kidx.py rebuild \$IDX && rm -f \$PH/_index_pending.tsv\" && echo \"started \$UNIT\""
        ;;
      status) cb_ssh "systemctl is-active knowledge-index-backfill 2>/dev/null || true; journalctl -u knowledge-index-backfill --no-pager -n 4 2>/dev/null || true; \
                      grep -hE '^knowledge_index_backfill_(phase\{.*\} 1|progress_ratio|files_(listed|total|done)|rate_files|eta_seconds|parse_errors|running)' /var/lib/prometheus/node-exporter/knowledge_index_backfill.prom 2>/dev/null || echo '(no progress file: run started by an older version)'";;
      *) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 1;;
    esac
    ;;
  enrich)
    if [[ "${2:-}" == start || "${2:-}" == stop ]]; then
      echo 'Caption service lifecycle is GitOps-managed. Edit caption-gitops/config.json enabled, regenerate and push.' >&2
      exit 2
    fi
    KI_MODEL="${KI_MODEL:-gemma4:e2b}"; KI_ENRICHER="${KI_ENRICHER:-gemma4-e2b-p1}"; KI_MIN_FREE_MIB="${KI_MIN_FREE_MIB:-3000}"
    KI_API="${KI_API:-ollama}"
    case "$KI_API" in
      ollama) KI_EXTRA='{"think":false}'; KI_BATCH=200;;
      openai) KI_EXTRA='{"chat_template_kwargs":{"enable_thinking":false},"max_tokens":384}'; KI_BATCH=16;;
      *) echo 'KI_API must be ollama or openai' >&2; exit 1;;
    esac
    if [[ "$KI_API" == ollama && "$KI_MODEL" == bonsai-27b ]]; then
      KI_EXTRA='{"think":false,"options":{"num_ctx":8192,"num_predict":384,"temperature":0.2}}'
      KI_BATCH=16
    fi
    run_cmd() {   # runs on the host beside the read-only photo library
      echo "$KI/venv/bin/python $KI/enrichers/media_summary.py run --index \"\$IDX\" --library \"\$PH/library\" --endpoint '${KI_ENDPOINT:?set KI_ENDPOINT}' \
            --model '$KI_MODEL' --api '$KI_API' --extra-json '$KI_EXTRA' --batch-size $KI_BATCH --enricher '$KI_ENRICHER' --min-free-mib $KI_MIN_FREE_MIB \
            --prom /var/lib/prometheus/node-exporter/knowledge_index_pipeline.prom $*"; }
    case "${2:-}" in
      sample) install_files
              cb_ssh "command -v ffmpeg >/dev/null || { echo 'ffmpeg missing on the host: apt-get install ffmpeg (ask first)'; exit 1; }; $MOUNTS; $(run_cmd --dry-run --limit "${3:-10}")";;
      status) cb_ssh "systemctl is-active knowledge-index-enrich 2>/dev/null || true; journalctl -u knowledge-index-enrich --no-pager -n 6 2>/dev/null || true; \
                      $MOUNTS; $KI/venv/bin/python $KI/kidx.py query \"\$IDX\" \"SELECT enricher, status, count(*) n FROM media_summaries GROUP BY ALL ORDER BY 1,2\"";;
      *) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 1;;
    esac
    ;;
  quota-diff)
    # the oracle wants <root>/gphotos/library: build that with a symlink in a temp dir
    cb_ssh "$MOUNTS; T=\$(mktemp -d); trap 'rm -rf \$T' EXIT; mkdir \$T/gphotos; ln -s \$PH/library \$T/gphotos/library; \
            python3 $KI/oracle/gphotos-quota-list.py \$T 2>/dev/null | sed 's|^gphotos/library/||' | sort > \$T/want; \
            time $KI/venv/bin/python $KI/kidx.py query \"\$IDX\" 'SELECT path FROM gphotos_quota ORDER BY path' | tail -n +2 | sort > \$T/got; \
            echo \"oracle \$(wc -l < \$T/want) paths, index \$(wc -l < \$T/got) paths\"; diff \$T/want \$T/got | head -20 && echo 'diff: empty (equal)'"
    ;;
  *) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 1;;
esac
