#!/usr/bin/env bash
# exporter-desired.sh
# Declarative ensuring: node-exporter + SMART + sensors configured.
# Safe on any Debian/Ubuntu host – re-runs cause 0 side-effects.

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

PKGS=(prometheus-node-exporter smartmontools lm-sensors moreutils curl wget)
MISSING=()
for p in "${PKGS[@]}"; do dpkg -s "$p" &>/dev/null || MISSING+=("$p"); done
[[ ${#MISSING[@]} -gt 0 ]] && { apt-get update -qq; apt-get install -y -qq "${MISSING[@]}"; }

systemctl enable --now prometheus-node-exporter

NODE_USER=$(grep -E '^User=' /lib/systemd/system/prometheus-node-exporter.service | cut -d= -f2)
COLLECT_DIR=/var/lib/node-exporter/textfile_collector
[[ -d $COLLECT_DIR ]] || mkdir -p "$COLLECT_DIR"
chown "$NODE_USER:$NODE_USER" "$COLLECT_DIR"

SMARTMON=/usr/local/bin/smartmon.sh
if [[ ! -x $SMARTMON ]]; then
  echo "*** Installing smartmon.sh"
  wget -qO "$SMARTMON" \
    https://raw.githubusercontent.com/prometheus-community/node-exporter-textfile-collector-scripts/master/smartmon.sh
  chmod 755 "$SMARTMON"
fi

CRON=/etc/cron.d/smartmon
DESIRED_CRON='*/5 * * * * root /usr/local/bin/smartmon.sh | /usr/bin/sponge /var/lib/node-exporter/textfile_collector/smartmon.prom'
grep -qF "$DESIRED_CRON" "$CRON" 2>/dev/null || echo "$DESIRED_CRON" >"$CRON"

# One-shot run if metrics file missing or empty
FILE="$COLLECT_DIR/smartmon.prom"
[[ ! -s $FILE ]] && sudo -u "$NODE_USER" "$SMARTMON" | sponge "$FILE"

# Optional: run sensors-detect silently the first time (skip if already done)
if ! sensors | grep -q 'coretemp'; then
  yes no | sensors-detect --auto >/dev/null 2>&1 || true
fi

echo "*** exporter-desired.sh complete (idempotent)"

