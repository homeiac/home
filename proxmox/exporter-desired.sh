#!/usr/bin/env bash
# exporter-desired.sh  —  idempotent bootstrap WITH VERBOSE LOGGING
# Safe to run repeatedly; prints clear progress and skips when state is OK.

set -euo pipefail
log() { printf '\e[36m[%s] %s\e[0m\n' "$(date +%H:%M:%S)" "$*"; }

# ------------------------------------------------------------ install packages
log "Checking required packages…"
MISSING=()
for p in prometheus-node-exporter smartmontools lm-sensors moreutils curl wget; do
  dpkg -s "$p" &>/dev/null || MISSING+=("$p")
done
if ((${#MISSING[@]})); then
  log "Installing: ${MISSING[*]}"
  DEBIAN_FRONTEND=noninteractive apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${MISSING[@]}"
else
  log "All packages already present."
fi

# ------------------------------------------------------------ node exporter
log "Enabling & starting prometheus-node-exporter.service"
systemctl enable --now prometheus-node-exporter

NODE_USER=$(grep -E '^User=' /lib/systemd/system/prometheus-node-exporter.service | cut -d= -f2)
TEXTFILE_DIR=/var/lib/node-exporter/textfile_collector
mkdir -p "$TEXTFILE_DIR"
chown "$NODE_USER:$NODE_USER" "$TEXTFILE_DIR"

# ------------------------------------------------------------ smartmon script
SMARTMON=/usr/local/bin/smartmon.sh
if [[ ! -x $SMARTMON ]]; then
  log "Installing smartmon.sh"
  wget -qO "$SMARTMON" \
    https://raw.githubusercontent.com/prometheus-community/node-exporter-textfile-collector-scripts/master/smartmon.sh
  chmod 755 "$SMARTMON"
else
  log "smartmon.sh already present."
fi

CRON=/etc/cron.d/smartmon
CRONLINE='*/5 * * * * root /usr/local/bin/smartmon.sh | /usr/bin/sponge /var/lib/node-exporter/textfile_collector/smartmon.prom'
grep -qF "$CRONLINE" "$CRON" 2>/dev/null || { log "Adding cron job"; echo "$CRONLINE" >"$CRON"; }

# one-shot run if missing/empty
SMARTFILE="$TEXTFILE_DIR/smartmon.prom"
if [[ ! -s $SMARTFILE ]]; then
  log "Generating initial SMART metrics"
  sudo -u "$NODE_USER" "$SMARTMON" | sponge "$SMARTFILE"
fi

log "Done.  Exporter metrics available on :9100"

