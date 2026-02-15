#!/bin/bash
# Setup macOS scoped resolver for *.homelab domains
# Routes all *.homelab queries to OPNsense DNS (192.168.4.1)
# Survives DHCP lease renewals - permanent fix for multi-network setups
#
# Usage: sudo ./setup-macos-resolver.sh

set -e

RESOLVER_DIR="/etc/resolver"
RESOLVER_FILE="$RESOLVER_DIR/homelab"
OPNSENSE_DNS="192.168.4.1"

# Check for root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (sudo)"
   exit 1
fi

# Create resolver directory if needed
mkdir -p "$RESOLVER_DIR"

# Create scoped resolver
echo "nameserver $OPNSENSE_DNS" > "$RESOLVER_FILE"

echo "Created $RESOLVER_FILE with nameserver $OPNSENSE_DNS"
echo ""
echo "Verifying..."
scutil --dns | grep -A3 "homelab" || echo "Resolver not yet active - may need a moment"
echo ""
echo "Test with: dig frigate.app.homelab +short"
