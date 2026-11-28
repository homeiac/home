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

## Mac ten-thread arm — rejected

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

## still-fawn 75% arm — running

Independent cgroup readback reports `CPUQuotaPerSecUSec=750ms`, MemoryHigh 10 GiB,
MemoryMax 12 GiB. The first frozen input is still warming within its explicit
900-second CPU diagnostic deadline. It has no qualifying completion or quality
claim yet. This longer diagnostic deadline does not silently change production's
existing 100-second Metal/150-second RTX request timeouts. Any useful CPU production
route needs its own bounded adapter and verified publication path.

Private arm: `/private/tmp/cricket-still-fawn-q75-forward`; host/guest resource and
peer samples: `/private/tmp/cricket-still-fawn-q75-resources.jsonl`. Next: close the
arm by measured acceptance or rejection, verify cleanup/recovery, descend under
the same bounds, and reverse-repeat eligible settings. No other CPU owner is active.

## Completion remains open

Both backend rows remain open. Required: measured descending outcomes, complete
reviewed quality on passing profiles (including separate calls if joint fails),
independent evaluation/readback, reverse repetition, combined useful throughput,
chosen setting or tested rejection, cleanup/recovery, pushed receipts and served
Grafana before/after verification. Source/model/prompt or background-workload changes
require a new comparable profile/baseline. Readiness and this journal do not establish
the best configuration.
