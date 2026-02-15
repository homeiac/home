#!/bin/bash
# setup-nut.sh - Install and configure NUT on pve for tiered UPS shutdown
# Run on: pve (192.168.4.122) - the only host with USB connection to UPS
#
# Architecture:
#   CyberPower CP1500 --USB--> pve --SSH--> other Proxmox hosts
#
# Tiered shutdown:
#   40%: pumped-piglet, still-fawn (heavy GPU/K3s hosts)
#   20%: MAAS VM 102
#   10%: chief-horse, then pve itself

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root"
    exit 1
fi

HOSTNAME=$(hostname)
if [[ "$HOSTNAME" != "pve" ]]; then
    log_error "This script should only run on 'pve', not '$HOSTNAME'"
    exit 1
fi

log_info "Installing NUT packages..."
apt-get update
apt-get install -y nut nut-client nut-server

log_info "Configuring /etc/nut/nut.conf..."
cat > /etc/nut/nut.conf << 'EOF'
# NUT configuration mode
# standalone = UPS connected directly, no network sharing
MODE=standalone
EOF

log_info "Configuring /etc/nut/ups.conf..."
cat > /etc/nut/ups.conf << 'EOF'
# UPS definitions
# CyberPower CP1500 connected via USB
[ups]
    driver = usbhid-ups
    port = auto
    desc = "CyberPower CP1500"
EOF

log_info "Configuring /etc/nut/upsd.conf..."
cat > /etc/nut/upsd.conf << 'EOF'
# UPS daemon configuration
LISTEN 127.0.0.1 3493
EOF

log_info "Configuring /etc/nut/upsd.users..."
cat > /etc/nut/upsd.users << 'EOF'
[admin]
    password = nutadmin
    actions = SET
    instcmds = ALL

[upsmon]
    password = upsmonpass
    upsmon master
EOF

chmod 640 /etc/nut/upsd.users
chown root:nut /etc/nut/upsd.users

log_info "Configuring /etc/nut/upsmon.conf..."
cat > /etc/nut/upsmon.conf << 'EOF'
# UPS monitor configuration
MONITOR ups@localhost 1 upsmon upsmonpass master

POLLFREQ 5
POLLFREQALERT 5

NOTIFYCMD /root/nut-notify.sh

NOTIFYFLAG ONLINE   SYSLOG+EXEC
NOTIFYFLAG ONBATT   SYSLOG+EXEC
NOTIFYFLAG LOWBATT  SYSLOG+EXEC
NOTIFYFLAG FSD      SYSLOG+EXEC
NOTIFYFLAG COMMOK   SYSLOG
NOTIFYFLAG COMMBAD  SYSLOG
NOTIFYFLAG SHUTDOWN SYSLOG
NOTIFYFLAG REPLBATT SYSLOG

SHUTDOWNCMD "/sbin/shutdown -h +0"
FINALDELAY 5
RUN_AS_USER root
EOF

chmod 640 /etc/nut/upsmon.conf
chown root:nut /etc/nut/upsmon.conf

log_info "Installing tiered shutdown notify script to /root/nut-notify.sh..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/nut-notify.sh" ]]; then
    cp "$SCRIPT_DIR/nut-notify.sh" /root/nut-notify.sh
    chmod +x /root/nut-notify.sh
    log_info "Copied nut-notify.sh from $SCRIPT_DIR"
else
    log_warn "nut-notify.sh not found in $SCRIPT_DIR - copy it manually"
fi

log_info "Setting up USB permissions for NUT..."
cat > /etc/udev/rules.d/90-nut-ups.rules << 'EOF'
# CyberPower UPS - allow nut user access
SUBSYSTEM=="usb", ATTR{idVendor}=="0764", MODE="0664", GROUP="nut"
EOF

udevadm control --reload-rules
udevadm trigger

log_info "Enabling and starting NUT services..."
systemctl enable nut-server
systemctl enable nut-monitor
systemctl restart nut-server
sleep 2
systemctl restart nut-monitor

log_info "Verifying UPS connection..."
sleep 3
if upsc ups@localhost &>/dev/null; then
    log_info "UPS detected successfully!"
    echo ""
    upsc ups@localhost 2>/dev/null | grep -E "^(battery\.|ups\.|device\.)" | head -20
else
    log_warn "UPS not detected. Check:"
    echo "  1. USB cable connected from UPS to this server"
    echo "  2. Run: lsusb | grep -i cyber"
    echo "  3. Check: systemctl status nut-server"
fi

echo ""
log_info "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Verify SSH to other hosts:"
echo "     ssh root@pumped-piglet.maas hostname"
echo "     ssh root@still-fawn.maas hostname"
echo "     ssh root@chief-horse.maas hostname"
echo ""
echo "  2. Test UPS status: upsc ups@localhost"
echo ""
echo "  3. Test notify script (dry run):"
echo "     UPSNAME=ups NOTIFYTYPE=ONBATT /root/nut-notify.sh"
