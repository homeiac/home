#!/bin/sh
# Snapshot Flint 3 network config to /tmp
set -eu
TS=$(date +%F_%H-%M-%S)
FILE="/tmp/flint-backup-$TS.tar.gz"
net_cfg="/tmp/network.$TS"

sysupgrade -b "$FILE"
cp /etc/config/network "$net_cfg"

echo "Backup files: $FILE $net_cfg"
