# Cricket highlights operations

The private review page is `https://photos.app.home.panderosystems.com/cricket`.
Suggestions are best effort. Corrections and dismissals are authoritative and
survive reanalysis. Original photos and videos are never modified.

## Durable locations

- Host: pumped-piglet, resolved from `proxmox/inventory.txt` before SSH.
- State: `/local-3TB-backup/photo-enrichment/cricket`.
- Authority: `ledger.sqlite3`; cached frames: `evidence`; model checkpoints:
  `worker/answers`; effective snapshots: `worker/effective`.
- Runtime: `cricket-highlights.service`; policy: `policy.json` under state.
- Private UI uses the existing `photo-enrichment-gui.service` and Traefik route.

Do not copy a laptop bootstrap ledger over this directory after deployment.
The deployer refuses to overwrite an existing ledger or operator policy. Inspect
the current deployed release before each rollout; source hashes prevent racing
another deployment. Resolve any three-way merge conflict before applying.

## Live controls

From `scripts/knowledge-index`, set `CRICKET_HOST` to the inventory-confirmed SSH
target. The following reusable commands operate on the host authority:

```bash
python3 -m cricket.remote --host "$CRICKET_HOST" status
python3 -m cricket.remote --host "$CRICKET_HOST" pause
python3 -m cricket.remote --host "$CRICKET_HOST" workers --backend mac --workers 2
python3 -m cricket.remote --host "$CRICKET_HOST" workers --backend rtx --workers 0
python3 -m cricket.remote --host "$CRICKET_HOST" resume
python3 -m cricket.remote --host "$CRICKET_HOST" retry
```

Worker counts reload every two seconds. A lower count or pause drains in-flight
requests; it does not discard answers. Host memory below 512 MiB pauses dispatch
for at least 60 seconds. Do not change baseline caption/audio services to improve
a cricket benchmark. Start trials at measured serving bounds and decrease; keep
input hashes, errors and unsuccessful settings in the experiment journal.

Jobs have renewable leases and three attempts. A crashed worker's stale lease
cannot commit over its successor. Successful window answers are reused after a
retry. `retry` resets only terminal errors for the selected analysis version;
it never resets completed work or corrections. A new analysis version creates
new jobs and reconciles onto durable event IDs.

## Backup, restore and rollback

The `cricket.ops` CLI on the host supports `backup --path BACKUP_FILE` and
`restore --path BACKUP_FILE` with `--ledger LEDGER_FILE`. Backups use SQLite's
online backup API. Restore requires a new destination and refuses to replace an
existing authority. Inspect a restored copy before any operator-directed switch.

Every UI rollout retains the previous release, service unit, and a ledger backup
under `/opt/photo-enrichment/backups/cricket-*`. Failed UI health checks restore
the prior code and unit automatically while retaining all current corrections.
Pausing analysis leaves the review UI and saved corrections available. A feature
rollback must restore code/configuration only; never restore an older ledger
over corrections created since the backup.

Private inventories, portraits, transcripts, frame caches, source IDs, and runtime
policies stay out of Git. Aggregate status contains no media paths or names.
