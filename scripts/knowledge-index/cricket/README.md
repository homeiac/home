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
No worker, HTTP route, publication, or live inference is enabled by this PR.
