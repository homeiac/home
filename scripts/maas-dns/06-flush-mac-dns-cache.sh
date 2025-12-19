#!/bin/bash
# Flush macOS DNS cache
# Usage: ./06-flush-mac-dns-cache.sh
# NOTE: Requires sudo - will prompt for password

echo "=== Flushing macOS DNS Cache ==="
echo ""
echo "This requires sudo access..."
echo ""

sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder

echo ""
echo "✅ DNS cache flushed"
echo ""
echo "Test with: nslookup rancher.homelab"
