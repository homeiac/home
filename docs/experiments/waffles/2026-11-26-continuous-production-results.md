# Waffles continuous-production results

**Status: interrupted / incomplete.**

Baseline production workers remained separate from the extra-worker benchmark. Mac baseline uses Metal; Linux baselines use CPU. Chief-horse is guarded standby and RTX is unused.

The frozen sample contains 122 photos including 13 Waffles and 13 non-Waffles controls. A valid trial requires at least 9 true positives, zero false positives, unchanged binary decisions, one attempt and no unexpected process exits. These selected controls do not establish library-wide accuracy.

| Backend / device | Extra processes | CPU lanes | Pass | Photos/min | Mean seconds/photo | TP / FP | Valid |
|---|---:|---:|---|---:|---:|---|---|
| mac / cpu | 1 | default | a | 120.3 | 0.232 | 9 / 0 | True |
| mac / cpu | 1 | default | b | 190.9 | 0.191 | 9 / 0 | True |
| still-fawn / cpu | 2 | 1 | a | 58.2 | 1.894 | 9 / 0 | True |
| still-fawn / cpu | 2 | 2 | a | 100.6 | 1.064 | 9 / 0 | True |
| still-fawn / cpu | 2 | 3 | a | 108.4 | 0.976 | 9 / 0 | True |
| still-fawn / cpu | 2 | 3 | b | 101.2 | 1.004 | 9 / 0 | True |
| still-fawn / cpu | 2 | 2 | b | 94.4 | 1.102 | 9 / 0 | True |

## Selected settings

- mac: 1 extra cpu processes, default CPU lanes; paired rate 147.6 photos/min. Provisional; the complete experiment has not passed.
- still-fawn: 2 extra cpu processes, 3 CPU lanes; paired rate 104.7 photos/min. Provisional; the complete experiment has not passed.

Failure retained: Mac sustained memory pressure guard (RuntimeError). Extra capacity restored; baseline production is not paused by this runner.

Trial failure retained: mac cpu 3 extras, attempt 1: Mac sustained memory pressure guard.

Trial failure retained: still-fawn cpu 2 extras, attempt 1: Mac sustained memory pressure guard.

## Observed resource ranges

Mac whole-system CPU: 0.0–30.6%. Apple GPU: 93–100%. These include other applications.
Mac system swap at first/last sample: 19.09/18.89 GiB. This includes preexisting swap; it is not attributed entirely to Waffles.
still-fawn maximum observed host temperature: 45.0°C.

## Provenance

Session `1127054343`; code revision `eb22dcf8986dcb83cccdc4046cb8378d7670de39`.
Sample SHA-256 `3beae47139538015c9968b5d39a38b5bfb3bdb1f9b740370406d6ca73ee57ca2`.
Classifier SHA-256 `99b7570ece61f51168a93d0a085b0b31d78da38bb6fb20aaa09a8da9754b41e2`.

[Protocol](2026-11-26-continuous-production.md) · [Append-only journal](2026-11-26-continuous-production.jsonl)
