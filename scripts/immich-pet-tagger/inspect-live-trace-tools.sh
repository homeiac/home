#!/usr/bin/env bash
# Inspect tracing tools and worker PIDs inside the inventory-listed still-fawn VM.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$HERE/../k3s/exec.sh" still-fawn 'command -v perf; command -v bpftrace; command -v strace; cat /proc/sys/kernel/perf_event_paranoid; pgrep -a -f worker.py'
