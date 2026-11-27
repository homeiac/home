# Waffles experiment journal

The purpose is to improve completed throughput while preserving recognition
quality. Record unsuccessful trials and resource costs alongside improvements.
Private photos, asset IDs, credentials and individual cloud-model responses stay
outside this repository.

## Continuous-production experiment

The user requires a baseline worker on every node throughout tuning. The
[replacement protocol](2026-11-26-continuous-production.md) separates permanent
production workers from extra capacity. Its measurements must remain separate
from the earlier isolated trials.

[Results](2026-11-26-continuous-production-results.md) and the
[append-only journal](2026-11-26-continuous-production.jsonl) retain valid passes,
resource rejections and the incomplete combined comparison.

The [one-model CPU-thread experiment](2026-11-26-cpu-threads.md) follows resource
rejections at higher process counts. Its results must remain separate because
the pinned detector library's thread override is explicitly controlled there.

The [throughput exporter audit](2026-11-26-throughput-exporter-audit.md) explains
the reported simultaneous graph drop: old and new queue-pod slopes were added
together. The corrected query deduplicates durable totals before taking the
derivative. PostgreSQL-based benchmark measurements were unaffected.

## Preregistered isolated experiment — interrupted

- [Protocol](2026-11-26-live-tuning.md): hypotheses, frozen inputs, trial order,
  acceptance criteria and selection rule, committed before measured trials.
- [Timestamped JSONL journal](2026-11-26-live-tuning.jsonl): actual settings,
  input/code hashes, resource snapshots, measurements, deviations and restoration.
- [Hardware and runtime observation](2026-11-26-live-tuning-environment.json):
  captured during the experiment without changing configuration. PVE's hypervisor
  SSH observation was unavailable; its Kubernetes node capacity is recorded.
- [Preliminary results and interpretation](2026-11-26-live-tuning-results.md):
  explicitly marked interrupted. The final combined comparison did not run.

The initial preflight aborted before measurement because it counted expired
leases as active work. Production was restored, the check was corrected, and
the deviation was recorded before rerunning. Original records remain intact.
The measured sweep was later interrupted when the user added the continuous
baseline requirement. Production resumed on all four admitted backends.

## Earlier evidence, indexed retrospectively

These studies occurred before this journal protocol was established. Their
existing aggregate records are retained; they are not presented as preregistered
trials of the live-concurrency experiment.

| Question | Evidence | Finding |
|---|---|---|
| Does distributing the same inference work help? | [96-photo ABBA benchmark](../../reference/waffles-backend-benchmark.json) | still-fawn alone: 105.4 photos/min; Mac + PVE + still-fawn: 324.9 photos/min. All binary decisions agreed across passes. |
| Does the current classifier preserve the reviewed labels? | [Backend holdouts](../../reference/waffles-backend-benchmark.json) | Mac, PVE, still-fawn and fun-bedbug each accepted 9/13 Waffles and rejected all 13 non-Waffles controls. |
| Can Luna or Sol recover local misses safely? | [26-photo frontier evaluation](../../reference/waffles-frontier-evaluation.json) | Neither recovered any of the four local misses at the fixed high-confidence rule. Automatic cloud fallback remains disabled. |
| Can the additional native hosts participate? | [Native deployment notes](../../runbooks/immich-pet-tagger.md#native-hosts-outside-kubernetes) | fun-bedbug passed its holdout. chief-horse stayed on standby because the startup memory guard failed; no quality result is claimed for it. |

## Reproduction and operation

The [runbook](../../runbooks/immich-pet-tagger.md#live-tuning-and-experimental-evidence)
documents live controls and resource bounds. `scripts/immich-pet-tagger/continuous-experiment.py`
runs the current sweep against private frozen inputs. The earlier `experiment.py`
is retired for execution; its report generator reads the interrupted journal. Each new execution
uses unique run identifiers. Repeating an experiment appends records rather than
reusing completed jobs or silently overwriting earlier measurements.

Two repetitions and a selected 26-photo holdout do not establish a confidence
interval or library-wide accuracy. Benchmark jobs exclude Immich face/tag writes;
production throughput must be observed separately.
