#!/usr/bin/env bash
# Called only by the Flux-managed Job, over the existing SSH deployment key.
# All new files are dedicated to this feature. Save the initial state before
# changing it, validate before activation, and restore on a failed deployment.
set -euo pipefail
stage=${1:?bundle directory}
action=${2:-apply}
# This file is decrypted by Flux, not stored as plaintext in Git.
set -a
. "$stage/network.env"
set +a
state=/var/lib/immich-wifi
install=/opt/immich-wifi
units=(immich-wifi-firewall.service immich-wifi-proxy.service immich-wifi-dns.service)
[[ $(hostname -s) == "$EXPECTED_HOST" ]] || { echo 'Wrong target host'; exit 1; }
. /etc/os-release
[[ $ID == debian && $VERSION_ID == 12 ]] || { echo 'Expected the inspected Debian 12 host'; exit 1; }
umask 077
mkdir -p "$state"
exec 9>"$state/lock"
flock -n 9

rollback() {
  systemctl disable --now immich-wifi-proxy.service immich-wifi-dns.service || true
  systemctl disable --now immich-wifi-firewall.service || true
  bash "$stage/firewall.sh" remove
  for unit in "${units[@]}"; do rm -f "/etc/systemd/system/$unit"; done
  systemctl daemon-reload
  rm -f "$state/applied.sha256"
  echo 'Disabled the Wi-Fi listeners; the existing Traefik and HA paths are unchanged.'
}
if [[ $action == rollback ]]; then rollback; exit; fi
[[ $action == apply ]] || exit 2
ip -4 addr show dev "$WAN_INTERFACE" | grep -F "$RELAY_ADDRESS/24" >/dev/null
ip -4 addr show dev "$LAB_INTERFACE" | grep -F "$PVE_ADDRESS/24" >/dev/null
# Fail closed if Google Wi-Fi's DHCP WAN address has changed since discovery.
curl --fail --connect-timeout 3 --max-time 10 -sS "http://$GOOGLE_GATEWAY_ADDRESS/api/v1/status" |
  python3 -c 'import json,os,sys; assert json.load(sys.stdin)["wan"]["localIpAddress"] == os.environ["GOOGLE_WAN_ADDRESS"], "Google Wi-Fi WAN changed: update the Git ACL before deployment"'

if [[ ! -f "$state/initial-backup/complete" ]]; then
  for unit in "${units[@]}"; do
    [[ ! -e /etc/systemd/system/$unit ]] || { echo "Refusing to overwrite unmanaged $unit"; exit 1; }
  done
  [[ ! -e $install ]] || { echo 'Refusing to overwrite unmanaged install directory'; exit 1; }
  # Ensure both listeners are free, without dumping unrelated service details.
  if ss -H -lntu | awk '$5 ~ /(:53|:443)$/ {found=1} END {exit !found}'; then
    echo 'Port 53 or 443 already has a listener; review before deployment'; exit 1
  fi
  mkdir -p "$state/initial-backup"
  iptables-save > "$state/initial-backup/iptables.rules"
  ip -4 route > "$state/initial-backup/routes.txt"
  dpkg-query -W > "$state/initial-backup/packages.txt"
  touch "$state/initial-backup/complete"
fi

if ! command -v haproxy >/dev/null || ! command -v dnsmasq >/dev/null; then
  # dnsmasq-base provides only the binary; our dedicated unit owns its listener.
  # Prevent the distribution HAProxy service from starting during installation.
  if ! dpkg-query -W -f='${db:Status-Status}' haproxy 2>/dev/null | grep -qx installed; then
    systemctl mask haproxy.service
  fi
  export DEBIAN_FRONTEND=noninteractive
  # Refresh only the distribution repositories needed for these two packages.
  cat > "$stage/debian.list" <<'APT'
deb http://deb.debian.org/debian bookworm main
deb http://security.debian.org/debian-security bookworm-security main
APT
  apt_options=(-o "Dir::Etc::sourcelist=$stage/debian.list" -o Dir::Etc::sourceparts=-)
  apt-get "${apt_options[@]}" update
  apt-get "${apt_options[@]}" install -y --no-install-recommends haproxy dnsmasq-base
fi
# Render only the two public templates using the decrypted network settings.
python3 - "$stage" <<'RENDER'
import os,sys
from pathlib import Path
from string import Template
stage=Path(sys.argv[1])
for name in ('haproxy.cfg','dnsmasq.conf'):
    p=stage/name
    p.write_text(Template(p.read_text()).substitute(os.environ))
RENDER
haproxy -c -f "$stage/haproxy.cfg"
dnsmasq --test --conf-file="$stage/dnsmasq.conf"
for file in "$stage"/*.sh; do bash -n "$file"; done
systemd-analyze verify "$stage"/*.service

desired=$(cd "$stage"; sha256sum *.sh *.cfg *.conf *.service network.env | sha256sum | cut -d' ' -f1)
matches=true
for file in host.sh firewall.sh haproxy.cfg dnsmasq.conf network.env; do
  cmp -s "$stage/$file" "$install/$file" || matches=false
done
for unit in "${units[@]}"; do
  cmp -s "$stage/$unit" "/etc/systemd/system/$unit" || matches=false
  systemctl is-active --quiet "$unit" || matches=false
done
if [[ -f $state/applied.sha256 && $(cat "$state/applied.sha256") == "$desired" && $matches == true ]]; then
  bash "$install/firewall.sh" apply
  echo 'Desired configuration is already active.'
  exit
fi

backup="$state/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup"
[[ ! -d $install ]] || cp -a "$install" "$backup/install"
for unit in "${units[@]}"; do
  [[ ! -f /etc/systemd/system/$unit ]] || cp -a "/etc/systemd/system/$unit" "$backup/"
done
restore_failed_deploy() {
  trap - ERR
  rollback
  if [[ -d $backup/install ]]; then
    cp -a "$backup/install/." "$install/"
    for unit in "${units[@]}"; do cp -a "$backup/$unit" "/etc/systemd/system/$unit"; done
    systemctl daemon-reload
    systemctl enable --now "${units[@]}"
  fi
  exit 1
}
trap restore_failed_deploy ERR
mkdir -p "$install"
chmod 755 "$install"
for file in host.sh firewall.sh haproxy.cfg dnsmasq.conf network.env; do
  mode=644
  [[ $file == network.env ]] && mode=600
  install -m "$mode" "$stage/$file" "$install/$file"
done
for unit in "${units[@]}"; do install -m 644 "$stage/$unit" "/etc/systemd/system/$unit"; done
systemctl daemon-reload
# Stop listeners before changing rules; bring the firewall up before listeners.
systemctl stop immich-wifi-proxy.service immich-wifi-dns.service
systemctl enable "${units[@]}"
systemctl restart immich-wifi-firewall.service
systemctl start immich-wifi-proxy.service immich-wifi-dns.service
systemctl is-active "${units[@]}"
curl --fail --connect-timeout 3 --max-time 15 -sS \
  --resolve "$IMMICH_HOSTNAME:443:$RELAY_ADDRESS" \
  "https://$IMMICH_HOSTNAME/api/server/ping"
echo "$desired" > "$state/applied.sha256"
dpkg-query -W haproxy dnsmasq-base > "$state/installed-versions.txt"
trap - ERR
echo 'DEPLOYED: local DNS and TLS relay active; configure Google Wi-Fi DNS after client verification.'
