# One-model CPU-thread results

**Status: incomplete / stopped.**

Warning-pressure policy: **observe**. Critical pressure remains a stop condition. Earlier journal sessions retained: 1.

One extra Mac CPU process; baseline Metal and all admitted production workers stay running. Same 122 photos, six excluded warm-up photos, reverse order on the second pass. Earlier process-sweep environment variables did not verify the detector thread count; this phase explicitly controls the pinned Ultralytics selector.

| Threads | Pass | Photos/min | Mean seconds/photo | TP / FP | Valid |
|---:|---|---:|---:|---|---|
| 2 | a | 83.9 | 0.255 | 9 / 0 | True |
| 4 | a | 66.0 | 0.319 | 9 / 0 | True |

Failure retained: CPU-thread experiment interrupted. Previous extra policy was restored; no completed winner is claimed.

Observed whole-Mac CPU range: 6.1–47.4%; includes other applications. System swap first/last: 4.71/5.29 GiB.

Two repetitions are not a confidence interval. Zero false positives on 13 selected controls does not establish library-wide precision.

Session `1127061749`; code `fc48a701e6867207c04da62708cf716760e825ca`; sample SHA-256 `3beae47139538015c9968b5d39a38b5bfb3bdb1f9b740370406d6ca73ee57ca2`.

[Protocol](2026-11-26-cpu-threads.md) · [Journal](2026-11-26-cpu-threads.jsonl)
