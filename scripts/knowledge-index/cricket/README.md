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
