# Ollama CPU priority

Ollama previously had no CPU request. On a busy 10-vCPU node, that leaves
its CPU inference work with minimal scheduling weight. The deployment now
starts at 4 CPUs, and VPA adjusts the CPU request between 4 and 5 CPUs.
There is no CPU limit; memory and GPU allocations are not controlled by VPA.
This improves contention priority, not physical host capacity.

The initial deployment rollout changes QoS from BestEffort to Burstable and
requires one restart. A zero-surge rollout stops the existing model pod before
creating its replacement. Subsequent
VPA changes use Kubernetes in-place CPU resizing with NotRequired restart policy.
The updater runs in InPlace mode and has no pod eviction permission. An infeasible
resize waits rather than restarting the model. The updater can converge to the
target after a two-minute pod warmup, instead of waiting the default 12 hours
when the current request is already inside the recommendation bounds. The
upstream flag name includes "eviction", but InPlace mode and no eviction RBAC
keep these changes restart-free. Template request remains 4 CPUs
on later pod replacements; the updater reapplies recommendations afterward.

Requires Kubernetes 1.35+ and existing VPA 1.7.3 CRDs. Those CRDs are currently
owned by photo-enrichment-preview; do not install a second copy or delete that
owner without transferring CRD ownership. Images are pinned to verified digests.
InPlace is an alpha VPA feature explicitly enabled on this scoped updater.
No admission webhook is needed: the template provides initial requests and
--use-admission-controller-status=false enables the in-place updater loop.

There is exactly one Ollama VPA, one recommender and one updater scoped to
ollama. The existing photo recommender is scoped to immich-pilot, so neither
recommender processes the other's policies. No CRDs or webhook are duplicated.
The controllers prefer nodes other than the busy GPU node. Resizing permissions
are namespace-scoped; cluster permissions are read-only. Single-replica Recreate
controllers disable leader election and cannot overlap during rollout.

At rollout, the GPU node reserved 4.205 of 10 CPUs before Ollama; the 5-CPU cap
leaves 0.795 CPU unreserved. Recheck capacity when adding workloads. VPA sees
observed CPU consumption, not unmet demand; the 4-CPU floor prevents a starved
workload receiving a tiny recommendation.

Verify after Flux reconciliation:

```sh
scripts/ollama/check-cpu-vpa.sh
```

Inspect VPA recommendation, pod requested/allocated CPU, controller errors and
resize conditions. Compare summary inference time and generated tokens/second
under comparable traffic; a healthy controller alone does not prove a speedup.
Revert this change through Git to roll back. Do not edit the live Deployment.

Upstream: https://github.com/kubernetes/autoscaler/tree/vertical-pod-autoscaler-1.7.3/vertical-pod-autoscaler
Related investigation: #212.
