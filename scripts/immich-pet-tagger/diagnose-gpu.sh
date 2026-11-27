#!/usr/bin/env bash
# Read-only three-second Apple GPU/process sample. Never prompt for a password.
set -euo pipefail
umask 077
output="${1:?private output path required}"
sudo -n /usr/bin/powermetrics --samplers tasks,gpu_power --show-process-gpu --show-process-wait-times --show-process-io --show-process-netstats -i 1000 -n 3 > "$output"
