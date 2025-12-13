# Action Log: Home Assistant Frigate IP Migration

**Date**: YYYY-MM-DD
**Operator**: [Name/AI Agent]
**GitHub Issue**: #XXX
**Status**: [In Progress | Completed | Failed]

---

## Pre-Flight Checklist

| Check | Command | Expected | Actual | Status |
|-------|---------|----------|--------|--------|
| K8s Frigate pods | `kubectl get pods -n frigate` | Running | | |
| Service IPs | `kubectl get svc -n frigate` | IPs listed | | |
| Test target Frigate | `curl http://NEW_IP:5000/api/stats` | JSON | | |
| Current HA URL | QEMU guest exec | URL | | |

---

## Migration Execution

**Script**: `./scripts/frigate/update-ha-frigate-url.sh`
**Arguments**: `OLD_URL` `NEW_URL`
**Timestamp**: HH:MM

### Output:
```
[PASTE SCRIPT OUTPUT HERE]
```

**Backup Location**: [Path from script output]

---

## Verification

**Script**: `./scripts/frigate/check-ha-frigate-integration.sh`
**Timestamp**: HH:MM

### Output:
```
[PASTE OUTPUT HERE]
```

**Result**: [Success / Partial / Failed]

---

## Issues Encountered

### Issue 1: [Title]
**Severity**: [Low/Medium/High]
**Symptoms**: [Description]
**Resolution**: [Steps taken]

---

## Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | [Success / Partial / Failed] |
| **Start Time** | HH:MM |
| **End Time** | HH:MM |
| **Old URL** | http://X.X.X.X:5000 |
| **New URL** | http://X.X.X.X:5000 |
| **Backup Created** | [Yes/No] |

---

## Follow-Up Actions
- [ ] Verify cameras appear in HA
- [ ] Test Frigate events
- [ ] Update blueprint if learnings
- [ ] Close GitHub issue
- [ ] Monitor 24h stability
