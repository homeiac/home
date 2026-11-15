#!/bin/sh
# dhcp-ipv4-watchdog.sh - runs INSIDE the PBS LXC (103) via systemd timer.
#
# Why: ifupdown runs dhclient once at boot. If the MAAS DHCP server
# (192.168.4.53, a VM on pve) is down at that moment, dhclient gives up after
# ~60s, releases, and NEVER retries. PBS then sits IPv6-only and every node
# fails with "Can't connect to 192.168.4.211:8007 (No route to host)".
#
# This checks for an IPv4 address on eth0 and, if missing, makes one fresh
# DHCP attempt (-1 = try once, exit non-zero on failure; timer retries).
IFACE=eth0
if ip -4 -o addr show dev "$IFACE" | grep -q 'inet '; then
    exit 0
fi
logger -t dhcp-ipv4-watchdog "no IPv4 on $IFACE - requesting DHCP lease"
# Clear any stale dhclient (the v4 one; leave the -6 client alone)
if [ -f /run/dhclient.$IFACE.pid ]; then
    kill "$(cat /run/dhclient.$IFACE.pid)" 2>/dev/null || true
fi
exec /sbin/dhclient -1 -v -pf /run/dhclient.$IFACE.pid \
    -lf /var/lib/dhcp/dhclient.$IFACE.leases "$IFACE"
