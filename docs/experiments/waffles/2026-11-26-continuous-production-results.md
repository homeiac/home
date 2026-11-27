# Waffles continuous-production results

**Status: interrupted / incomplete.**

Baseline production workers remained separate from the extra-worker benchmark. Mac baseline uses Metal; Linux baselines use CPU. Chief-horse is guarded standby and RTX is unused.

The frozen sample contains 122 photos including 13 Waffles and 13 non-Waffles controls. A valid trial requires at least 9 true positives, zero false positives, unchanged binary decisions, one attempt and no unexpected process exits. These selected controls do not establish library-wide accuracy.

| Backend / device | Extra processes | CPU lanes | Pass | Photos/min | Mean seconds/photo | TP / FP | Valid |
|---|---:|---:|---|---:|---:|---|---|
| mac / cpu | 1 | default | a | 260.3 | 0.161 | 9 / 0 | True |

## Selected settings


Failure retained: Mac sustained memory pressure guard (RuntimeError). Extra capacity restored; baseline production is not paused by this runner.

## Observed resource ranges

Mac whole-system CPU: 0.0–27.0%. Apple GPU: 98–100%. These include other applications.
Mac system swap at first/last sample: 19.32/19.30 GiB. This includes preexisting swap; it is not attributed entirely to Waffles.
still-fawn maximum observed host temperature: 40.0°C.

## Provenance

Session `1127054012`; code revision `a94ef333adbc4af58f7d2c9c7da18ef15b1ae2cc`.
Sample SHA-256 `3beae47139538015c9968b5d39a38b5bfb3bdb1f9b740370406d6ca73ee57ca2`.
Classifier SHA-256 `99b7570ece61f51168a93d0a085b0b31d78da38bb6fb20aaa09a8da9754b41e2`.

[Protocol](2026-11-26-continuous-production.md) · [Append-only journal](2026-11-26-continuous-production.jsonl)
