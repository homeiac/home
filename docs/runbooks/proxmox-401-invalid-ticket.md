# Runbook: Proxmox 401 "Invalid PVE Ticket" Error

## Symptoms

- Proxmox web UI shows "permission denied - invalid PVE ticket (401)"
- Error appears for specific node(s) in cluster view
- Direct access to affected node's UI (https://IP:8006) may still work
- Other nodes in cluster work normally

## Quick Diagnosis

```bash
# 1. Check time on all nodes (MOST COMMON CAUSE)
for node in chief-horse still-fawn pumped-piglet fun-bedbug; do
  echo "=== $node ==="
  ssh root@$node.maas "date; chronyc tracking | grep -E 'Stratum|System time'" 2>/dev/null || \
  ssh root@$(grep $node ~/code/home/proxmox/inventory.txt | awk '{print $1}') "date; chronyc tracking | grep -E 'Stratum|System time'" 2>/dev/null
done

# Or use the script:
scripts/proxmox/check-ntp-sync.sh
```

**Red flags:**
- Stratum: 0 (not syncing)
- System time offset > 5 seconds
- Time difference between nodes > 30 seconds

## Resolution Steps

### If Time Drift (Most Common)

```bash
NODE_IP="192.168.4.19"  # Set to affected node IP

# 1. Check current NTP sources
ssh root@$NODE_IP "chronyc sources"

# 2. If no valid sources (all showing ^?), add public pool
ssh root@$NODE_IP "grep -q 'pool.ntp.org' /etc/chrony/chrony.conf || echo 'pool pool.ntp.org iburst' >> /etc/chrony/chrony.conf"

# 3. Restart chrony and force sync
ssh root@$NODE_IP "systemctl restart chronyd && sleep 3 && chronyc makestep"

# 4. Verify sync
ssh root@$NODE_IP "chronyc tracking"

# 5. Restart PVE services
ssh root@$NODE_IP "systemctl restart pvedaemon pveproxy"

# 6. Test - refresh cluster UI
```

### If SSL Certificate Issue

Check logs for SSL errors:
```bash
ssh root@$NODE_IP "journalctl -u pveproxy -n 50 | grep -i ssl"
```

If you see "failed to load local private key":
```bash
# Regenerate node certificates
ssh root@$NODE_IP "pvecm updatecerts --force"
ssh root@$NODE_IP "systemctl restart pvedaemon pveproxy"
```

### If Cluster Quorum Issue

```bash
# Check cluster status
ssh root@$NODE_IP "pvecm status"

# Should show "Quorate: Yes"
# If not, check corosync
ssh root@$NODE_IP "systemctl status corosync"
```

### Browser-Side Issues

If server-side looks fine:
1. Hard refresh: Cmd+Shift+R (Mac) / Ctrl+Shift+R
2. Clear cookies for Proxmox domain
3. Try incognito window
4. Try different browser

## Node IP Reference

| Node | IP |
|------|-----|
| chief-horse | 192.168.4.19 |
| still-fawn | 192.168.4.17 |
| pumped-piglet | (check inventory.txt) |
| fun-bedbug | 192.168.4.172 |

## Prevention

1. Ensure all nodes have `pool pool.ntp.org iburst` in `/etc/chrony/chrony.conf`
2. Monitor NTP sync status
3. Alert on time drift > 30 seconds between nodes

## Related

- RCA: `docs/rca/2025-12-27-chief-horse-pve-401-time-drift.md`
- Script: `scripts/proxmox/check-ntp-sync.sh`

## Tags

proxmox, pve, 401, authentication, ticket, ntp, chrony, time, cluster, runbook
