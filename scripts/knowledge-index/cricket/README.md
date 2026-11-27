# Cricket highlight ledger

PR 1 of [the implementation plan](../../../../docs/plans/adil-cricket-highlights.md), tracked in [#250](https://github.com/homeiac/home/issues/250).

The SQLite ledger stores album-scoped source assets, immutable model proposals,
stable events, user revisions, and future job checkpoints. Effective results
overlay user edits field by field. Null clears a person explicitly. Confirmation
freezes all current event fields; dismiss/restore and undo retain history.
Model writes increment the event revision so an open editor cannot confirm stale
content. All write operations use short immediate transactions and validate the
complete resulting event before committing. Every query includes the owner scope.

Run from `scripts/knowledge-index`:

```sh
python3 -m unittest cricket.test_ledger
python3 -m cricket init /private/state/cricket.sqlite3
python3 -m cricket backup /private/state/cricket.sqlite3 /private/backups/cricket-001.sqlite3
python3 -m cricket restore /private/backups/cricket-001.sqlite3 /private/state/cricket-restored.sqlite3
```

Restore deliberately writes a new path. Stop/drain the consuming service before
switching it to the restored file; keep the old ledger until verification completes.
Backups use SQLite's online backup API and include committed WAL changes. Schema
migration backs up an existing ledger first. Database and backup files are private
(0600); keep the parent state directory private too. Do not use a network share for
the live SQLite file or run multiple schema upgrades concurrently.

Identity assumptions never change native face recognition. A changed source
fingerprint is rejected until the original/event mapping is explicitly reconciled.
No worker, publication, or live inference is enabled by this module.

## Playback and correction API

Enable the existing `photo-enrich.py serve` command with both `--cricket-ledger`
and `--cricket-owner`. The latter is the fixed owner for this private instance;
query parameters and JSON cannot change it. The existing review app has no user
login: retain its private gateway access control. Host, same-origin and CSRF checks
apply to cricket too. Without these flags all cricket API routes remain disabled.

GET routes under `/api/cricket/`: `albums`, `assets?album=...`,
`events?album=...`, `event?id=...`, and `media?album=...&asset=...`.
Media uses bounded file streaming and single HTTP byte ranges for seeking.
POST `create` takes album, asset, and complete event data. POST `revise` takes
id, expected revision, and either a patch or action (accept/dismiss/restore/undo).
A stale editor receives HTTP 409. Reads and streaming bypass the photo database
lock; each cricket read uses a separate short SQLite snapshot.

Run API tests with `python3 -m unittest cricket.test_api`; they bind loopback.

## Correction UI

The enabled review application links to `/cricket`. Pass `--cricket-people` with
a private JSON mapping of person IDs to display names from the same owner.
The user chooses a name, edits labels and times, or dismisses/undoes a suggestion.
Unknown identities remain explicitly unclear. Failed saves keep the editor open.
Filters for batting outcomes and bowling wickets use the album's default person.

Browser verification uses generated media in a new private temporary directory:

```sh
python3 -m cricket.demo --state /private/tmp/cricket-ui-demo
node cricket/check_ui.cjs /private/tmp/cricket-ui-demo/ready.json /private/tmp/cricket-ui.png
```

The check requires Playwright and Chrome and launches a fresh headless profile.
Set `PLAYWRIGHT_MODULE` to an isolated installation when not on Node's module path.
Use a new state directory for each check so the starting fixture is unchanged.

## Inventory and role identity rules

`inspect_album.py` reads all matching accessible albums, follows metadata-search
pagination, and writes a private inventory only when requested. It uses the v3
album-user owner field and paginated search; see the
[Immich v3 migration notes](https://immich.app/blog/v3-migration).
`inspect_runtime.py` checks the selected host from the inventory, matches original
sizes, and reuses read-only audio-story results by canonical or alias path.

`python3 -m cricket.importer --inventory PRIVATE.json --runtime PRIVATE.json
--ledger PRIVATE.sqlite3 --people PEOPLE.json --dry-run` resolves the named album
and unique person before writing. Remove `--dry-run` to import and enqueue.
Repeat imports preserve jobs and corrections. Role classification applies the
default person only to a featured batter; bowling identity requires separate
matching evidence. Visual role extraction is connected with the evidence/model
worker in the next PRs, rather than guessing roles from album membership.

## Timed evidence

`python3 -m cricket.prepare --ledger PRIVATE.sqlite3 --runtime PRIVATE.json
--folder PRIVATE_CACHE --host INVENTORY_HOST --workers 4 --limit 32` selects
duration-stratified video inputs and prepares low-priority, single-threaded frames
on the media host. Thirty-second windows overlap by ten seconds; every window
has eight timestamped frames. Cached audio-story segments retain source-relative
times. Missing audio is explicit and never prevents visual analysis.

Preparation caches include source fingerprint, extraction version and audio
evidence. Completed assets survive restarts; failed assets can be retried. The
pilot does not mutate original media or the existing backfill. `--limit 0`
prepares the full chosen media kind; do that only after the live capacity trials.

## Suggestions and descending live trials

The analyzer accepts likely fours, sixes, unclear boundaries, dismissals and
run-outs. Run-up timestamps get ten seconds of pre-roll; release-only observations
get an approximate fifteen-second fallback. End times include five seconds of
aftermath and all bounds are clamped to the original. A separate portrait match
can suggest bowling identity; only featured batting uses the album assumption.

`discover_backends` records reachable existing Mac/RTX/CPU endpoints and their
upper serving bounds in a private, initially disabled policy. `reference` reads
the selected person's existing portrait. `trial` runs a fixed private set without
publishing, saves hashes before requests, and records every result. Begin at each
backend's measured maximum, then descend. Use `--match PREVIOUS/inputs.json` for
later trials, including reverse-order confirmation, so newly prepared files do
not change the comparison. Never count cached answers as inference throughput.

See [the experiment journal](../../../../docs/experiments/cricket/science-journal.md)
for acceptance criteria and aggregate results. Raw outputs, portraits, evidence
and policy credentials remain outside Git.
