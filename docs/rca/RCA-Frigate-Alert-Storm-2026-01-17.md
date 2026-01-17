# RCA: Frigate Health Checker Alert Storm

**Date**: 2026-01-17
**Duration**: N/A (proactive fix)
**Severity**: Low (annoyance, not outage)
**Author**: Infrastructure Team

## Summary

The Frigate health checker CronJob was sending duplicate email notifications during a single incident, and would attempt futile restarts when the target node (still-fawn) was down.

## Timeline

| Time | Event |
|------|-------|
| 2026-01-17 ~11:00 | User reported alert should fire only once per incident |
| 2026-01-17 ~11:05 | Added `alert_sent_for_incident` flag to ConfigMap |
| 2026-01-17 ~11:10 | User noted still-fawn was down - restart attempts pointless |
| 2026-01-17 ~11:15 | Added node Ready status check before restart |

## Root Cause

Two issues in the health checker logic:

### Issue 1: Alert Storm
The CronJob runs every 5 minutes. When Frigate was unhealthy:
1. Health check fails twice (consecutive failures threshold)
2. Restart triggered + email sent
3. Next health check (5 min later) - Frigate still starting up
4. Another restart triggered + **another email sent**
5. Repeat until healthy

**Missing**: State tracking for "alert already sent for this incident"

### Issue 2: Pointless Restarts When Node Down
Frigate is pinned to still-fawn (has Coral TPU). When still-fawn is down:
1. Health check fails (no pod or pod not responding)
2. Restart triggered
3. New pod stuck in Pending (node unavailable)
4. Repeat every 5 minutes until node returns

**Missing**: Check if target node is actually available

## Resolution

### Fix 1: Alert Deduplication
Added `alert_sent_for_incident` field to ConfigMap:
- Set to `"true"` when email sent
- Reset to `"false"` when Frigate becomes healthy
- Skip email if already `"true"`

```yaml
# configmap-health-state.yaml
data:
  alert_sent_for_incident: "false"
```

### Fix 2: Node Availability Check
Added pre-restart check:
```bash
FRIGATE_NODE=$(kubectl get pods -n frigate -l app=frigate -o jsonpath='{.items[0].spec.nodeName}')
NODE_READY=$(kubectl get node "$FRIGATE_NODE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
if [[ "$NODE_READY" != "True" ]]; then
  echo "NODE DOWN: skipping restart"
  exit 0
fi
```

## Commits

- `de5697c` - fix: send Frigate restart alert only once per incident
- `ba3813b` - fix: skip Frigate restart when target node is down

## Lessons Learned

1. **Alerting needs incident state** - Stateless alerting = alert storms. Every alert system needs "already notified for this incident" tracking.

2. **Check preconditions before actions** - A restart is pointless if the target node is down. Check that actions can actually succeed before attempting them.

3. **Think through failure modes** - The happy path worked fine. The failure path (node down, slow restart) revealed the gaps.

4. **Small automations need SRE thinking** - Even a "simple" health checker needs:
   - Deduplication
   - Rate limiting (already had this)
   - Precondition checks
   - State management

## Action Items

| Item | Owner | Status |
|------|-------|--------|
| Add alert_sent_for_incident flag | Infra | Done |
| Add node Ready check | Infra | Done |
| Consider adding "incident resolved" notification | Infra | Future |

## Tags

frigate, alerting, alert-storm, deduplication, health-check, cronjob, sre, still-fawn
