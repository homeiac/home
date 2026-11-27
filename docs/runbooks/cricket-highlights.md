# Cricket highlights operations

The private review page is `https://photos.app.home.panderosystems.com/cricket`.
Suggestions are best effort. Corrections and dismissals are authoritative and
survive reanalysis. Original photos and videos are never modified.

## Durable locations

- Host: pumped-piglet, resolved from `proxmox/inventory.txt` before SSH.
- State: `/local-3TB-backup/photo-enrichment/cricket`.
- Authority: `/var/lib/photo-enrichment/cricket/ledger.sqlite3` on the host NVMe
  filesystem, linked from the stable state directory; cached frames: `evidence`; model checkpoints:
  `worker/answers`; effective snapshots: `worker/effective`.
- Runtime: `cricket-highlights-ssd.service`; policy: `policy.json` under state.
  The original ZFS worker unit is disabled. `worker` links to the NVMe checkpoint directory.
- Private UI uses the existing `photo-enrichment-gui.service` and Traefik route.

Do not copy a laptop bootstrap ledger over this directory after deployment.
The deployer refuses to overwrite an existing ledger or operator policy. Inspect
the current deployed release before each rollout; source hashes prevent racing
another deployment. Resolve any three-way merge conflict before applying.

The SSD cutover retains online ledger backups, old worker caches, and old units.
`cricket.inspect_worker --host "$CRICKET_HOST"` reports kernel waits and storage
health. `cricket.move_ledger` is a one-time, guarded migration for the observed ZFS
commit stall, not a general retry command. Export opens the ledger read-only and
does not perform migrations. Never reactivate the original worker alongside the
SSD worker or restore the old ZFS ledger over newer corrections.

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
python3 -m cricket.remote --host "$CRICKET_HOST" scope --scope-file /private/path/pilot.json
python3 -m cricket.remote --host "$CRICKET_HOST" scope
```

Worker counts reload every two seconds. A lower count or pause drains in-flight
requests; it does not discard answers. Host memory below 512 MiB pauses dispatch
for at least 60 seconds. Do not change baseline caption/audio services to improve
a cricket benchmark. Start trials at measured serving bounds and decrease; keep
input hashes, errors and unsuccessful settings in the experiment journal.

`scope --scope-file` restricts new claims to a private JSON array of source IDs;
`scope` without the file allows the imported album. Neither command resets jobs
or corrections. Videos are dispatched before photos. The current measured setting
is four Mac requests and zero RTX requests; the latter failed its recovery probe.

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

## Corrected search and publication

The cricket page supports saved filter URLs (`?filter=four`, `?filter=six`,
`?filter=batting_out`, `?filter=bowling_wicket`), text search, and exact-moment
links. All filters read effective corrections immediately. Cards load in pages
of 60 and defer original-video loading until playback.

The existing photo analytical export now publishes `cricket_highlights` alongside
the photo search tables. It contains corrected actor/role/result, clip bounds,
review status, category memberships, searchable text, and links to the moment
and original. Each generation replaces the entire table, so dismissed, removed,
or recategorized moments cannot linger in append-only output. Export timing and
failures use the existing snapshot manifest and retry timer. `cricket.remote
status` reports the publication timestamp and row count.

Example query through the existing analytical query command:

```sql
SELECT person, role, outcome, start_seconds, end_seconds, highlight_url
FROM cricket_highlights
WHERE list_contains(categories, 'bowling_wicket');
```

The worker also exports aggregate Prometheus metrics in
`/var/lib/prometheus/node-exporter/cricket_highlights.prom`: heartbeat, queued /
running / complete / error jobs, desired and active workers, completed source
minutes, and memory-pressure pause state. Labels contain no names or media IDs.
