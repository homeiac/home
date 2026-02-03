#!/bin/bash
# Check Proxmox cluster status: quorum, node health, and VM/CT summary
# Usage: ./check-cluster-status.sh
set -e

SSH_KEY="/home/claude/.claude/ssh/proxmox_ed25519"
PVE_HOST="192.168.4.122"
SSH_OPTS="-o ConnectTimeout=10 -o StrictHostKeyChecking=no"

if [[ -f "$SSH_KEY" ]]; then
    SSH_CMD="ssh $SSH_OPTS -i $SSH_KEY root@$PVE_HOST"
else
    SSH_CMD="ssh $SSH_OPTS root@pve.maas"
fi

echo "=== Proxmox Cluster Status ==="
echo ""

echo "--- Cluster & Quorum ---"
$SSH_CMD "pvecm status" 2>/dev/null
echo ""

echo "--- Node Resources ---"
$SSH_CMD "pvesh get /cluster/resources --type node --output-format json" 2>/dev/null | \
    jq -r '
        ["NODE","STATUS","CPUs","CPU%","RAM_USED","RAM_TOTAL","RAM%","UPTIME_DAYS"],
        (.[] | [
            .node,
            .status,
            (.maxcpu // "-" | tostring),
            (if .cpu then (.cpu * 100 | round | tostring) + "%" else "-" end),
            (if .mem then ((.mem / 1073741824 * 10 | round / 10 | tostring) + "G") else "-" end),
            (if .maxmem then ((.maxmem / 1073741824 * 10 | round / 10 | tostring) + "G") else "-" end),
            (if .mem and .maxmem and .maxmem > 0 then ((.mem / .maxmem * 100 | round | tostring) + "%" ) else "-" end),
            (if .uptime then ((.uptime / 86400 * 10 | round / 10 | tostring)) else "-" end)
        ]) | @tsv
    ' | awk -F'\t' '{printf "%-18s %-10s %-6s %-6s %-10s %-10s %-6s %-s\n", $1, $2, $3, $4, $5, $6, $7, $8}'
echo ""

echo "--- VMs & Containers ---"
$SSH_CMD "pvesh get /cluster/resources --type vm --output-format json" 2>/dev/null | \
    jq -r '
        ["VMID","NAME","TYPE","NODE","STATUS","CPU%","RAM_USED","RAM_TOTAL"],
        (sort_by(.vmid) | .[] | [
            (.vmid | tostring),
            .name,
            .type,
            .node,
            .status,
            (if .cpu and .status == "running" then (.cpu * 100 | round | tostring) + "%" else "-" end),
            (if .mem and .status == "running" then ((.mem / 1073741824 * 10 | round / 10 | tostring) + "G") else "-" end),
            (if .maxmem then ((.maxmem / 1073741824 * 10 | round / 10 | tostring) + "G") else "-" end)
        ]) | @tsv
    ' | awk -F'\t' '{printf "%-6s %-24s %-6s %-16s %-10s %-6s %-10s %-s\n", $1, $2, $3, $4, $5, $6, $7, $8}'
