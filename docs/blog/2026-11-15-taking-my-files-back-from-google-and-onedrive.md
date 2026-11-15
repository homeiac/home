# Delete From the Cloud Without Fear: Backing Up Google Drive, Google Photos and OneDrive to Your Homelab (2026 Guide)

*"Your storage is almost full." Instead of paying for the next tier, I pulled everything home, proved the copies were good, and only then deleted from the cloud. Here's the exact, scripted, step-by-step way to do it, including the 2025 Google Photos API change that breaks every tutorial you'll find.*

> **Status:** living guide. Steps marked ✅ are built and verified; 🚧 steps land before this guide is final.
> Everything here is a committed script or a GitOps manifest. Design spec: [`docs/plans/cloud-drive-backup-and-reclaim.md`](../plans/cloud-drive-backup-and-reclaim.md).

---

## TL;DR

1. **Measure first.** My "Google Drive is full" problem was actually a **Google Photos + Gmail** problem. Drive was about 8% of the quota.
2. **rclone can't back up Google Photos anymore.** Since 2025-03-31, the Photos API only exposes photos *the app itself uploaded*. Use **scheduled Google Takeout** instead.
3. **Never `rclone sync` a backup you plan to delete from.** The day after you delete in the cloud, `sync` deletes your only copy. Use `rclone copy`.
4. **Two copies, two disks, matching hashes, an approved list.** Only then delete, and to the Trash first.
5. **Keep your laptop out of the data path.** Do the OAuth sign-in through an SSH tunnel; the data goes cloud → server directly.

---

## Why this is harder than "just run rclone"

Copying files is easy. The hard part is the **delete**. Once you remove a file from Google or Microsoft, your homelab copy is the only one, and every shortcut stops being a shortcut:

| Shortcut | What goes wrong |
|----------|-----------------|
| `rclone sync` nightly | Mirrors your cloud deletions → wipes the backup |
| One copy on one disk | One dead disk = data gone |
| "It finished, so it's fine" | Partial runs, quota errors, skipped files |
| Google Photos via rclone | Since 2025 it only sees photos rclone uploaded |
| Deleting by gut feel | You delete the one folder that didn't copy |

So the design is built around one rule: **you may delete a cloud file only if you can prove it exists, byte-identical, in two independent local copies.**

## What you'll build

```
 Google Photos ──scheduled Takeout (.tgz)──▶ OneDrive / Drive
 Google Drive ─┐
 OneDrive ─────┤  rclone COPY (never sync) — nightly K8s CronJob
               ▼
   PRIMARY   <smb-share>/cloud-backup/{gdrive,onedrive,gphotos}
             browseable from any device · ZFS snapshots for history
               │  host timer: mount share READ-ONLY → rclone copy
               ▼
   SECONDARY <usb-ssd> (exFAT) — separate physical disk, readable on any laptop
               │
               ▼
   RECLAIM   report → verify in BOTH copies → you approve a list → delete to Trash
```

### Aliases used in this guide

Replace these with your own values. All the scripts read them from environment variables, with defaults in `scripts/backup/cloud-backup-common.sh`.

| Alias | Meaning | Env var |
|-------|---------|---------|
| `<backup-host>` | Linux box (mine is a Proxmox node) that runs rclone and has the USB SSD | `CB_HOST=root@<backup-host>` |
| `<k8s-node>` | Kubernetes node that hosts the SMB share's storage | (manifest `nodeSelector`) |
| `<smb-share>` | Your SMB share, e.g. `\\nas\secure` | — |
| `<usb-ssd-serial>` | USB serial of the second-copy disk (`lsblk -dno NAME,SERIAL`) | `CB_SSK_SERIAL` |
| `gdrive-backup`, `onedrive` | rclone remote names | `CB_GDRIVE_REMOTE`, `CB_ONEDRIVE_REMOTE` |

### What you need

- A Linux server that stays on (any distro with `bash`, `curl`, `python3`)
- An SMB share with room for everything (or any directory you can browse; the SMB part is optional)
- A second disk for the second copy, ideally a USB SSD
- A browser, once per provider, for sign-in
- Optional: Kubernetes + Flux, if you want the nightly job as GitOps (a systemd timer works too)

---

## Step 1 ✅ Install a pinned, verified rclone

```bash
scripts/backup/cloud-backup-install-rclone.sh
```

Distro packages lag badly: Debian 12 ships rclone **1.60 (2022)**, too old for today's OneDrive API. The script installs a pinned official release and checks it against rclone's published `SHA256SUMS` before installing:

```bash
V=v1.76.0; F=rclone-$V-linux-amd64.deb
curl -fsSLO https://downloads.rclone.org/$V/$F
curl -fsSL https://downloads.rclone.org/$V/SHA256SUMS | grep " $F$" | sha256sum -c -
dpkg -i "$F"
```

Re-running it does nothing if that version is already installed.

## Step 2 ✅ Connect Google Drive

If you already have an rclone Google remote (I had one for Postgres backups, stored as a **SOPS-encrypted** Kubernetes secret), reuse it:

```bash
scripts/backup/cloud-backup-seed-gdrive-config.sh
```

It decrypts the secret on your workstation and **streams** it over SSH into the server's rclone config: no plaintext file on your laptop, nothing printed. It merges by remote section, so other remotes on the server are kept.

No existing remote? Follow Step 3 with `drive` in place of `onedrive`.

> ⚠️ **2026 gotcha:** if rclone prints *"This remote uses rclone's shared Google Drive client_id, which is being retired"*, create your own OAuth client (Google Cloud Console → APIs & Services → enable **Drive API** → OAuth client ID → *Desktop app*) and put `client_id` and `client_secret` in the remote. Otherwise your backups stop working partway through 2026.

## Step 3 ✅ Connect OneDrive without your laptop in the data path

OAuth needs a browser once. The trick: run rclone's config **on the server**, inside an SSH session that tunnels rclone's callback port back to your laptop.

```bash
scripts/backup/cloud-backup-auth-onedrive.sh
# which is essentially:
ssh -t -L 53682:127.0.0.1:53682 root@<backup-host> \
  "rclone config create onedrive onedrive"
```

1. rclone prints a URL → open it in your browser → sign in to Microsoft.
2. Microsoft redirects to `127.0.0.1:53682`. On your laptop that's the tunnel, so the token is delivered **to the server**.
3. Answer rclone's prompts: *OneDrive Personal or Business*, then pick your drive.

Your browser only ever sees the login page. Tokens live only in the server's rclone config: never in git, never on the SMB share.

## Step 4 ✅ Measure before you design anything

```bash
scripts/backup/cloud-backup-measure.sh
```

For each remote it runs `rclone about` (quota) and **one** recursive `rclone lsjson`, and prints:

- total size and file count
- Google-native Docs/Sheets/Slides (they don't use quota, and back up as `.docx`/`.xlsx`/`.pptx` exports)
- size per top-level folder, and the 30 largest files
- a **capacity gate**: does the total fit on *both* the primary and the second disk?

My result, anonymized:

```
Total:   100 GiB
Used:      9.2 GiB    <- Google Drive
Other:    80.2 GiB    <- Google Photos + Gmail (same quota!)
Free:     10.6 GiB

Files with data : ~23k   total  8.25 GB
Google-native   : 114 Docs/Sheets/Slides
```

**Drive wasn't the problem.** Without measuring, I'd have built a careful Drive pipeline that freed 8 GB of an 80 GB problem.

> 💡 A Google `rclone about` shows **Used** (Drive) vs **Other** (Photos + Gmail). Run it before you plan anything.

## Step 5 ✅ Prepare the second-copy disk

```bash
CB_SSK_SERIAL=<usb-ssd-serial> scripts/backup/cloud-backup-format-ssk.sh --yes
```

This step is **destructive**, so the script:

- finds the disk by **USB serial**, never by `/dev/sdX` (which can change between boots)
- refuses if any partition is mounted or belongs to an imported ZFS pool
- writes a fresh GPT with one partition and formats it **exFAT**

**Why exFAT?** If the server is dead, you can plug the disk into any Mac, Windows or Linux laptop. **Not FAT32:** its 4 GB file-size limit rejects videos and Takeout archives.

> 🧯 Mine turned out to be an old Proxmox boot disk. Before wiping it I imported its ZFS pool **read-only** (`zpool import -o readonly=on -N -R /mnt/x <id>`) to check nothing irreplaceable was on it. Do the same with any "spare" disk.

## Step 6 🚧 Google Photos: scheduled Takeout

**Why not rclone?** On **2025-03-31** Google restricted the Photos Library API: apps can only read media **they uploaded**. rclone's `googlephotos` backend, and every other third-party tool, can no longer download your existing library, and old tokens don't keep full access. The Picker API needs you to select items by hand.

**What works:** Google Takeout, which since June 2026 can run on a **schedule**.

1. Go to takeout.google.com → **Deselect all** → tick **Google Photos only** (a Photos-only selection is required for scheduled exports).
2. **Frequency:** *Export every 2 months for 1 year*.
3. **File type and size:** `.tgz`, **50 GB**.
4. **Destination:** *Add to OneDrive* or *Add to Drive*. Pick the one with **free space ≥ your Photos size**. The archives temporarily count against that drive's quota. My Google account had 10.6 GiB free for an ~80 GiB library, so the first full export went to OneDrive.
5. Set a calendar reminder for **11 months from now**: the schedule expires after a year.

The nightly pull (Step 7) picks the archives up like any other file. An **ingest job** then:

- checks each archive (`tar -tzf` completes; size matches the cloud copy)
- extracts it into `cloud-backup/gphotos/`, keeping Takeout's `.json` sidecars (date taken, GPS, description)
- records it in a ledger (`_ingested.tsv`)
- marks the cloud copy of the archive deletable **only after** the extracted files are on the second disk too

> Reports disagree on whether exports after the first are incremental. Check the size of your second export before relying on it.

## Step 7 🚧 The nightly pull: `copy`, never `sync`

A Kubernetes CronJob (Flux-managed) on `<k8s-node>`, writing into the SMB share:

```bash
rclone copy gdrive-backup: /backup/gdrive \
  --backup-dir /backup/.versions/gdrive/$(date +%F) \
  --drive-export-formats docx,xlsx,pptx,svg \
  --fast-list --checksum
```

- **`copy`** only adds or updates. A cloud delete never propagates to your backup.
- **`--backup-dir`** keeps the old version of any file that changed.
- The job writes a status file **only on success**, so a half-finished run never looks finished.

## Step 8 🚧 History: ZFS snapshots

The share's storage gets daily (×14) and monthly (×6) ZFS snapshots with `sanoid`. Ransomware or a fat-fingered `rm -rf` on the share can be rolled back.

## Step 9 🚧 The second copy

A systemd timer on `<backup-host>`:

1. mounts the SMB share **read-only**, so the mirror job can't damage the primary
2. checks the USB disk's serial
3. runs `rclone copy` share → disk, then `rclone check` to confirm they match

## Step 10 🚧 Reclaim: delete only what you can prove you have

```bash
scripts/backup/cloud-reclaim-report.sh      # read-only
# → reclaim-candidates-<date>.csv: path, size, hash, in_primary, in_second_copy, verified
```

Open the CSV and keep the rows you want deleted. Then:

```bash
scripts/backup/cloud-reclaim-delete.sh --approved my-approved-list.csv
```

It re-verifies every row against **both** copies, shows the total, and makes you **type the GB figure** to confirm. Files go to **Drive Trash / OneDrive Recycle Bin**; you empty those yourself, later.

**Google Photos** can't be deleted through the API either. The report gives you verified album and date ranges, and you delete them in the Photos web UI. They sit in Photos Trash for 60 days.

---

## The safety rules (enforced in code, not good intentions)

| # | Rule | Enforcement |
|---|------|-------------|
| 1 | Backups never delete local data because it vanished upstream | `copy` + `--backup-dir`; a test greps for `rclone sync` |
| 2 | The mirror can't modify the primary | read-only SMB mount |
| 3 | Delete only if hash-identical in **both** copies | `rclone check` against both before listing a file |
| 4 | Delete only what you approved | `--approved` list plus typed confirmation |
| 5 | Deletes are recoverable | Trash / Recycle Bin first |
| 6 | Right disk, every time | located by serial, mounted by UUID |
| 7 | Stale backups block deletes | status files older than 48 h → reclaim refuses to run |
| 8 | Takeout archives survive until extracted **and** mirrored | ingest ledger + second-copy check |

## Mistakes I made so you don't have to

- **Planned around the wrong service.** Measure first (Step 4).
- **Trusted an API that changed.** Google Photos via rclone stopped working in 2025. Takeout is the way now.
- **Nearly used `sync`.** It's the default in most tutorials and the worst choice when you plan to delete.
- **Gave a laptop network adapter a static IP with no gateway.** macOS made that adapter primary and the whole laptop lost internet. If you hand-configure a second interface, check `netstat -rn` afterwards.

## FAQ

**Why not Google Drive for Desktop or the OneDrive app on a laptop?** That puts the laptop in the data path and ties the backup to it being on, synced, and not low on disk.

**Is two copies in one house enough?** Not against fire or theft. Add an offsite third copy for anything irreplaceable, e.g. a disk at a friend's place or a cold-storage bucket.

**What about Gmail?** Same quota, same Takeout. Select *Mail* in a separate export. It isn't covered here yet.

---

*All scripts: [`scripts/backup/`](../../scripts/backup/) · Design: [`docs/plans/cloud-drive-backup-and-reclaim.md`](../plans/cloud-drive-backup-and-reclaim.md)*

### Sources

- [rclone forum: Google Photos no longer allowing rclone access](https://forum.rclone.org/t/google-photos-no-longer-allowing-rclone-access-to-all-photos-any-workarounds-why-not-add-this-feature-to-gphotosdl/54310)
- [TrueNAS: Google Photos cloud sync limitations](https://www.truenas.com/docs/scale/25.10/scaletutorials/dataprotection/cloudsynctasks/addgooglephotoscloudsynctask/)
- [Google: How to download your Google data (Takeout, scheduled exports)](https://support.google.com/accounts/answer/3024190)
- [9to5Google: Google Photos scheduled exports (June 2026)](https://9to5google.com/2026/06/01/google-photos-schedule-export/)
- [rclone: Making your own Google Drive client_id](https://rclone.org/drive/#making-your-own-client-id)
