# Action Log Template: Frigate Stale Database Cleanup

## Execution Date: [DATE]

## Pre-flight Checks
- [ ] Frigate running: `kubectl get pods -n frigate`
- [ ] Current I/O: `ssh root@pumped-piglet.maas "zpool iostat local-20TB-zfs 2 3"`
- [ ] Current load: `ssh root@pumped-piglet.maas "uptime"`
- [ ] Backup database: `kubectl exec -n frigate deployment/frigate -- cp /config/frigate.db /config/frigate.db.backup`

---

## Step 1: Investigate Database State
- **Command**: [command used]
- **Status**: [PENDING/SUCCESS/FAILED]
- **Stale entries found**: [count/date range]
- **Output**:
```
[paste output here]
```

---

## Step 2: Clean Stale Entries
- **Method used**: [API/Direct DB/Fresh DB]
- **Command**: [command used]
- **Status**: [PENDING/SUCCESS/FAILED]
- **Entries removed**: [count]
- **Output**:
```
[paste output here]
```

---

## Step 3: Restart Frigate (if needed)
- **Command**: `kubectl rollout restart deployment/frigate -n frigate`
- **Status**: [PENDING/SUCCESS/FAILED]
- **Output**:
```
[paste output here]
```

---

## Step 4: Verify Fix

### I/O Check
- **Before cleanup**: [X] MB/s read
- **After cleanup**: [X] MB/s read
- **Output**:
```
[paste output here]
```

### Load Average Check
- **Before cleanup**: [X]
- **After cleanup**: [X]
- **Output**:
```
[paste output here]
```

### Log Check
- **Errors present**: [YES/NO]
- **Output**:
```
[paste output here]
```

---

## Results Summary

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Disk Read I/O | [X] MB/s | [X] MB/s | [X]% |
| Host Load Avg | [X] | [X] | [X]% |
| Cleanup Errors | [YES/NO] | [YES/NO] | - |

---

## Final Status
- **Overall**: [SUCCESS/PARTIAL/FAILED]
- **Notes**:

---

## Rollback (if needed)
```bash
kubectl exec -n frigate deployment/frigate -- cp /config/frigate.db.backup /config/frigate.db
kubectl rollout restart deployment/frigate -n frigate
```
- **Executed**: [YES/NO]
- **Reason**:

---

## References
- Plan: `scripts/frigate/PLAN-cleanup-stale-db-entries.md`
- [Frigate API Docs](https://docs.frigate.video/integrations/api/)
