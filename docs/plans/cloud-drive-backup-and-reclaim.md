# Cloud Drive Backup & Space Reclaim (Google Drive + OneDrive + Google Photos)

**Status:** Proposed — design review
**Date:** 2026-11-14
**Owner:** homelab
**Related:** `scripts/backup/` (existing rclone + Google Drive tooling), `gitops/clusters/homelab/apps/samba/`, `gitops/clusters/homelab/apps/postgres/gdrive-sync-cronjob.yaml`

---

## 1. Problem

Google Drive, Google Photos and OneDrive are filling up. Google Drive and Google Photos
share one Google storage quota. The goal is to pull a complete, verified copy of all three
into the homelab, then delete the large items from the cloud to reclaim quota.

The second half changes the risk profile: **after the delete, the homelab copy is
the only copy.** The design is therefore built around making that copy trustworthy
before anything is removed from the cloud.

## 2. Goals

| # | Goal |
|---|------|
| G1 | Full copy of Google Drive, OneDrive and Google Photos held in the homelab, refreshed automatically (Photos on Takeout's 2-month cadence; see §5.4). |
| G2 | Two independent local copies on separate physical disks: a **primary** (browseable over SMB) and a **secondary** on the SSK USB disk. |
| G3 | A **reclaim workflow**: report the largest items, prove each one is present and hash-identical in both local copies, delete only what the user explicitly approves. |
| G4 | The user's Mac is **not in the data path**. Data flows cloud → homelab directly. (A browser is needed once per provider for OAuth sign-in; any browser is acceptable.) |
| G5 | Everything as code: Flux-managed workloads, scripts in `scripts/backup/`, SOPS-encrypted secrets. No hand-run one-liners. |

## 3. Non-goals

- **Offsite copy.** After reclaim, both copies live in the same house. Fire/theft/surge
  protection is out of scope here and listed as an open question (§12).
- **Two-way sync / restoring to the cloud.** This is a one-way pull.
- **Backing up the large WD external disks** (`sda` BitLocker 2.3T, `sdb` PBS pool 2.7T). These are not cloud data and already serve as backup targets.

## 4. Current state (verified 2026-11-14)

| Item | Fact |
|------|------|
| Host | `pumped-piglet` (192.168.4.175) — Proxmox node, hosts K3s VM 105 `k3s-vm-pumped-piglet-gpu` |
| rclone | v1.76.0 installed on pumped-piglet host (official .deb, SHA256-verified) |
| SMB share | Samba pod (namespace `samba`, LB `192.168.4.120`), share `secure` → hostPath `/mnt/samba-storage` inside VM 105 |
| SMB backing disk | VM 105 `scsi1` = zvol `local-3TB-backup/vm-105-disk-0`, **200G, 170G free** (ext4) |
| 3TB pool | `local-3TB-backup` on WD 3TB USB HDD: 2.72T, 1.90T used, **752G free**. Shared with the PBS datastore (`subvol-103-homelab-backup`, 1.80T). |
| SSK disk | USB SSD on pumped-piglet, serial `DD56419883935`, **238.5G**, freshly formatted **exFAT**, label `SSK`, UUID `EBFF-FC78` |
| Existing Google Drive remote | `gdrive-backup` (scope=`drive`, full access) in SOPS secret `database/rclone-gdrive-config` — used by `postgres-gdrive-sync`. **Token still valid** (Phase 0). It uses rclone's **shared Google client_id, which rclone says is being retired during 2026**. |
| **Google quota (Phase 0, 2026-11-15)** | 100 GiB plan: Drive **9.2 GiB**, Other (**Photos + Gmail**) **80.2 GiB**, free **10.6 GiB** |
| **Google Drive contents (Phase 0)** | **8.25 GB** in 23,360 files, plus 114 native Docs/Sheets/Slides. The three largest top-level folders are 3.4, 2.1 and 1.9 GB (names kept out of this public repo). Full report on the host: `/var/lib/cloud-backup/reports/measure-20261115-031305.txt` |
| **OneDrive (Phase 0, 2026-11-15)** | Personal account, **free 5 GiB plan**: used **3.9 GiB**, free **1.1 GiB**. Listable files **2.46 GB** in 4,549 files. The rest of "used" is Personal Vault, which the Graph API can't list ("ObjectHandle is Invalid"), plus version history. Personal Vault is **excluded** (`CB_ONEDRIVE_EXCLUDE`); copy anything in it into a normal folder by hand. Report on the host: `/var/lib/cloud-backup/reports/measure-20261115-065326.txt` |
| Google Photos API | Since **2025-03-31** the Library API only exposes media the calling app uploaded itself. rclone's `googlephotos` backend (and every other third-party tool) **can't list or download an existing library**. Old tokens don't keep full access. |
| Google Takeout | Only complete Photos export. Since **June 2026** supports **scheduled, incremental** Photos-only exports: every 2 months for 1 year, delivered to Drive / OneDrive / Dropbox / Box or as download links. |

**Related finding:** `postgres-gdrive-sync` CronJob is pinned to `k3s-vm-fun-bedbug`, which is powered off
(thermal) — its Jobs have been `Pending` for ~171 days. Postgres offsite sync has silently not run. Tracked separately.

## 5. Architecture

```
 ┌───────────────┐
 │ Google Photos │  scheduled Takeout (Photos only, every 2 months, incremental)
 └──────┬────────┘
        │ download links → clicked in in-homelab browser (download-browser pod)
        │ → .tgz saved straight to gphotos/_incoming/ on the primary disk
        ▼
   ┌──────────────┐      ┌──────────────┐
   │ Google Drive │      │   OneDrive   │
   └──────┬───────┘      └──────┬───────┘
          │  rclone copy (pull, never sync)
          ▼                     ▼
┌───────────────────────────────────────────────────────────┐
│ K8s CronJob  cloud-backup/cloud-drive-pull   (nightly)    │
│ node: k3s-vm-pumped-piglet-gpu                            │
│ writes → /mnt/samba-storage/cloud-backup/{gdrive,onedrive}│
│ replaced/removed-upstream files → .versions/<date>/       │
│                                                           │
│ K8s CronJob  cloud-backup/photos-takeout-ingest (daily)   │
│ new gphotos/_incoming/*.tgz → verify → extract →          │
│   /mnt/samba-storage/cloud-backup/gphotos/                │
└──────────────────────────┬────────────────────────────────┘
                           │  PRIMARY COPY (browseable)
                           ▼
        \\192.168.4.120\secure\cloud-backup     (SMB, read via Finder/Explorer)
        zvol local-3TB-backup/vm-105-disk-0     (ZFS snapshots: daily×14, monthly×6)
                           │
                           │  host systemd timer  cloud-backup-mirror.timer
                           │  (mount SMB read-only → rclone copy → SSK)
                           ▼
        SSK exFAT  /mnt/ssk-cloud/cloud-backup   SECONDARY COPY (separate disk)
```

### 5.1 Why the primary lives on the SMB volume

The user wants a browseable copy. Putting the primary *on* the Samba volume makes it
browseable for free and avoids a third copy on the same 3TB pool (a separate ZFS
dataset plus a Samba copy would be two copies on one physical disk — no extra safety,
double the space).

### 5.2 Why a K8s CronJob for the pull

- The Samba volume is an ext4 zvol attached to VM 105; the host cannot safely mount it
  while the VM uses it. The writer must run inside VM 105 → a K3s workload pinned to that node.
- Matches the existing `postgres-gdrive-sync` pattern and keeps it under Flux (G5).

### 5.3 Why a host timer for the secondary copy

The SSK disk is plugged into the pumped-piglet host. Passing a USB disk into the VM to
reach a pod adds moving parts. The host instead mounts the SMB share **read-only** and
copies to the SSK. The secondary copy therefore depends only on Samba being up, and
the copy job can never modify the primary.

### 5.4 Google Photos via scheduled Takeout

No API path exists for an existing library (§4), so Photos comes in through **Google Takeout**
and rides the Drive pipeline:

1. **Set up once (in a browser, by the user):** takeout.google.com → select **Google Photos only**
   → *Export every 2 months for 1 year* → file type **.tgz**, size **50 GB** →
   delivery **Send download link via email**. The first export is a full library. Later ones should be incremental
   (new and changed items) per Google's June 2026 change. Older guides say every export is a
   full library, so this is **verified on the second run** before relying on it. If they turn out to be
   full, ingest de-duplicates by path and hash, and old archives are deleted from Drive sooner.
2. **Fetch with an in-homelab browser:** a Firefox container (`apps/cloud-backup/download-browser`,
   linuxserver Firefox image with a web-based desktop, pinned tag) runs on pumped-piglet. Its
   Downloads folder is the hostPath `/mnt/samba-storage/cloud-backup/gphotos/_incoming/`, so
   archives land on the primary disk and are visible on the SMB share as they arrive. When
   Google's "export is ready" email arrives, the user opens `download-browser` (Traefik Ingress,
   LAN/Tailscale only), signs in to Google once (the profile persists), and clicks the download
   links. The Mac only displays the remote browser; archive bytes go Google → homelab disk (G4).
   The browser profile lives in `/var/lib/cloud-backup/browser/`, outside the share, so cookies
   are never browseable. Small footprint (1 Gi request), always on, behind basic auth
   (`download-browser-auth` SOPS secret). Links expire after 7 days.
   *Later (optional):* a Playwright job reuses that same signed-in profile to open the Takeout
   "manage exports" page and click every part, so each export is one command. Fully headless
   sign-in isn't used: Google blocks automated sign-ins and often re-asks for the password before
   Takeout downloads. When that happens the job stops and the user clicks in the browser instead.
3. **Ingest:** `photos-takeout-ingest` finds archives it hasn't processed yet, checks each one
   (download complete, no `.part` file; `tar -tzf` completes), extracts into `cloud-backup/gphotos/`
   (`Google Photos/<album or year>/…` plus Takeout's `.json` metadata sidecars), and records each archive in
   `gphotos/_ingested.tsv` (archive name, size, MD5, file count, date).
4. **Archive cleanup:** the local `.tgz` is deleted once it is extracted and the extracted tree is
   on the SSK; the extracted tree is the copy that's kept. Nothing is stored in cloud quota.

**Why download links (not Add to Drive / OneDrive):** delivering into a cloud drive costs that
drive's quota. Google has 10.6 GiB free and the export is ~80 GiB; OneDrive is a 5 GiB plan. Links
cost no cloud space and, clicked in the in-homelab browser, land directly on the homelab disks. The
trade-off is a few clicks per export, every 2 months, within 7 days. The same browser handles any
other click-to-download export (e.g. OneDrive Personal Vault contents). Alternative if that becomes
annoying: buy one month of 2 TB Google storage, deliver to Drive, and let the nightly pull fetch it.

**Recurrence ends after a year.** The Takeout schedule has to be renewed by hand every
12 months. The ingest job warns (status marker plus alert) if no new archive has arrived in 70 days.

**Deleting from Google Photos is manual.** The API can't delete library items either, so
reclaim for Photos produces a **list** (album/date ranges plus the files it covers, all
verified in both local copies). The user deletes those items in the Photos web UI, and they go
to Photos Trash for 60 days.

## 6. Components

| Component | Location | Notes |
|-----------|----------|-------|
| Namespace `cloud-backup` | `gitops/clusters/homelab/apps/cloud-backup/` | New Flux app |
| CronJob `cloud-drive-pull` | same dir | `rclone/rclone:1.76.0` (tag to be verified before merge), `concurrencyPolicy: Forbid`, nightly 01:30 |
| Writable rclone config | hostPath `/var/lib/cloud-backup/rclone/` in VM 105 | Copied from the Proxmox host by `cloud-backup-seed-k8s-config.sh` (host → VM, `qm guest exec --pass-stdin`); see §8 |
| Status marker | `/mnt/samba-storage/cloud-backup/_status/<remote>.json` | last success time, bytes, file count, errors |
| ZFS snapshots | sanoid policy for `local-3TB-backup/vm-105-disk-0` | via existing `scripts/backup/setup-zfs-snapshots.sh` |
| `cloud-backup-mirror.{service,timer}` | `scripts/backup/systemd/` | host-side, installed by `scripts/backup/install-cloud-backup-mirror.sh` |
| CronJob `photos-takeout-ingest` | `apps/cloud-backup/` | Daily. Verifies and extracts new Takeout archives into `gphotos/`, maintains `_ingested.tsv`, and alerts if no archive has arrived in 70 days |
| `cloud-backup-measure.sh` | `scripts/backup/` | Phase 0 sizing (Drive, OneDrive, and Google storage split Drive vs. Photos via `rclone about`) |
| `cloud-reclaim-report.sh` | `scripts/backup/` | Largest-items report + dual-copy verification |
| `cloud-reclaim-delete.sh` | `scripts/backup/` | Deletes only an approved, verified list |

## 7. Safety invariants

These are hard rules. Each is enforced in code, not just documented.

| # | Invariant | Enforcement |
|---|-----------|-------------|
| S1 | Backup jobs **never** delete local data because it vanished upstream. | Jobs use `rclone copy` with `--backup-dir` for overwrites; `rclone sync` is forbidden in `cloud-backup` manifests and scripts (grep check in `scripts/backup/test-backup-strategy.sh`). |
| S2 | The mirror job can't modify the primary. | Host mounts SMB with `-o ro`. |
| S3 | Nothing is deleted from the cloud unless it is present and **hash-identical in both** local copies. | `cloud-reclaim-report.sh` runs `rclone check --one-way --download=false` against primary and SSK; only rows passing both go to the candidate list. |
| S4 | Nothing is deleted from the cloud without explicit user approval of the exact list. | `cloud-reclaim-delete.sh` requires `--approved <file>`, prints count/total GB, requires typing the total GB to confirm; refuses rows not in the latest verified report. |
| S5 | Cloud deletes are recoverable for a grace period. | Deletes go to Drive Trash / OneDrive Recycle Bin (rclone default, **no** `--drive-use-trash=false`). Emptying trash is a separate, manual step. |
| S6 | The SSK is the right disk. | Mirror mounts **by UUID** `EBFF-FC78` and checks serial `DD56419883935`; aborts otherwise. |
| S7 | A partially completed pull never looks like a complete one. | Status marker written only on exit 0; reclaim report refuses to run if either copy's marker is older than 48h. |
| S8 | A Takeout archive is never deleted, locally or from Drive, before its contents are extracted into the primary **and** mirrored to the SSK. | Ingest deletes the local `.tgz` only after extraction succeeds and the file count matches `tar -tzf`. The Drive copy only becomes a reclaim candidate once `_ingested.tsv` has the row **and** the SSK mirror holds the extracted files. |

## 8. Secrets & OAuth

- **Google Drive:** reuse the existing `gdrive-backup` OAuth token (scope `drive`) if it still
  refreshes; otherwise re-authorize. Verified in Phase 1 with `rclone about`.
- **OneDrive:** `cloud-backup-auth-onedrive.sh`. `rclone authorize` runs on the host, and the
  browser redirect comes back through an SSH tunnel to `localhost:53682`. The drive is taken from
  Graph `GET /me/drive`, not rclone's drive picker: the picker can pick Personal Vault, which loops
  on "ObjectHandle is Invalid". `--repair` re-detects the drive from the stored token without
  signing in again. The token lands on the server; it is never pasted into chat or committed in plain text.
- **Token refresh:** OneDrive rotates refresh tokens, so rclone needs a **writable** config.
  The CronJob mounts the hostPath `/var/lib/cloud-backup/rclone/rclone.conf` (VM 105, dir 0700,
  file 0600) and rclone persists refreshed tokens there. That path is **outside** the SMB share,
  so tokens are never browseable.
- **Getting the config there:** `cloud-backup-seed-k8s-config.sh` copies the host's rclone config
  into the VM with `qm guest exec --pass-stdin`. The tokens go host → VM only: they never pass
  through the workstation and are **not committed at all** (not even SOPS-encrypted). This
  replaces the earlier idea of a SOPS seed Secret plus an initContainer. Idempotent; `--force` to
  re-seed after re-authorizing a remote on the host. Trade-off: rebuilding VM 105 needs a re-seed,
  which is one command.

## 9. Data-format notes

| Topic | Handling |
|-------|----------|
| Google Docs/Sheets/Slides (native) | Exported as `docx/xlsx/pptx` (`--drive-export-formats`). Exports lose comments, revision history and form links, so **native Google files are excluded from reclaim by default**. |
| Google "shared with me" | Not included (`--drive-shared-with-me=false`); only owned files count toward quota. |
| Google duplicate names | Drive allows two files with the same name in one folder; rclone de-dupes on copy with a warning. Report lists them. |
| OneDrive hashes | QuickXorHash; rclone computes it locally for verification. |
| exFAT (SSK) | No POSIX perms/symlinks, case-insensitive, no 4GB limit. Acceptable for a file archive. Case-only name collisions (possible from Google Drive) are reported by the mirror job. |
| SMB perms | Share uses `force user=nobody`, mask 0770. Pull job runs as uid/gid 65534 so files are browseable. |
| Google Photos (Takeout) | Originals in their uploaded quality, plus a `.json` sidecar per item (taken time, GPS, description). Edited versions come out as separate `-edited` files. EXIF in the files isn't rewritten, but the sidecars are kept so the metadata isn't lost. Partner-shared and shared-album items owned by others aren't included. |

## 10. Capacity

| Copy | Space |
|------|------|
| Primary (SMB zvol) | 170G free now. Can be grown online: `qm resize 105 scsi1 +<N>G` + `resize2fs` in the VM. The pool has 752G free but is shared with PBS (1.80T and growing). |
| Secondary (SSK) | 238G total. |

**Hard gate:** if `gdrive + onedrive + gphotos` (owned, excluding native Docs) > ~220G, the SSK can't
hold a full second copy and G2 fails. Photos libraries are often the largest of the three.
During ingest the primary temporarily needs room for **archive + extracted** (≈2× the archive
size, up to 50 GB per archive), so ingest processes one archive at a time. Options then: a bigger second disk, or limit reclaim
scope to what fits. The gate is evaluated in Phase 0, before any download.

## 11. Monitoring & failure modes

| Failure | Detection | Effect |
|---------|-----------|--------|
| Pull job fails | `KubeJobFailed` alert (kube-prometheus-stack); stale status marker | Primary stale; reclaim blocked by S7 |
| OAuth token expired/revoked | rclone exit code + log `invalid_grant` | Same as above; re-run Phase 1 auth for that provider |
| Primary disk full | rclone `no space left`; status marker not updated | Grow zvol (§10) |
| SSK unplugged or wrong disk | mirror unit fails on UUID/serial check | Secondary stale; reclaim blocked |
| PBS growth starves the pool | `zpool list` free < 15% | Shared pool; PBS prune or a bigger disk |
| Node/cluster outage (as on 2026-11-14) | Job doesn't run | Catches up on the next run; `copy` is idempotent |
| Takeout export fails (quota full) or the schedule lapses after 12 months | No new archive in 70 days → ingest alert | Photos copy goes stale; renew the schedule or switch the delivery target |
| Corrupt or partial Takeout archive | `tar -tzf` fails or size mismatch → ingest marks the row `failed` and skips it | Archive kept on Drive (S8); request a re-export |

## 12. Open questions

1. **Offsite.** After reclaim, should a third copy go somewhere off-premises (e.g. a friend's NAS, cold-storage bucket)?
2. ~~**First Takeout delivery target.**~~ *Answered 2026-11-15:* neither cloud has room (Google
   10.6 GiB free vs ~80 GiB of Photos; OneDrive is a 5 GiB plan). Use **download links fetched on the
   host** (§5.4). Fallback: one month of 2 TB Google storage.
5. **Own Google OAuth client_id.** rclone's shared client_id is being retired during 2026. Create a
   personal Google Cloud OAuth client (Drive API, "Desktop app") and re-authorize `gdrive-backup` before
   Phase 2. This also fixes the existing `postgres-gdrive-sync` remote.
3. **Schedule.** Nightly is the default. Once reclaim is done the cloud stops growing as fast; weekly may be enough.
4. **Retention of `.versions/`.** Default 90 days, then prune. OK?

## 13. Alternatives considered

| Option | Why not |
|--------|---------|
| `rclone sync` instead of `copy` | Propagates cloud deletions locally — after reclaim it would erase the only copy. Violates S1. |
| Separate ZFS dataset on the 3TB pool as primary + copy into Samba | Two copies on the same physical disk; no added safety, double the space. |
| Run everything on the host (no K8s) | Host can't mount the Samba zvol while VM 105 uses it; would also bypass Flux. |
| Sync via the Mac (Google Drive for Desktop / OneDrive app) | User requirement G4: Mac not in the path. |
| SSK as ext4 | Linux-only. exFAT keeps the SSK readable on any laptop in an emergency. |
| rclone `googlephotos` backend | Since 2025-03-31 it can only see media rclone uploaded itself. It can't back up an existing library. |
| Photos Picker API | Requires picking items or albums by hand in a browser each time. No unattended full-library access. |
| Takeout delivered as download links | Needs a browser to fetch (Mac in the path, G4), and links expire after 7 days. |

## 14. Implementation plan

Each phase ends with a check that has to pass before the next one starts.

### Phase 0 — Measure (read-only) — *done 2026-11-15*
- Scripts (all in `scripts/backup/`, shared settings in `cloud-backup-common.sh`):
  - `cloud-backup-install-rclone.sh`: pinned rclone v1.76.0 on the host, SHA256-verified, idempotent.
  - `cloud-backup-seed-gdrive-config.sh`: decrypts the existing SOPS rclone config and streams it to the host (never printed or written locally); merges by remote section.
  - `cloud-backup-auth-onedrive.sh`: interactive one-time OneDrive OAuth. rclone runs on the host and the browser redirect is tunnelled over SSH; default drive from Graph `/me/drive`; `--repair` mode.
  - `cloud-backup-measure.sh`: `rclone about` plus one recursive listing per remote, giving totals, native-Docs count, per-folder sizes, largest files and the capacity gate.
  - `cloud-backup-format-ssk.sh --yes`: (re)format the SSK, located by USB serial. Already run 2026-11-14.
- **Gate:** sizes recorded in §4 (Drive ✔ 8.25 GB, OneDrive ✔ 2.46 GB); capacity gate (§10) evaluated (10.7 GB fits both copies, Photos measured at first Takeout); user confirms scope.

### Phase 1 — Auth & secrets
- Verify the existing `gdrive-backup` token, or re-authorize. Create the `onedrive:` remote via headless OAuth.
- Seed the K3s VM with `cloud-backup-seed-k8s-config.sh` (done 2026-11-15).
- **User (browser):** set up the scheduled Google Takeout for Photos (§5.4), delivery by download link.
- **Gate:** `rclone about gdrive:` and `rclone about onedrive:` succeed from inside the pod; Takeout
  confirmation email received.

### Phase 2 — Primary pull (Flux)
- `apps/cloud-backup/cloud-drive-pull`: CronJob (02:30 nightly, `rclone/rclone:1.76.0`, `copy` + `--backup-dir .versions/<date>/`), status in `/var/lib/cloud-backup/status/last-run.json`. Scripts: `cloud-backup-run-now.sh`, `cloud-backup-status.sh`.
- Grow the SMB zvol if Phase 0 shows a need.
- First run triggered manually: `cloud-backup-run-now.sh`.
- **Gate:** status marker shows exit 0; `rclone check --one-way` cloud→primary reports 0 differences; files visible at `\\192.168.4.120\secure\cloud-backup`.

### Phase 2b — Google Photos ingest
- `apps/cloud-backup/download-browser`: Firefox web desktop, Downloads = `gphotos/_incoming/`, Ingress on the wildcard domain, basic auth (§5.4). Scripts: `download-browser-create-secret.sh`, `download-browser-password.sh` (clipboard), `download-browser-status.sh`.
- `photos-takeout-ingest` CronJob (§5.4).
- **Gate:** the first full export is ingested; `_ingested.tsv` file counts match `tar -tzf` for every
  archive; the item count in `gphotos/` is within a few percent of the library count shown in Google
  Photos. After the **second** scheduled export, confirm whether it was incremental and update §5.4.

### Phase 3 — Snapshots
- sanoid policy for `local-3TB-backup/vm-105-disk-0` (daily×14, monthly×6).
- **Gate:** `zfs list -t snapshot` shows the policy taking snapshots.

### Phase 4 — Secondary copy (SSK)
- `install-cloud-backup-mirror.sh` installs systemd units on pumped-piglet: fstab entry by UUID (`nofail`), read-only CIFS mount of the share, `rclone copy` → SSK.
- **Gate:** `rclone check` primary↔SSK reports 0 differences.

### Phase 5 — Reclaim report (read-only)
- `cloud-reclaim-report.sh` → `reclaim-candidates-<date>.csv`: path, size, provider, hash, `in_primary`, `in_ssk`, `verified`.
- Google Photos section: verified album/date ranges with item counts and sizes, plus Takeout `.tgz`
  files on Drive that pass S8.
- **Gate:** user reviews the CSV and marks the rows to delete.

### Phase 6 — Reclaim delete (destructive, manual)
- `cloud-reclaim-delete.sh --approved <file>`: re-verifies each row, deletes to Trash/Recycle Bin, logs every deletion.
  This covers Drive files (including processed Takeout archives) and OneDrive.
- **Google Photos:** the user deletes the approved album/date ranges in the Photos web UI (no API
  for this). They go to Photos Trash for 60 days.
- **Gate:** cloud quota reduced as expected; the deleted files are still present in both local copies.
- Emptying Trash/Recycle Bin is left to the user, after a grace period they choose.

### Rollback
- Phases 0–5 are additive; remove the Flux app and systemd units to undo.
- Phase 6: restore from Drive Trash / OneDrive Recycle Bin / Photos Trash within the grace period, or re-upload from the local copies.

### References
- Google Photos Library API change (2025-03-31) and its effect on rclone: [rclone forum](https://forum.rclone.org/t/google-photos-no-longer-allowing-rclone-access-to-all-photos-any-workarounds-why-not-add-this-feature-to-gphotosdl/54310), [TrueNAS docs](https://www.truenas.com/docs/scale/25.10/scaletutorials/dataprotection/cloudsynctasks/addgooglephotoscloudsynctask/)
- Takeout scheduled exports: [Google help](https://support.google.com/accounts/answer/3024190), [9to5Google, June 2026](https://9to5google.com/2026/06/01/google-photos-schedule-export/)
