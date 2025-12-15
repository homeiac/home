#!/bin/bash
# Check Proxmox host logs for a specific time window
# Usage: ./check-host-logs.sh [host] [start_time] [end_time]
# Usage: ./check-host-logs.sh still-fawn "06:00" "08:00"
# Usage: ./check-host-logs.sh still-fawn "2025-12-15 06:00" "2025-12-15 08:00"

set -e

HOST="${1:-still-fawn}"
START="${2:-06:00}"
END="${3:-08:00}"

# If only time provided, assume today
if [[ "$START" =~ ^[0-9]{2}:[0-9]{2}$ ]]; then
    TODAY=$(date '+%Y-%m-%d')
    START="$TODAY $START"
    END="$TODAY $END"
fi

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     PROXMOX HOST LOGS: $HOST                           ║"
echo "║     Window: $START to $END                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if host is reachable
if ! ssh -o ConnectTimeout=5 "root@${HOST}.maas" "echo ok" &>/dev/null; then
    echo "ERROR: Cannot connect to root@${HOST}.maas"
    exit 1
fi

echo "┌─ SYSTEM EVENTS (journalctl) ──────────────────────────────────┐"
ssh "root@${HOST}.maas" "journalctl --since '$START' --until '$END' --priority=warning --no-pager 2>/dev/null | head -30" 2>/dev/null || echo "│ No warning-level events"
echo "└────────────────────────────────────────────────────────────────┘"
echo ""

echo "┌─ VM EVENTS (qm/pve) ──────────────────────────────────────────┐"
ssh "root@${HOST}.maas" "journalctl --since '$START' --until '$END' --no-pager 2>/dev/null | grep -iE 'qemu|kvm|vm|pve' | head -20" 2>/dev/null || echo "│ No VM events"
echo "└────────────────────────────────────────────────────────────────┘"
echo ""

echo "┌─ USB EVENTS ──────────────────────────────────────────────────┐"
ssh "root@${HOST}.maas" "journalctl --since '$START' --until '$END' --no-pager 2>/dev/null | grep -iE 'usb|coral|apex' | head -10" 2>/dev/null || echo "│ No USB events"
echo "└────────────────────────────────────────────────────────────────┘"
echo ""

echo "┌─ RESOURCE CHANGES ────────────────────────────────────────────┐"
ssh "root@${HOST}.maas" "journalctl --since '$START' --until '$END' --no-pager 2>/dev/null | grep -iE 'memory|cpu|cgroup|oom|throttl' | head -10" 2>/dev/null || echo "│ No resource events"
echo "└────────────────────────────────────────────────────────────────┘"
echo ""

echo "┌─ NETWORK EVENTS ──────────────────────────────────────────────┐"
ssh "root@${HOST}.maas" "journalctl --since '$START' --until '$END' --no-pager 2>/dev/null | grep -iE 'network|bridge|vmbr|link|eth' | head -10" 2>/dev/null || echo "│ No network events"
echo "└────────────────────────────────────────────────────────────────┘"
echo ""

echo "┌─ CRON/SCHEDULED TASKS ────────────────────────────────────────┐"
ssh "root@${HOST}.maas" "journalctl --since '$START' --until '$END' --no-pager 2>/dev/null | grep -iE 'cron|systemd.*start|timer' | head -10" 2>/dev/null || echo "│ No scheduled tasks"
echo "└────────────────────────────────────────────────────────────────┘"
echo ""

echo "┌─ DMESG (kernel) ──────────────────────────────────────────────┐"
# dmesg doesn't have timestamps by default, so we check recent kernel messages
ssh "root@${HOST}.maas" "dmesg --time-format=iso 2>/dev/null | grep -E '$(echo $START | cut -d' ' -f1)T0[${START:11:1}-${END:11:1}]' | tail -20" 2>/dev/null || echo "│ No kernel messages in window (or dmesg doesn't support --time-format)"
echo "└────────────────────────────────────────────────────────────────┘"
