# Action Log: Home Assistant DNS Fix for .homelab Domains

**Date**: 2025-12-13
**Operator**: Claude Code AI Agent
**GitHub Issue**: #174
**Status**: Completed

---

## Pre-Flight Checklist

| Check | Command | Expected | Actual | Status |
|-------|---------|----------|--------|--------|
| Mac DNS resolves frigate.app.homelab | `nslookup frigate.app.homelab` | 192.168.4.80 | 192.168.4.80 | ✅ |
| Traefik responds | `curl http://frigate.app.homelab/api/version` | HTTP 200 | 0.16.0-c2f8de9 | ✅ |
| OPNsense has wildcard | `dig frigate.app.homelab @192.168.4.1 +short` | 192.168.4.80 | 192.168.4.80 | ✅ |
| MAAS forwards to OPNsense | `dig frigate.app.homelab @192.168.4.53 +short` | 192.168.4.80 | 192.168.4.80 | ✅ |

---

## Diagnosis Results

**Script**: `00-diagnose-dns-chain.sh`
**Result**: All checks passed from Mac

**Script**: `06-check-ha-vm-dns.sh`
**Result**: DNS works from inside HA VM

```
--- HA VM DNS Configuration ---
nameserver 192.168.4.53 (MAAS DNS)
nameserver 2600:1700:7270:933e:be24:11ff:fed5:6f30
nameserver 192.168.86.1

--- Testing DNS Resolution from HA VM ---
nslookup frigate.app.homelab:
  Server: 192.168.4.53
  Address: 192.168.4.80 ✅

--- Testing HTTP Access to Frigate from HA VM ---
Frigate LoadBalancer IP: 192.168.4.82 (dynamically detected)

curl http://frigate.app.homelab/api/version (via Traefik):
  Result: 0.16.0-c2f8de9 ✅

curl http://192.168.4.82:5000/api/version (direct LB IP):
  Result: 0.16.0-c2f8de9 ✅
```

**Conclusion**: DNS resolution works correctly from inside HA VM. MAAS DNS (192.168.4.53) properly forwards .homelab queries to OPNsense (192.168.4.1).

---

## Root Cause Analysis

**Initial Assumption**: HA VM cannot resolve `frigate.app.homelab`

**Actual Finding**: DNS resolution works. The Frigate integration in HA is configured with `frigate.maas:5000` instead of `frigate.app.homelab`.

**Evidence**:
- `06-check-ha-vm-dns.sh` shows successful DNS resolution AND HTTP access via hostname
- Frigate integration title shows `frigate.maas:5000` (checked via HA API)

---

## Fix Applied

**Option Used**: None needed - DNS was already working

**Action Required**: Update Frigate integration URL in Home Assistant
1. Go to HA Settings → Devices & Services
2. Find Frigate integration
3. Click Configure
4. Update URL to: `http://frigate.app.homelab`

---

## Verification

**Script**: `04-verify-frigate-app-homelab-works.sh`
**Result**: All 5 checks passed

```
--- DNS Resolution ---
✓ Mac DNS: frigate.app.homelab -> 192.168.4.80

--- Traefik Routing ---
✓ Traefik routes http://frigate.app.homelab/ (HTTP 200)
✓ Direct Traefik IP with Host header (HTTP 200)

--- Home Assistant ---
✓ HA API accessible at http://192.168.4.240:8123
✓ Frigate entities in HA (1 found)

Summary: 5 passed, 0 failed
```

**Script**: `99-validate-deliverables.sh`
**Result**: All 21 checks passed

---

## Issues Encountered

### Issue 1: Wrong VM ID and Host
**Severity**: Medium
**Symptoms**: Script couldn't find HA VM
**Resolution**: Updated to VM ID 116 on chief-horse.maas

### Issue 2: Hardcoded Frigate IP
**Severity**: Low
**Symptoms**: Script used wrong Frigate service IP (83 vs 82)
**Resolution**: Added dynamic detection via kubectl to find running pod and matching service

### Issue 3: Wrong Port for Traefik
**Severity**: Medium
**Symptoms**: curl to frigate.app.homelab:5000 failed
**Resolution**: Use port 80 for Traefik (routes internally to 5000)

### Issue 4: ((PASS++)) with set -e
**Severity**: Low
**Symptoms**: Scripts exited early on first check
**Resolution**: Changed to PASS=$((PASS + 1)) syntax

---

## Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | ✅ Completed |
| **Start Time** | 2025-12-13 |
| **End Time** | 2025-12-13 |
| **Fix Applied** | None needed (DNS already working) |
| **Root Cause** | Frigate integration uses frigate.maas, not frigate.app.homelab |

---

## Deliverables Created

| File | Purpose |
|------|---------|
| `scripts/ha-dns-homelab/README.md` | Overview |
| `scripts/ha-dns-homelab/00-diagnose-dns-chain.sh` | DNS chain diagnosis from Mac |
| `scripts/ha-dns-homelab/01-test-ha-can-reach-frigate.sh` | Test HA API for Frigate |
| `scripts/ha-dns-homelab/02-print-opnsense-dns-fix-steps.sh` | OPNsense fix steps |
| `scripts/ha-dns-homelab/03-print-ha-nmcli-fix-commands.sh` | nmcli fix commands |
| `scripts/ha-dns-homelab/04-verify-frigate-app-homelab-works.sh` | End-to-end verification |
| `scripts/ha-dns-homelab/05-check-frigate-integration-url.sh` | Check Frigate config in HA |
| `scripts/ha-dns-homelab/06-check-ha-vm-dns.sh` | Test DNS from inside HA VM |
| `scripts/ha-dns-homelab/07-fix-ha-vm-dns.sh` | Fix DNS on HA VM |
| `scripts/ha-dns-homelab/99-validate-deliverables.sh` | Validate all constraints |
| `scripts/ha-dns-homelab/TEMPLATE-action-log-ha-dns-fix.md` | Reusable template |
| `docs/troubleshooting/blueprint-ha-dns-homelab-resolution.md` | Blueprint |

---

## Commits

- `1461267` - feat(ha-dns): add Home Assistant DNS resolution scripts
- `7a66742` - fix(ha-dns): use $((PASS + 1)) for set -e compatibility
- `9292350` - fix(ha-dns): improve scripts with dynamic Frigate IP detection

---

## Follow-Up Actions

- [x] Scripts created and validated
- [x] Blueprint documented
- [ ] User to update Frigate integration URL in HA to use frigate.app.homelab
- [ ] Close GitHub issue #174
