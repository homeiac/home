# Waffles continuous-production results

**Status: interrupted / incomplete.**

Baseline production workers remained separate from the extra-worker benchmark. Mac baseline uses Metal; Linux baselines use CPU. Chief-horse is guarded standby and RTX is unused.

The frozen sample contains 122 photos including 13 Waffles and 13 non-Waffles controls. A valid trial requires at least 9 true positives, zero false positives, unchanged binary decisions, one attempt and no unexpected process exits. These selected controls do not establish library-wide accuracy.

| Backend / device | Extra processes | CPU lanes | Pass | Photos/min | Mean seconds/photo | TP / FP | Valid |
|---|---:|---:|---|---:|---:|---|---|

## Selected settings


Failure retained: Continuous experiment interrupted (KeyboardInterrupt). Extra capacity restored; baseline production is not paused by this runner.

## Observed resource ranges

Mac whole-system CPU: 6.4–22.3%. Apple GPU: 97–100%. These include other applications.
Mac system swap at first/last sample: 19.53/19.51 GiB. This includes preexisting swap; it is not attributed entirely to Waffles.
still-fawn maximum observed host temperature: 40.0°C.

## Provenance

Session `1127053201`; code revision `53325ca5341c18621d05c3b0320fe5eea76d35ec`.
Sample SHA-256 `3beae47139538015c9968b5d39a38b5bfb3bdb1f9b740370406d6ca73ee57ca2`.
Classifier SHA-256 `99b7570ece61f51168a93d0a085b0b31d78da38bb6fb20aaa09a8da9754b41e2`.

[Protocol](2026-11-26-continuous-production.md) · [Append-only journal](2026-11-26-continuous-production.jsonl)
