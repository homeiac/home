# Action Log: VirtioFS Import Setup

## Execution Date: 2025-12-12

## Outcome: SUCCESS

Old Frigate recordings (118GB) now accessible to K8s Frigate pod via virtiofs mount, with database entries and thumbnails fully restored. All 1,977 review segments from the old LXC deployment are now visible in the Review UI.

---

## Pre-flight Checks
- [x] Proxmox version >= 8.4: **8.4.14**
- [x] K3s cluster healthy: 3/3 nodes Ready
- [x] Source data exists: 120GB at `/local-3TB-backup/subvol-113-disk-0/frigate/`

---

## Key Decision: No Data Copy Needed

**Original plan**: Create new ZFS dataset, copy 120GB of recordings.

**Revised approach**: Mount the existing `subvol-113-disk-0` dataset directly via virtiofs. Pod accesses `/mnt/frigate-import/frigate/` subdirectory.

**Result**: Zero copy time, instant access.

---

## Step 1: Create ZFS Dataset
- **Script**: `./01-create-zfs-dataset.sh`
- **Status**: SKIPPED - using existing dataset instead

---

## Step 2: Copy Recordings
- **Script**: `./02-copy-recordings.sh`
- **Status**: SKIPPED - no copy needed
- **Note**: Initially started rsync (~5MB/s), then cp -a (~30MB/s), but cancelled after realizing we can mount existing dataset directly.

---

## Step 3: Create Directory Mapping
- **Script**: Manual `pvesh` command (script not updated for existing dataset)
- **Status**: SUCCESS
- **Command**:
```bash
ssh root@pumped-piglet.maas "pvesh create /cluster/mapping/dir --id frigate-import --map node=pumped-piglet,path=/local-3TB-backup/subvol-113-disk-0"
```

---

## Step 4: Attach VirtioFS to VM
- **Script**: `./04-attach-virtiofs-to-vm.sh`
- **Status**: SUCCESS
- **VM downtime**: 68 seconds
- **K3s rejoin time**: Immediate (node was Ready when checked)

---

## Step 5: Mount in VM
- **Script**: `./05-mount-in-vm.sh`
- **Status**: SUCCESS (after troubleshooting)

### Issues Encountered:

**Issue 1: SSH not working to VM**
- Direct SSH to `ubuntu@192.168.4.210` failed (port 22 connection refused)
- `qm guest exec` also failed - guest agent not installed

**Solution**: Created `00-install-guest-agent.sh` to install qemu-guest-agent via privileged pod with nsenter.

**Issue 2: Mount point existed but empty**
- `/mnt/frigate-import` existed from previous 9p attempt but virtiofs wasn't mounted
- Old 9p fstab entry needed updating

**Solution**:
```bash
ssh root@pumped-piglet.maas "qm guest exec 105 -- mount -t virtiofs frigate-import /mnt/frigate-import"
ssh root@pumped-piglet.maas "qm guest exec 105 -- sed -i 's/9p trans=virtio,version=9p2000.L/virtiofs defaults,nofail/' /etc/fstab"
```

---

## Step 5a: Update Deployment
- **Script**: `./05a-update-deployment.sh`
- **Status**: SUCCESS
- **Change**: hostPath `/mnt/frigate-import` → `/mnt/frigate-import/frigate`

---

## Step 6: Verify Frigate Access
- **Script**: `./06-verify-frigate-access.sh`
- **Status**: SUCCESS (after fixing stale pods)

### Issues Encountered:

**Issue 1: Pods in Unknown state**
- Old pods stuck in Unknown status after VM restart

**Solution**: Force delete pods, let deployment recreate them.
```bash
kubectl delete pods -n frigate --all --force --grace-period=0
```

**Issue 2: Service endpoints empty**
- Service selector had kustomize labels (`app.kubernetes.io/name`, etc.)
- Pod only had `app: frigate` label

**Solution**: Created `07-fix-service-selector.sh` to delete and recreate services.

---

## Step 7: Fix Service Selector
- **Script**: `./07-fix-service-selector.sh`
- **Status**: SUCCESS
- **Result**: `frigate.app.homelab` now working

---

## Final Status
- **Overall**: SUCCESS (VirtioFS mount + Database import complete)
- **K3s cluster**: 3/3 nodes Ready
- **Frigate pod**: Running v0.16.0
- **Old recordings**: 118GB accessible at `/import/recordings`
- **Database entries**: 1,977 reviewsegments, 3,820 events imported
- **Thumbnails**: 2,507 symlinks created for old clips
- **Review UI**: Old recordings now visible with thumbnails
- **LoadBalancer IP**: 192.168.4.83
- **Ingress**: `frigate.app.homelab` working

---

## Step 8: Database Import - Restore Old Recordings to Review UI

### Problem
Old recordings (118GB) were visible on disk at `/import/recordings` and `/import/clips`, but **NOT visible in Frigate Review UI**. No database entries existed for these recordings.

### Investigation

**Step 8a: Check for Old Database Files**
- **Script**: `./08-check-for-old-frigate-db.sh`
- **Status**: NOT FOUND on fun-bedbug or still-fawn
- **Result**:
  - fun-bedbug LXC 113: Only 6 recordings (too new - after migration to K8s)
  - still-fawn: No `/config/frigate.db` found
  - Mounted `/import` data: Only `recordings/` and `clips/` folders, no database

**Step 8b: Check PBS Backups**
- **Script**: `./09-check-pbs-backups.sh`
- **Status**: SUCCESS
- **Found**: 4 backups of LXC 113 on pumped-piglet (homelab-backup storage)
  - Dec 6, 2024: 159GB (most recent before migration)
  - Nov 22, 2024: 156GB
  - Nov 2, 2024: 152GB
  - Oct 16, 2024: 144GB

**Step 8c: Restore Backup to Temp Container**
- **Script**: `./10-restore-pbs-backup.sh`
- **Status**: SUCCESS
- **Action**: Restored Dec 6 backup to temp container 9113
- **Result**: Extracted `/config/frigate.db` with:
  - **45,441 recordings**
  - **1,956 reviewsegments**
  - **3,782 events**

### Schema Mismatch Issue

**Step 8d: Check Database Schema**
- **Script**: `./11-check-db-schema.sh`
- **Status**: MISMATCH FOUND
- **Issue**: Old database (v0.14.1) has `has_been_reviewed` column in `reviewsegments` table
- **Current**: New database (v0.16.0) doesn't have this column
- **Solution**: Export only compatible columns during merge

### Database Merge Process

**Step 8e: Export Data from Old Database**
- **Script**: `./12-export-old-db-data.sh`
- **Status**: SUCCESS
- **Actions**:
  - Extracted specific columns matching new schema
  - Exported reviewsegments (without `has_been_reviewed`)
  - Exported events
  - Exported recordings
- **Output**: SQL INSERT statements compatible with v0.16.0 schema

**Step 8f: Import Data into K8s Database**
- **Script**: `./13-import-to-k8s-db.sh`
- **Status**: SUCCESS (after fixing kubectl cp corruption)
- **Issue**: `kubectl cp` corrupted database files during transfer
- **Solution**: Used base64 encoding for safe transfer
  ```bash
  # Encode on source
  base64 < old-data.sql > old-data.sql.b64

  # Transfer and decode in pod
  kubectl cp old-data.sql.b64 frigate/frigate-pod:/tmp/
  kubectl exec -n frigate frigate-pod -- sh -c "base64 -d < /tmp/old-data.sql.b64 > /tmp/old-data.sql"
  ```
- **Merge method**: `INSERT OR IGNORE` to avoid duplicates

### Thumbnail Path Issue

**Step 8g: Create Symlinks for Old Thumbnails**
- **Script**: `./14-create-thumbnail-symlinks.sh`
- **Status**: SUCCESS
- **Issue**: Old thumbnails at `/import/clips/review/` but Frigate expects `/media/frigate/clips/review/`
- **Solution**: Created 2,507 symlinks from `/media/frigate/clips/review/` to `/import/clips/review/`
- **Result**: Thumbnails now display correctly in Review UI

### Final Database Status

**Step 8h: Verify Database Import**
- **Script**: `./15-verify-db-import.sh`
- **Status**: SUCCESS
- **Final counts**:
  - **1,977 reviewsegments** in database
  - **3,820 events**
  - Old recordings now visible in Review UI with thumbnails

---

## Scripts Created/Modified

| Script | Purpose |
|--------|---------|
| `00-install-guest-agent.sh` | Install qemu-guest-agent via privileged pod |
| `04-attach-virtiofs-to-vm.sh` | Attach virtiofs to VM (worked) |
| `05-mount-in-vm.sh` | Mount virtiofs via qm guest exec |
| `05a-update-deployment.sh` | Update hostPath to include /frigate |
| `06-verify-frigate-access.sh` | Verify pod can see recordings |
| `07-fix-service-selector.sh` | Fix service selector mismatch |
| `08-check-for-old-frigate-db.sh` | Search for old database files on LXC hosts |
| `09-check-pbs-backups.sh` | List PBS backups of LXC 113 |
| `10-restore-pbs-backup.sh` | Restore backup to temp container 9113 |
| `11-check-db-schema.sh` | Compare old and new database schemas |
| `12-export-old-db-data.sh` | Export compatible columns from old database |
| `13-import-to-k8s-db.sh` | Import old data into K8s database (with base64) |
| `14-create-thumbnail-symlinks.sh` | Create symlinks for old thumbnails |
| `15-verify-db-import.sh` | Verify database import success |
| `16-cleanup-temp-container.sh` | Remove temp container 9113 (optional) |
| `17-document-import-process.sh` | Document the import methodology |
| `18-create-restore-runbook.sh` | Create runbook for future database restores |

---

## Lessons Learned

### VirtioFS and VM Management

1. **Don't copy when you can mount** - Existing dataset can be mounted directly, no need to copy 120GB.

2. **qemu-guest-agent not installed by default** - K3s VM 105 didn't have it; needed privileged pod to install.

3. **Service selector mismatch from kustomize** - When applying manifests directly (not via kustomize), services may have extra labels in selector that pods don't have.

4. **SSH may not be available** - VM may not have SSH server running; qm guest exec is more reliable if guest agent is installed.

### Database Import and Migration

5. **Recordings without database = invisible** - Files on disk don't appear in Frigate UI without database entries. Always backup and restore the database when migrating.

6. **PBS backups contain everything** - Proxmox Backup Server backups include the full LXC filesystem, including databases. Restore to temp container to extract specific files.

7. **Schema evolution breaks direct imports** - Database schema changes between Frigate versions (e.g., v0.14.1 → v0.16.0) require column-specific exports/imports, not full table dumps.

8. **kubectl cp corrupts binary files** - Don't use `kubectl cp` for SQLite databases or other binary files. Use base64 encoding for safe transfer to/from pods.

9. **Thumbnail paths are hardcoded** - Frigate expects thumbnails at specific paths (`/media/frigate/clips/review/`). Use symlinks to map old paths to new locations.

10. **INSERT OR IGNORE for safe merges** - When merging old data into existing database, use `INSERT OR IGNORE` to skip duplicates and avoid constraint violations.

---

## References
- [Proxmox 8.4 VirtioFS Tutorial](https://forum.proxmox.com/threads/proxmox-8-4-virtiofs-virtiofs-shared-host-folder-for-linux-and-or-windows-guest-vms.167435/)
- [VirtioFS vs 9p Performance](https://www.phoronix.com/news/Linux-5.4-VirtIO-FS)
- Plan: `/Users/10381054/.claude/plans/wiggly-percolating-sunrise.md`
