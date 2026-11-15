# I Tried to Stop Paying Google for Storage. My Photos Were 4× Bigger Than My Bill Said.

**Date:** 2026-11-15
**Tags:** google-photos, google-drive, onedrive, takeout, rclone, zfs, k3s, homelab, backup, self-hosting

> My Google account said 89 GB of 100 GB used and nagged me to upgrade. The plan sounded simple: copy
> everything to the homelab, keep two copies, delete from Google, downgrade. A day later I had learned
> that my Photos library is 306 GB (not 70), that downloading it can take down a Kubernetes node whose
> database lives on a *different* disk, and that the cheapest storage upgrade is understanding what
> Google actually bills you for.

## TL;DR

- **"Storage used" ≠ "what you have."** Google said Photos used **70.5 GB**. The Takeout export was
  **306 GB**. Photos uploaded in "High quality" before June 2021 never counted against quota, but they
  are still yours and still exported. Deleting them frees **nothing**.
- **Only ~70 GB of Photos is worth deleting** from Google, and that's exactly the part that needs two
  local copies first. So my second copy (a 238 GB USB SSD) holds Drive, OneDrive and *only* the Photos
  that count against quota, picked automatically from Takeout's metadata.
- **There is no API for your existing Google Photos library anymore** (since March 2025). It's Google
  Takeout or nothing. I download it with a browser that runs *inside* the homelab, so 306 GB never
  touches my laptop.
- **Eight parallel downloads to one USB disk took down a K3s node** whose etcd sits on NVMe. Two
  settings caused it; both are one-liners (below).
- **Status, honestly:** Drive and OneDrive are backed up in three places, nightly. Photos is
  downloading. I have **not** deleted anything from Google yet, and I won't until the numbers check out.

## The setup (aliases)

| Alias | What it is |
|---|---|
| `<backup-host>` | Proxmox host with two pools: internal NVMe (`<fast-pool>`) and a USB HDD (`<usb-pool>`) |
| `<k8s-vm>` | K3s VM on that host. Root disk (K3s, etcd) on `<fast-pool>`; a second disk on `<usb-pool>` holds the SMB share |
| `<smb-share>` | Samba in K3s, browseable from any laptop. **Primary copy.** |
| `<usb-ssd>` | 238 GB exFAT USB SSD. **Second copy**, mirrored daily, unplug-able |
| `<old-hdd>` | An old 2.5 TB USB HDD with bad sectors. **Third copy** (Drive + OneDrive only), re-read and verified after every run |

Everything is scripted and committed; the step-by-step build is in the companion guide:
[Delete From the Cloud Without Fear](2026-11-15-taking-my-files-back-from-google-and-onedrive.md).

## Part 1 — Measure before you design anything

My bill said "Google: 89 GB." The breakdown said:

| | Size |
|---|---|
| Google Photos | 70.5 GB |
| Drive + Gmail + other | 19 GB (Drive itself: 9.2 GB) |
| OneDrive (free plan) | 3.9 of 5 GB |

So Drive — the thing everyone writes rclone tutorials about — was 10% of the problem. Photos was the
problem. Had I not measured, I'd have built a lovely Drive pipeline and freed 8 GB.

## Part 2 — Drive and OneDrive: the "easy" part (it wasn't)

A K8s CronJob runs `rclone copy` (never `sync` — nothing in the backup is ever deleted because it
vanished upstream) into the SMB share every night. Changed files keep their old version in
`.versions/<date>/`. The surprises:

1. **23,650 files, 7.8 GB, 23 files per minute.** Google Drive's API is slow with small files and
   my Drive had an old code checkout in it. 4 parallel transfers would have taken 17 hours. 16
   transfers plus a shorter API pacer: **185 files/minute**, done in about 2 hours.
2. **Two Google Docs had 700–970 character names** (I'd apparently saved chat prompts as
   titles). Linux allows 255 bytes per file name. rclone fails them every night until you rename them.
3. **rclone's shared Google OAuth client is being retired in 2026.** You need your own: a Google Cloud
   project, Drive API, consent screen, Desktop OAuth client. Two traps: leave the app in **"Testing"**
   and Google expires the sign-in every **7 days** (your nightly backup silently dies weekly); and
   **"Publish app" stays greyed out** until the branding page has a home page + privacy link *and*
   their domain is listed as authorized.
4. **OneDrive's interactive setup loops forever** on some personal accounts ("ObjectHandle is
   Invalid") because it picks the **Personal Vault**, which the API can't open. Ask Microsoft Graph
   for `/me/drive` instead and set the drive ID yourself.
5. **OneNote notebooks are silently skipped.** 0.7 GB of my OneDrive. `--onedrive-expose-onenote-files`
   downloads them as real `.one` files.

## Part 3 — Google Photos: there is no API anymore

Since **2025-03-31** the Google Photos Library API only shows apps the photos **they uploaded**.
rclone's `googlephotos` backend, and every other tool, can't read your existing library. The only
complete export is **Google Takeout** — which now runs on a schedule (every 2 months for a year,
"only new and updated items" after the first).

Takeout can deliver into Drive or OneDrive, but that costs cloud quota you don't have (that's why you're
here). The alternative is **download links** — which normally means your laptop downloads 300 GB.

**The trick: a browser that lives in the homelab.** A Firefox container (`linuxserver/firefox`) in
K3s, with its Downloads folder mounted on the backup disk. I open it in a tab, sign in to Google once,
click the links; the bytes go Google → homelab disk. The laptop only shows pixels. The browser profile
(cookies) lives on the host, outside the share, so a pod restart keeps the sign-in — and, it turned
out, the download list.

### The 306 GB surprise

The export summary: **306 GB, 8 files.** Google had been showing me 70.5 GB for Photos.

Most likely explanation: before June 2021, "High quality" uploads were free and unlimited, and they
**still don't count** against quota — but Takeout exports them. (Some older Pixel phones uploaded originals for
free too.) Consequences:

- My primary backup disk had to grow from 200 GB to 600 GB (online, a few seconds, scripted).
- My 238 GB USB SSD can't hold a full second copy.
- **Deleting old photos from Google would free nothing.** Only the ~70 GB that counts is worth
  deleting — so that's what the second copy holds.

### Picking "the 70 GB" automatically

Every photo in a Takeout archive has a JSON sidecar with `creationTime` — when it was **uploaded**.
Anything uploaded on or after 2021-06-01 counts against quota. A small script walks the extracted
library, pairs files with sidecars (Takeout truncates sidecar names, numbers duplicates as `IMG(1).jpg`
↔ `IMG.jpg.supplemental-metadata(1).json`, and shares sidecars with `-edited` copies), skips album
duplicates (Takeout puts the same photo in "Photos from 2023" *and* every album), and hands the list
to `rclone copy --files-from`. Files it can't date are **included** — too much beats too little.

## Part 4 — How 8 downloads took down a Kubernetes node

I clicked Download on all 8 parts. 25–37 MB/s, beautiful. Thirty minutes later the K3s node went
`NotReady`, Kubernetes evicted every pod on it after 5 minutes, and the downloads died.

"The USB disk can't do 25 MB/s?" Of course it can. That wasn't it. Two things were:

**1. ZFS wrote everything twice.** The share is ext4 inside the VM on a ZFS volume. ext4 flushes its
journal every few seconds; with ZFS's default `logbias=latency`, no separate log device and the
volume's small 16K blocks, each flush made ZFS copy the data into its intent log *on the same USB
disk*, then write it again into its final place.
Eight streams turned that into a seek storm. The host log said it plainly:

```
INFO: task txg_sync blocked for more than 122 seconds.
 zil_commit_impl ... zvol_write
```

Fix: `zfs set logbias=throughput <pool>/<zvol>` — large sync writes go straight to their final place.
Same durability, live, reversible.

**2. One "outbox" for every disk.** K3s and etcd are on the NVMe disk — so why did they stall? Inside
the VM, Linux keeps written-but-not-yet-flushed data in memory: about 1.5 GB here, **shared by all
disks**. The downloads filled it with data for the slow USB disk. When it's full, Linux makes *every*
writer wait — including etcd, whose writes go to NVMe. etcd expects milliseconds, got seconds, and
K3s declared the node dead.

Fix: limit the USB disk to 20% of that budget (`/sys/block/<dev>/bdi/max_ratio`, persisted with a
udev rule matched on the filesystem label).

**Bonus fix:** the browser pod now tolerates a NotReady node for an hour instead of 5 minutes, and has
no CPU/memory limits.

**And the downloads weren't lost.** Firefox kept the `.part` files on the backup disk and resumes a
retried download from them — but first it re-reads each partial file (you'll see a long burst of disk
*reads*, and the progress numbers freeze, sometimes for half an hour with several big partials). Only
then does it continue downloading. With both fixes in, all 7 remaining parts are running again; I'll
update this post with how that went.

## Part 5 — Three copies, and the boring rules that make deleting safe

| Copy | Where | How |
|---|---|---|
| 1 | SMB share on ZFS | nightly `rclone copy` from Drive/OneDrive; Photos unpacked from Takeout every 2 h |
| 2 | USB SSD (exFAT) | daily: ZFS snapshot → read-only clone → `rclone copy`. Drive, OneDrive, Photos-that-count |
| 3 | Old USB HDD | same, Drive + OneDrive only, **every file re-read and compared** (it has bad sectors) |

The mirror never mounts the share over the network and never needs a password: it snapshots the ZFS
volume, mounts a **read-only clone**, copies, and destroys the clone. Point-in-time, can't modify the
primary. The USB disks are found by **serial number**, never `/dev/sdX`.

The rules:

1. `copy`, never `sync`. A file deleted in the cloud stays in the backup.
2. Changed files keep their old version.
3. Nothing is deleted from Google until it is in **two** local copies, verified by hash.
4. Every step is a script in git, re-runnable, with a log.

## What I'd tell you before you start

1. **Measure Google's breakdown first.** Then export Photos and look at the *real* size.
2. **Old "High quality" photos are free.** Back them up, but don't delete them to save space — it won't.
3. **Your own OAuth client, in production.** Not "Testing", or the backup dies every week.
4. **Never download big things in parallel onto one spinning disk behind ZFS + a VM** without
   `logbias=throughput` and a cap on that disk's dirty pages. Your Kubernetes control plane will feel it.
5. **Firefox resumes.** Don't delete the `.part` files after a failure.
6. **Name your secrets' escape hatch.** All of this runs on keys and tokens; I wrote a separate post on
   making sure a dead laptop can't lock you out:
   [The Key That Unlocks Everything](2026-11-15-the-key-that-unlocks-everything.md).

## What's left

- Finish the Photos download, unpack, and let the second copy pick up the ~70 GB.
- Verify counts and hashes, then delete the counting photos and the biggest Drive files from Google.
- Then — and only then — see whether everything fits in the free 15 GB and the subscription can go.

I'll update this post with the final numbers.

---

*Companion posts:* the full build guide
([Delete From the Cloud Without Fear](2026-11-15-taking-my-files-back-from-google-and-onedrive.md)),
the K3s outage the same weekend
([My K3s Cluster Restarted 1,200 Times](2026-11-15-k3s-restart-loop-ipv6-loopback.md)).
