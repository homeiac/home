#!/bin/bash
# Start / watch the statistical verification of a mirror target (see host/verify-mirror-sample.sh)
#
# Usage: ./verify-mirror-sample-ctl.sh start <target> [host script options, e.g. --seed 7 --n 500]
#        ./verify-mirror-sample-ctl.sh status
# Runs on $CB_HOST as transient systemd unit "verify-mirror-sample" (survives SSH drops), idle I/O class.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
HOST_SCRIPT="$(dirname "${BASH_SOURCE[0]}")/host/verify-mirror-sample.sh"
case "${1:-}" in
  start) shift; T="${1:?target}"; shift
    cb_ssh "install -m 0755 /dev/stdin /usr/local/sbin/verify-mirror-sample.sh" < "$HOST_SCRIPT"
    cb_ssh "systemctl reset-failed verify-mirror-sample 2>/dev/null; systemd-run --unit=verify-mirror-sample --collect -p IOSchedulingClass=idle \
            -p StandardOutput=file:/var/lib/cloud-backup/reports/verify-sample-$T.log -p StandardError=inherit \
            /usr/local/sbin/verify-mirror-sample.sh $T $* && echo started";;
  status) cb_ssh "echo unit: \$(systemctl is-active verify-mirror-sample 2>/dev/null); tail -6 /var/lib/cloud-backup/reports/verify-sample-*.log 2>/dev/null | cut -c1-200";;
  *) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 1;;
esac
