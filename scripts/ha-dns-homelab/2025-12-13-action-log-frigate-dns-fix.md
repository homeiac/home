# Action Log: Home Assistant DNS Fix for .homelab Domains

**Date**: 2025-12-13
**Operator**: Claude Code AI Agent
**GitHub Issue**: #174
**Status**: In Progress

---

## Pre-Flight Checklist

| Check | Command | Expected | Actual | Status |
|-------|---------|----------|--------|--------|
| Mac DNS resolves frigate.app.homelab | `nslookup frigate.app.homelab` | 192.168.4.80 | 192.168.4.80 | PASS |
| Traefik responds | `curl -s http://192.168.4.80 -H "Host: frigate.app.homelab"` | HTTP 200 | TBD | |
| OPNsense has wildcard | `dig frigate.app.homelab @192.168.4.1 +short` | 192.168.4.80 | TBD | |
| MAAS forwards to OPNsense | `dig frigate.app.homelab @192.168.4.53 +short` | 192.168.4.80 | TBD | |

---

## Diagnosis Results

**Script**: `00-diagnose-dns-chain.sh`
**Timestamp**: TBD
**Output**:
```
[Run ./00-diagnose-dns-chain.sh and paste output here]
```

**Conclusion**: TBD

---

## HA Frigate Access Test

**Script**: `01-test-ha-can-reach-frigate.sh`
**Timestamp**: TBD
**Output**:
```
[Run ./01-test-ha-can-reach-frigate.sh and paste output here]
```

**Result**: TBD

---

## Fix Applied

**Option Used**: TBD

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
**Timestamp**: TBD
**Output**:
```
[Run ./04-verify-frigate-app-homelab-works.sh and paste output here]
```

**Result**: TBD

---

## Issues Encountered

(None yet)

---

## Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | In Progress |
| **Start Time** | 2025-12-13 |
| **End Time** | TBD |
| **Fix Applied** | TBD |

---

## Files Modified
- scripts/ha-dns-homelab/* (created)
- docs/troubleshooting/blueprint-ha-dns-homelab-resolution.md (created)

## Follow-Up Actions
- [ ] Run diagnosis scripts
- [ ] Apply fix (Option B or C)
- [ ] Update this log with results
- [ ] Close GitHub issue
- [ ] Monitor stability (24h)
