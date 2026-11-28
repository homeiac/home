# Cricket and photo CPU tuning — live journal

Status: active; no best configuration selected. The user authorized finishing CPU
tuning on the Mac and still-fawn, starting at the measured shared allowance and
descending. Cricket is the sole CPU actuator for both pools. The Knowledge Index
chat independently reviews quality and publication evidence and owns Grafana/#218.
Protected photo allocation remains four Mac Metal and three RTX lanes.

## Contracts and baseline

- Integrated #289 coordination/completion update `0904e04` in local merge
  `1b297d9`. Also integrated parser-parity clarification `1ad200f` before the next
  Mac arm. It does not change already recorded model inputs/settings.
- Existing pinned Bonsai Q1 model/Q8 projector; CPU and projector offload disabled.
  Original production-size images and prompts are frozen privately. Twelve reviewed
  photo cases include ten exact-stage references; unknown/abstained and unsupported
  actions stay in quality denominators. CPU joint inference must meet the applicable
  reviewed quality baseline; Metal currently uses separate calls.
- Expiring per-pool Kubernetes Leases are acquired, independently read back and
  renewed. A competing owner is refused. Trial resources are bounded; a released
  lease can be reacquired only by conditional version update. Three helper tests
  passed without cluster mutations before live use.
- The current formal capacity CLI still lacks complete phase/evaluation receipt
  integration. These are explicitly supervised experimental arms, not automatic
  admission or production promotion. Parsed JSON alone contributes no new verified
  production output.

| Pool | Measured protected baseline | Initial trial bound |
| --- | --- | --- |
| Mac CPU | 18 physical/logical CPUs; observed peak 4.7646 cores; memory-pressure free ≥56%; swap did not grow; protect five observed cores, two for returning pet work and one system core | Ten threads, aggregate quota 1000%, one context; frozen cohort; no GPU offload |
| still-fawn physical CPU, including guest 108 | Four CPUs; host peak 2.982 cores, guest peak 2.0976; running-pod CPU requests total 2.05; guest available memory ≥19.818 GiB | 75% of one core after 0.25-core system margin; one thread/context; cgroup MemoryHigh 10 GiB, MemoryMax 12 GiB |

Mac baseline: 300.138 s, 37 Metal and 93 RTX completions; their window p95s were
39.866 s and 14.363 s. Still-fawn baseline: 300.145 s, 38 Metal and 108 RTX
completions; their p95s were 38.066 s and 13.681 s. Whisper had no queued/in-flight
work; its request and returning demand remain protected. Its durable attempt counts
were unchanged on repeated read-only inspection. Pet Mac activity was zero.

Private baseline receipts:
`/private/tmp/cricket-mac-cpu-protected-baseline` and
`/private/tmp/cricket-cpu-clean-baseline-with-latency.jsonl`.

## Scope correction — workload totals govern acceptance

The first operator guard incorrectly applied a 90% rate floor independently to
Metal and RTX even though both serve `library-face-observations`. That floor was
not a registered backend SLO. Preserve the original stop receipts as history, but
use aggregate unique face-workload progress and combined latency/errors for
acceptance. Distinct Whisper, pet and service workloads retain their own budgets.
Frozen CPU evaluations are a separate unit and never inflate production progress.
Future evaluations use an explicit face-evaluation caller identity rather than the
legacy Cricket helper's default identity. Historical captures remain diagnostic.

Recomputing the same closed windows across the face workload gives:

| Arm | Unique GPU production completions | Combined p95 | Correct scoped result |
| --- | --- | --- | --- |
| Ten threads | 130 → 133 (ratio 1.022928) | 37.434 → 42.503 s | Aggregate latency fails 10% budget; stop remains justified on that evidence |
| Six threads | 130 → 137 (ratio 1.053790) | 37.434 → 36.111 s | Aggregate production peer budgets pass; the earlier backend-only rejection is withdrawn |

Neither includes CPU benchmark replays as new production work. Six-thread quality
and a unique-source live canary remain unqualified. Do not discard it solely for
moving work between backends. New profile arms compare both the original protected
baseline and a fresh baseline, with per-backend figures retained as diagnostics.

## Mac ten-thread arm — stopped, aggregate latency failure confirmed

First attempt returned fenced JSON in 63.897 s with zero cache reuse. The harness
incorrectly used bare JSON parsing. Preserved this as a diagnostic; corrected
parity against the production decoder before rerunning the same setting. Later
runner revisions import the production decoder/normalizer directly. Saved-response
parity checks passed seven responses without new inference.

The repeated arm warmed before measurement. Its first closed 300.182-second peer
window failed both Metal gates:

| Backend | Baseline → trial completions | Throughput ratio | Baseline → trial p95 |
| --- | --- | --- | --- |
| Mac Metal | 37 → 31 | 0.837716 | 39.866 → 44.680 s |
| RTX | 93 → 102 | 1.096615 | 14.363 → 12.388 s |

Independent Knowledge Index review reproduced the counts, rates and latency loss.
Faster RTX output does not offset the losing Metal peer. Five completed CPU cases
received partial independent quality review: 2/5 exact stages, 4/5 supported whole
actions, 2/5 both correct. This is a partial cohort, not a full quality score.

Rollback stopped only the isolated CPU listener. Runtime cleanup lingered after
SIGTERM; after the bounded drain interval, the exact lease-owned trial process was
killed. An incomplete evaluation was excluded. At `1795847358556469000` ns,
independent inspection confirmed zero trial model processes and released ownership.
Production allocations and corrections were unchanged. Authoritative recovery
starts after that confirmation; earlier overlapping shutdown captures are excluded.

Private arm: `/private/tmp/cricket-mac-cpu-t10-forward-v2`. Closed OTLP telemetry,
original peer comparison, independent review, rollback and drain readbacks are
retained there. Recovery: `/private/tmp/cricket-mac-cpu-recovery-verified-cleanup`.
Next: require recovery, then six threads; bracket useful settings and reverse-repeat
qualifying candidates. Request-boundary stop fencing and production decoder, action
normalizer and stage normalizer reuse are added before the next arm. Four synthetic
request-boundary tests pass, including stop/lost-owner/changed-input refusal and
valid low-confidence/null-action semantics. Stage helper source is the peer's
`cdd03bc` refactor; subsequent trial configs bind its source digest.

## Mac six-thread arm — stopped; aggregate verdict still open

After confirmed cleanup, recovery passed a closed 300.198-second window: Metal
39 completions versus the original 37, p95 36.982 versus 39.866 seconds; RTX 96
versus 93, p95 14.725 versus 14.363 seconds. Independent review confirmed recovery.
The six-thread/600% quota arm used the same frozen model/inputs and a bound on
the production validator source. The original backend-only guard stopped it after
its closed 300.154-second window showed:
Metal completed 32 versus the original 37 (ratio 0.864819), while p95 38.774 s
stayed within the 39.866 s baseline budget. RTX completed 105 versus 93, p95
11.694 versus 14.363 s. These backend diagnostics do not establish a whole-workload
loss; the aggregate correction above supersedes that interpretation.

The automatic watcher wrote the owner stop signal at the closed-window failure.
The current request finished, four completed evaluations were retained, and no new
request was admitted. Independent partial quality: 2/4 exact stages, 3/4 supported
whole actions, 2/4 both correct. At `1795848197998316000` ns, independent inspection
confirmed no model process/listener and released ownership. Private arm:
`/private/tmp/cricket-mac-cpu-t6-forward`. No six-thread production setting was
promoted. Lower settings and the alternative profile remain open.

The ten-thread rejection is visible in Grafana panel 294, dashboard
`knowledge-index`. Independent browser readback confirmed the served title and
7.40 → 6.20 Metal faces/min, 18.59 → 20.39 RTX faces/min. The owner separately
records dashboard version 84 and source #218 commit `49b3db3`; the browser UI
observation did not expose the version. Private readback:
`/private/tmp/cricket-grafana-panel294-ui-readback.json`.

## still-fawn 75% arm — failed tested diagnostic deadline

Independent cgroup readback reports `CPUQuotaPerSecUSec=750ms`, MemoryHigh 10 GiB,
MemoryMax 12 GiB. The first frozen input failed the explicit 900-second CPU
diagnostic deadline (901.916 seconds including transport). At 810.5 seconds it had
processed 658 of 767 prompt tokens. It has no qualifying completion or quality
claim. This is a tested safety bound, not a user-mandated latency SLO or a blanket
CPU rejection. This diagnostic deadline does not silently change production's
existing 100-second Metal/150-second RTX request timeouts. Any useful CPU production
route needs its own bounded adapter and verified publication path.

Private arm: `/private/tmp/cricket-still-fawn-q75-forward`; host/guest resource and
peer samples: `/private/tmp/cricket-still-fawn-q75-resources.jsonl`. Cleanup reports
inactive/dead and a closed listener; independent unit readback confirmed inactivity.
Preserve this failure and evaluate a concrete useful-gain hypothesis below rather
than treating the arbitrary diagnostic timeout as proof against every CPU profile.

## Smaller CPU quality profile — artifacts ready, no inference yet

The outcome researcher checked publisher primary sources for a smaller vision
model with implemented CPU kernels. The next bounded quality hypothesis is
[Prism Bonsai 2 2B](https://huggingface.co/prism-ml/Ternary-Bonsai-2-2B-gguf),
using PQ2_0 language weights and the Q8_0 vision projector. The publisher documents
vision, native CPU/OpenAI-compatible image requests and Apache 2.0 licensing.
Artifact sizes are about 517 MB and 365 MB, not measured resident memory. The Q8
projector avoids the publisher's documented concurrent-request BF16 issue. These
facts establish a candidate, not accuracy on the marked-person cohort or speed on
either machine.

| Component | Immutable pin / SHA-256 |
| --- | --- |
| Model repository revision | `a6032a5089ac27e96be3a80c7b42d1ad0bd89887` |
| PQ2_0 model | `d5f01a4ecaf49239653308ee732ad1a0c5f802c0ddb997549fc7b694c8b45928` |
| Q8_0 projector | `ac9934e8d7966d0d62442c202ec8fdad99a045dea79366c1a4a246a46f5c0533` |
| Runtime source | `41c86f7d6d0ab27c5d0529958d7ee7aa3091309f` |
| macOS ARM64 runtime archive | `0281adb71a1d4000181aa3e9a0acbfec4189b1dc67dfb8091847b1c42aa0b10d` |
| Ubuntu x64 CPU runtime archive | `daa1b6e0ddc169fed0dcccdde7499ef5e10f0533b76554d6e26e3bb2db5a7a9b` |

Published pins were checked against the publisher's
[checksums](https://huggingface.co/prism-ml/Ternary-Bonsai-2-2B-gguf/blob/a6032a5089ac27e96be3a80c7b42d1ad0bd89887/SHA256SUMS)
and [runtime assets](https://github.com/PrismML-Eng/llama.cpp/releases/expanded_assets/prism-b12220-41c86f7).
Both hosts now have locally hash-verified files in isolated directories, and
the pinned runtime's version command succeeds on each without loading a model.
Linux exposes AVX2 but no AVX-512 VBMI; do not claim the optional AVX-512 speedup.
Preparation used bounded CPU and did not replace a production runtime/model.
Private receipts: `/private/tmp/cricket-bonsai2-mac/prepared.json` and guest
`/var/tmp/cricket-bonsai2-profile/prepared.json`. Prepare in isolated
directories after an existing immutable measurement closes; do not replace a
production runtime/model or alter a running trial.

Start with the existing separate AGE/ACTION prompts, exactly the original frozen
images, original temperature/output limits and production normalizers. Historical
matched Mac two-call quality was 21/40 exact reviewed stages, 35/48 supported whole
actions and 16/40 both correct, with 48/48 completed over four repetitions of the
twelve faces. This is a reference, not a new CPU qualification. Include low-confidence
and null-action abstentions in the declared denominators.

At a fresh maximum shared allowance, first screen one case with both calls, using
explicit applicable production request bounds. If ready, complete the twelve-face
quality pass, independently review/read back outputs, and repeat promising quality
comparisons. Only a qualifying profile proceeds to descending/reverse capacity
selection with unchanged peer gates. A new model is a new profile; never pool its
measurements with the 27B arm. No new model inference has started at this receipt.

## Completion remains open

Both backend rows remain open. Required: measured descending outcomes, complete
reviewed quality on passing profiles (including separate calls if joint fails),
independent evaluation/readback, reverse repetition, combined useful throughput,
chosen setting or tested rejection, cleanup/recovery, pushed receipts and served
Grafana before/after verification. Source/model/prompt or background-workload changes
require a new comparable profile/baseline. Readiness and this journal do not establish
the best configuration.
