# Action Log: Home Assistant DNS Fix for .homelab Domains

**Date**: YYYY-MM-DD
**Operator**: [Name/AI Agent]
**GitHub Issue**: #XXX
**Status**: [In Progress | Completed | Failed]

---

## Pre-Flight Checklist

| Check | Command | Expected | Actual | Status |
|-------|---------|----------|--------|--------|
| Mac DNS resolves frigate.app.homelab | `nslookup frigate.app.homelab` | 192.168.4.80 | | |
| Traefik responds | `curl -s http://192.168.4.80 -H "Host: frigate.app.homelab"` | HTTP 200 | | |
| OPNsense has wildcard | `dig frigate.app.homelab @192.168.4.1 +short` | 192.168.4.80 | | |
| MAAS forwards to OPNsense | `dig frigate.app.homelab @192.168.4.53 +short` | 192.168.4.80 | | |

---

## Diagnosis Results

**Script**: `00-diagnose-dns-chain.sh`
**Timestamp**: HH:MM
**Output**:
```
[PASTE OUTPUT HERE]
```

**Conclusion**: [DNS chain works / MAAS forwarding broken / HA DNS misconfigured]

---

## HA Frigate Access Test

**Script**: `01-test-ha-can-reach-frigate.sh`
**Timestamp**: HH:MM
**Output**:
```
[PASTE OUTPUT HERE]
```

**Result**: [HA can/cannot reach Frigate via hostname]

---

## Fix Applied

**Option Used**: [B: OPNsense / C: nmcli / None needed]

### If Option B (OPNsense):
- [ ] Logged into OPNsense web UI
- [ ] Verified/added `*.app.homelab` -> 192.168.4.80
- [ ] Rebooted OPNsense (if needed)

### If Option C (nmcli):
- [ ] Accessed HA console via: [Terminal Add-on / Proxmox console]
- [ ] Ran: `nmcli connection show "Supervisor enp0s18"`
- [ ] Ran: `nmcli connection modify "Supervisor enp0s18" ipv4.dns "192.168.4.1"`
- [ ] Ran: `nmcli connection reload`
- [ ] Rebooted HA (if needed)

---

## Verification

**Script**: `04-verify-frigate-app-homelab-works.sh`
**Timestamp**: HH:MM
**Output**:
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
| **Fix Applied** | [Option B / Option C / None] |

---

## Files Modified
- [List any config files changed]

## Follow-Up Actions
- [ ] Update blueprint if new learnings
- [ ] Close GitHub issue
- [ ] Monitor stability (24h)
