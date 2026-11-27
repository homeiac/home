# One-model CPU-thread results

**Status: incomplete / stopped.**

One extra Mac CPU process; baseline Metal and all admitted production workers stay running. Same 122 photos, six excluded warm-up photos, reverse order on the second pass. Earlier process-sweep environment variables did not verify the detector thread count; this phase explicitly controls the pinned Ultralytics selector.

| Threads | Pass | Photos/min | Mean seconds/photo | TP / FP | Valid |
|---:|---|---:|---:|---|---|

Failure retained: Mac sustained memory pressure guard. Previous extra policy was restored; no completed winner is claimed.

Observed whole-Mac CPU range: 0.0–23.0%; includes other applications. System swap first/last: 18.87/18.87 GiB.

Two repetitions are not a confidence interval. Zero false positives on 13 selected controls does not establish library-wide precision.

Session `1127060523`; code `1abfe8de82ab847790f8d4f21ed4b8402e0ed0e6`; sample SHA-256 `3beae47139538015c9968b5d39a38b5bfb3bdb1f9b740370406d6ca73ee57ca2`.

[Protocol](2026-11-26-cpu-threads.md) · [Journal](2026-11-26-cpu-threads.jsonl)
