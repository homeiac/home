#!/bin/sh
# Flux supplies the public code and decrypts the network-specific settings.
set -eu
umask 077
. /settings/network.env
cp /credentials/id_rsa /work/id_rsa
chmod 600 /work/id_rsa
cd /work
cp /bundle/host.sh /bundle/firewall.sh /bundle/haproxy.cfg /bundle/dnsmasq.conf /bundle/*.service .
cp /settings/network.env .
tar -cf - host.sh firewall.sh haproxy.cfg dnsmasq.conf network.env \
  immich-wifi-firewall.service immich-wifi-proxy.service immich-wifi-dns.service |
  ssh -T -i /work/id_rsa -o BatchMode=yes -o ConnectTimeout=10 \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/settings/known_hosts \
    -o Hostname="$PVE_ADDRESS" -o HostKeyAlias="$PVE_HOSTNAME" \
    "root@$PVE_HOSTNAME" 'set -eu; umask 077; stage=$(mktemp -d /var/tmp/immich-wifi.XXXXXX); trap '\''rm -rf "$stage"'\'' EXIT; tar -xf - -C "$stage"; bash "$stage/host.sh" "$stage" apply'
