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
Its [results](2026-11-26-cpu-threads-results.md) and
[journal](2026-11-26-cpu-threads.jsonl) retain the initial warning rejection and
the follow-up after Rancher was reduced to 8 GiB and warnings became observational.
Two- and four-thread single passes both passed quality; the owner then requested
three Mac production workers, so the sweep was interrupted without an optimum.

The [read-only pipeline diagnosis](2026-11-26-pipeline-diagnosis.md) found that
queue candidate selection scans/sorts about 61,000 jobs and takes roughly half a
second while claims serialize per backend. The Mac Metal main thread spent 70.3%
of sampled time in HTTPS reads. No query, index, lock or client fix was applied.

## Production adoption after the interrupted comparison

still-fawn's two independently valid three-lane passes supported an operational
decision to enable two CPU extras there. This does not turn the interrupted
combined experiment into a successful result. The
[adoption journal](2026-11-26-still-fawn-adoption.jsonl) records the decision before
the change, convergence, and more than two minutes of subsequent observation.
Temperatures stayed 38–43°C, minimum host available memory was 1706 MiB, every
admitted baseline advanced, and no previously healthy workload restarted.

Across startup plus observation, production completions increased by 323 on
still-fawn, 185 on Mac, 76 on PVE and 30 on fun-bedbug. These unequal real photos
are operational progress, not a controlled before/after speedup. Production now
uses the original baseline workers plus two still-fawn extras with three CPU
affinity lanes. Subsequently the owner explicitly increased Mac to its Metal
baseline plus two quality-valid CPU extras at two threads each. This is an operator
setting, not the winner of a completed sweep. Chief-horse remains guarded standby
and RTX is unused.

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
