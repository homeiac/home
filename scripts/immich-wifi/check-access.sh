#!/usr/bin/env bash
# Force Wi-Fi (not Ethernet/Tailscale) for network acceptance checks on macOS.
# Optional ALBUM_PATH checks a supplied share link without logging its secret.
set -euo pipefail
wifi=${WIFI_INTERFACE:-en0}
. "$(dirname "${BASH_SOURCE[0]}")/load-network.sh"
hostname=$IMMICH_HOSTNAME
relay=$RELAY_ADDRESS
echo 'Local split DNS'
wifi_ip=$(ipconfig getifaddr "$wifi")
dig -b "$wifi_ip" +time=3 +tries=1 +short @"$relay" "$hostname" A
dig -b "$wifi_ip" +time=3 +tries=1 +tcp +short @"$relay" "$hostname" A
dig -b "$wifi_ip" +time=3 +tries=1 +short @"$relay" example.com A
echo 'HTTPS through relay, using Wi-Fi and normal certificate validation'
curl --interface "$wifi" --connect-timeout 5 --max-time 20 --fail --silent --show-error \
  --resolve "$hostname:443:$relay" "https://$hostname/api/server/ping"
echo
echo 'A different SNI must be rejected'
if curl --interface "$wifi" --insecure --connect-timeout 5 --max-time 10 --silent \
  --resolve "unrelated.invalid:443:$relay" https://unrelated.invalid/ -o /dev/null; then
  echo 'FAIL: different SNI was accepted'; exit 1
fi
echo 'A mismatched HTTP Host must be rejected by Traefik'
code=$(curl --interface "$wifi" --http1.1 --connect-timeout 5 --max-time 15 --silent --show-error \
  --resolve "$hostname:443:$relay" -H 'Host: unrelated.invalid' "https://$hostname/" -o /dev/null -w '%{http_code}')
[[ $code == 421 ]] || { echo "FAIL: expected 421, received $code"; exit 1; }
echo 'Google Wi-Fi effective DNS'
answer=$(dig -b "$wifi_ip" +time=3 +tries=1 +short @"$GOOGLE_GATEWAY_ADDRESS" "$hostname" A)
if [[ $answer != "$relay" ]]; then
  echo "PENDING: Google Wi-Fi custom DNS must point to $relay."
  exit 3
fi
curl --interface "$wifi" --connect-timeout 5 --max-time 20 --silent --show-error --fail \
  --resolve "$hostname:443:$answer" "https://$hostname/api/server/ping"
echo
if [[ -n ${ALBUM_PATH:-} ]]; then
  [[ $ALBUM_PATH == /share/* || $ALBUM_PATH == /s/* ]] || exit 2
  curl --interface "$wifi" --connect-timeout 5 --max-time 20 --silent --show-error --fail \
    --resolve "$hostname:443:$answer" "https://$hostname$ALBUM_PATH" -o /dev/null
  echo 'Supplied shared album page returned successfully.'
fi
echo 'PASS: Google Wi-Fi DNS and the certificate-verified Immich path work.'
