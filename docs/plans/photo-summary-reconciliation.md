# Reconcile saved photo and video summaries

Use Luna to combine existing local-GPU and Luna text with saved metadata. Preserve
both originals and write a separate `reconciled_summary` column. No image/video
uploads, new face inference, knowledge graph, or changes to Immich descriptions.

1. Seed exact `(path, size_bytes)` matches with two successful captions. Exclude
   album copies using the existing inventory rule. Freeze source text, model IDs,
   dates, saved places, human-confirmed names and group annotations.
2. Ask Luna to preserve supported detail, use explicit human annotations to resolve
   names/events, and flag unresolved contradictions for visual review. Agreement
   between models is not independent confirmation. Do not infer kinship or jobs.
3. Store each input fingerprint, result, unresolved conflicts, review flag, model,
   prompt version and reported usage in a separate SQLite ledger table on Piglet.
   Publish private Parquet with `local_summary`, `luna_summary`, and
   `reconciled_summary` side by side. Originals remain unchanged.
4. First run ten items with a $2 API-equivalent estimate cap. Inspect saved results
   and verify idempotent publication before increasing work.
5. Scale the shared queue across still-fawn and the Mac. Claims are transactional,
   fenced by batch ID, and bounded by global and per-runner concurrency. Other nodes
   may join after checking capacity and their authenticated Luna runtime; do not
   copy sign-in credentials to new machines.

The existing $250 campaign estimate includes the original caption campaign and
reconciliation. Reserve $1 per active request and settle with reported token usage.
Unknown outcomes retain their reservation, pause new work and are not retried
automatically. Estimates are accounting proxies, not an Enterprise invoice.

Rerunning the same seed does not resubmit identical inputs. Changed captions or
metadata create a new fingerprint and preserve history. The published file shows
the newest seeded revision for each file, with a null result while pending; it must
not silently fall back to an older reconciliation. Seeding is explicit, so the
data is a recorded snapshot rather than a live claim about later review edits.

The original Luna timer and Git-selected scheduling policy are reused. Caption
mode remains available. Reconciliation policy admits only configured runners;
the ledger enforces its own limits even if a runner sends a larger request.

## Pilot result — November 22, 2026

Ten of ten pairs produced separate reconciled summaries, with ten unique files,
no failed requests and three visual-review flags. Estimated incremental usage was
$0.011471. A sample review found explicit uncertainty about a disputed pouring
action and an unconfirmed full person name, rather than silently promoting them.
At that sample rate, 1,000 pairs would cost about $1.15; this is a projection.

The next policy allows 20 requests each on still-fawn and the Mac, with 40 global
slots. The combined campaign ceiling remains $250, including the earlier captions.
Pve, chief-horse and fun-bedbug had no existing Luna CLI/sign-in; pve and chief-horse
also had less than 1 GiB available at inspection. No credentials were copied.
