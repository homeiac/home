# RCA: Prometheus Storage Separation from Samba

**Date**: 2026-02-10
**Severity**: Medium
**Impact**: Potential data corruption risk, permission conflicts
**Resolution**: Storage paths separated, data migrated successfully

---

## Executive Summary

Prometheus and Samba storage were sharing the same underlying path (`/mnt/smb_data`), causing permission conflicts when Samba's init container ran `chown nobody:nogroup`. This created a risk of Prometheus data becoming inaccessible and complicated storage management due to misleading naming conventions.

---

## Root Cause Analysis

### Problem Statement

Prometheus TSDB data was stored at `/mnt/smb_data/prometheus` which was actually a symlink to `/mnt/samba-storage/smb_data/prometheus`. The Samba deployment's init container ran permission changes on the parent directory:

```yaml
# Problematic init container
initContainers:
- name: init-perms
  command:
  - sh
  - -c
  - |
    chown nobody:nogroup /mnt/smb_data  # Affects Prometheus subdirectory!
    chmod 0775 /mnt/smb_data
```

### Storage Layout Before Fix

```
/dev/sda1 (1.8TB) → / (root filesystem)
/dev/sdb  (196GB) → /mnt/samba-storage
                        └── smb_data/
                             ├── prometheus/prometheus-db/  ← Prometheus TSDB (17GB)
                             └── [samba shares]

/mnt/smb_data → symlink → /mnt/samba-storage/smb_data
```

### Issues Identified

| Issue | Impact | Risk Level |
|-------|--------|------------|
| Shared parent directory | Permission changes affect both services | High |
| Misleading naming (`smb_data` for Prometheus) | Operational confusion | Medium |
| Symlink indirection | Complicated troubleshooting | Low |
| Limited disk space (196GB) | Prometheus data could fill Samba disk | Medium |

### Contributing Factors

1. **Original architecture decision**: Prometheus PV was created to use existing Samba storage mount
2. **No storage isolation**: Single hostPath for multiple unrelated services
3. **Init container scope**: Samba init container affected entire mount, not just Samba directories

---

## Timeline

| Time | Event |
|------|-------|
| 2026-01-17 | Prometheus storage initially configured on `/mnt/smb_data/prometheus` |
| 2026-02-10 09:00 | Issue identified during storage architecture review |
| 2026-02-10 09:11 | Created `/mnt/prometheus` directory on VM |
| 2026-02-10 09:12 | Updated GitOps manifests |
| 2026-02-10 09:15 | Deleted old PV/PVC/StorageClass |
| 2026-02-10 09:17 | Flux reconciled, new storage created |
| 2026-02-10 09:23 | Migrated 17GB historical data |
| 2026-02-10 09:35 | Data migration verified, historical blocks loaded |

---

## Resolution

### Storage Layout After Fix

```
/dev/sda1 (1.8TB) → / (root filesystem)
                     └── /mnt/prometheus/prometheus-db/  ← Prometheus TSDB (isolated)

/dev/sdb  (196GB) → /mnt/samba-storage/  ← Samba only (no symlinks)
```

### Changes Made

1. **New Prometheus storage path**: `/mnt/prometheus` on root disk (1.5TB available)
2. **Samba uses direct path**: `/mnt/samba-storage` (no symlink)
3. **Removed symlink**: `/mnt/smb_data` symlink deleted
4. **Renamed resources**: `prometheus-2tb-storage` → `prometheus-storage` (cleaner naming)

### Git Commits

```
afb6c6f refactor(storage): separate Prometheus from Samba storage
```

**Files modified**:
- `gitops/clusters/homelab/infrastructure/monitoring/prometheus-storage-class.yaml`
- `gitops/clusters/homelab/infrastructure/monitoring/monitoring-values.yaml`
- `gitops/clusters/homelab/apps/samba/deployment.yaml`

---

## Verification

### Storage Isolation Confirmed

```bash
# Prometheus uses root disk
kubectl exec -n monitoring prometheus-... -c prometheus -- df -h /prometheus
# Output: /dev/sda1  1.7T  175G  1.5T  10% /prometheus

# Samba uses separate disk
ssh pumped-piglet.maas "qm guest exec 105 -- df -h /mnt/samba-storage"
# Output: /dev/sdb  196G   17G  170G   9% /mnt/samba-storage
```

### Historical Data Preserved

```bash
# Query data from Jan 27, 2026
curl "http://prometheus:9090/api/v1/query?query=count(up)&time=1769500000"
# Returns: {"status":"success","data":{"result":[{"value":[1769500000,"5"]}]}}
```

### Services Operational

- Prometheus: Scraping all targets, 16 historical TSDB blocks loaded
- Grafana: Dashboards displaying historical data
- Samba: Shares accessible via SMB

---

## Lessons Learned

### What Went Wrong

1. Storage paths were not isolated when Prometheus was first deployed
2. Naming convention (`smb_data`) was misleading
3. No documentation of storage dependencies between services

### What Went Right

1. Identified issue before actual data corruption occurred
2. Data migration preserved all historical metrics
3. Flux GitOps allowed clean, reversible changes

### Improvements

| Action | Priority | Status |
|--------|----------|--------|
| Create storage separation runbook | High | Done |
| Create data migration runbook | High | Done |
| Document storage architecture in inventory.txt | Medium | TODO |
| Add storage isolation to service deployment checklist | Medium | TODO |

---

## Prevention

### Storage Design Principles

1. **One service per storage path**: Never share hostPath mounts between unrelated services
2. **Clear naming**: Storage paths should reflect their purpose (`/mnt/prometheus` not `/mnt/smb_data/prometheus`)
3. **No symlinks for PVs**: Use direct paths to avoid indirection confusion
4. **Capacity planning**: Ensure each service has adequate dedicated space

### Monitoring Additions

Consider adding alerts for:
- Prometheus disk usage approaching 80%
- File permission changes in Prometheus data directory
- Unexpected ownership changes on critical paths

---

## References

- [Prometheus Storage Separation Runbook](prometheus-storage-separation.md)
- [Prometheus Data Migration Runbook](prometheus-data-migration.md)
- [Storage Architecture Investigation Runbook](storage-architecture-investigation.md)

---

**Tags**: prometheus, promethius, samba, storage, storage-separation, rca, incident, permissions, data-migration, gitops

**Owner**: Infrastructure Team
**Last Updated**: 2026-02-10
