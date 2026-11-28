# Cricket highlights operations

The private review page is `https://photos.app.home.panderosystems.com/cricket`.
Suggestions are best effort. Corrections and dismissals are authoritative and
survive reanalysis. Original photos and videos are never modified.

**Play whole video**, directly below a card's player, switches to the complete
original in the same player. It starts at the beginning and removes the highlight
stopping point. **Back to highlight** restores the saved interval without editing
its boundaries. Use the complete aftermath to decide whether an appeal succeeded.

**Attempted run-out — not out** is a separate result and saved filter. It remains
available under batting/bowling, but is excluded from Batter out and Bowling
wickets. A spectator shouting “out” alone no longer creates a dismissal; the
model must consider the aftermath, including the batter continuing to play.

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

The exporter also needs the ledger directory in its systemd `ReadWritePaths`
allowance for SQLite WAL coordination files, even with a read-only SQL connection.
The deployer installs the scoped `cricket-ledger.conf` override and backs it up.

## Live controls

Follow the [shared-indexer tuning playbook](shared-indexer-tuning.md) before any
worker increase or new reanalysis/frame-upload pass. Inventory knowledge indexing,
life-stage, Immich ML and any active dog-identification workers on the same
resources. The four-worker setting below is historical evidence for its observed
workload mix, not an exclusive reservation of four shared inference slots.

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
input hashes, errors, per-peer progress and unsuccessful settings in the experiment
journal. A live service or healthy endpoint is insufficient: every affected
backlogged indexer must continue committing useful work within its trial budget.

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

Bowling filters include unidentified bowling candidates, visibly labeled as
unclear, so they can be corrected without assuming every bowler is Adil. A saved
correction to another named person removes the moment from Adil's filters.

## Clip downloads

Use **Export clip** on a video moment to create an MP4 for its current corrected
interval. The download retains audio and stores provenance to the original,
source fingerprint, and effective revision. A timing correction creates a new
export; stale revision URLs are rejected. Two low-priority encodes may run at
once. Derived files live under `exports` and are not imported into Immich or
analyzed as new originals. Export errors leave the saved correction intact.

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

## OpenLABEL publication adapter

`cricket.openlabel` imports effective cricket corrections and native face
checkpoints into the existing life-stage ASAM OpenLABEL 1.0.0 contract. It calls
the existing `openlabel_album.bind_face`, `validate_scenes`, and `persist`
implementation; it does not create a parallel annotation table. The shared module
must come from the [life-stage implementation](https://github.com/homeiac/home/blob/codex/photo-memory-album-231/scripts/knowledge-index/memory-acceptance/openlabel_album.py).
Supply its directory explicitly and install its `jsonschema` dependency in the
existing runtime; PostgreSQL publication also uses the existing `psycopg` runtime.

Validate a private snapshot first, from `scripts/knowledge-index`:

```bash
python3 -m cricket.openlabel \
  --ledger "$CRICKET_LEDGER" --evidence "$CRICKET_EVIDENCE" \
  --shared-module "$LIFE_STAGE_OPENLABEL_MODULE" \
  --schema "$OPENLABEL_SCHEMA" --output "$CRICKET_OPENLABEL_OUTPUT"
```

The ledger is opened read-only. Only current album members with native-frame
checkpoints are included in this snapshot. Every returned native face is retained,
including unnamed/unassigned faces. Checkpoint absence is not proof of no faces.
Incomplete detection stays explicit. A missing legacy frame dimension can be
recovered from the exact checksum-matched local JPEG without another upload.

`frames` indexes ordered samples; `frame_properties.timestamp` carries exact
original-video seconds. Each sample names its Immich frame asset and oriented
image dimensions. Face boxes use OpenLABEL center-x/center-y/width/height pixels.
Native face ID and person ID remain separate; OpenLABEL occurrence UUIDs never
substitute for native IDs. Action/outcome codes and their definitions are versioned
in [vocabulary.py](../../scripts/knowledge-index/cricket/vocabulary.py).

Human overrides, effective event revision, review state, exact source times, age
context and evidence travel with the scene. Dismissed or superseded actions are
removed from the next scene revision while their face detections remain. An actor
relation requires a current unambiguous localized face; the album batting rule
alone stays a separate editable person assertion. Unassociated faces retain an
explicit `action_withheld` reason.

After validation and publication readiness checks, the same command's `--publish`
flag uses the existing private libpq configuration and shared PostgreSQL
`openlabel_album_scene` revision writer. It refuses to replace another producer's
scene; combine such annotations explicitly before publication. Changed scenes
append revisions and identical scenes use the shared writer's existing digest
behavior. No SQLite or frame JSON file becomes a second canonical scene store.

The current change supplies the adapter and tests. It does not install a new
publication timer, switch the live UI to PostgreSQL, or claim a completed face
backfill. The existing SQLite event API remains the correction/import surface.

For integration checks set `CRICKET_OPENLABEL_SHARED_MODULE` and
`CRICKET_OPENLABEL_SCHEMA`, then run `python3 -m pytest cricket/test_openlabel.py`.
Without those paths, tests requiring the external shared implementation are
explicitly skipped. Use a pinned 1.0.0 schema; the shared validator rejects 0.3.0.
The local validation used the VCD project's
[OpenLABEL schema source](https://github.com/Vicomtech/video-content-description-VCD/blob/master/vcd/schema.py)
after the ASAM schema host timed out. The extracted schema SHA-256 is
`201c360d3807c6108fe2b23634ed658caf43dcc9cc63068f91ebe99303b47011`.
