# Immich VPA recommendations

This deployment installs only the VPA recommender. It can read resource usage and
write VPA recommendations/checkpoints in `immich-pilot`. It cannot evict or resize
pods and does not install an admission webhook. Both target policies use `Off`.
The existing Metrics Server provides usage samples; recommendations accumulate
after deployment and should cover bulk import plus ordinary browsing before
automatic resizing is enabled.

## Pinned upstream sources

- Release: `vertical-pod-autoscaler-1.7.3`, commit
  `f16d0c32389ea2a45d60d58a55f513f2d2b94915` in `kubernetes/autoscaler`.
- `crds.yaml` is the unmodified upstream
  [vpa-v1-crd-gen.yaml](https://github.com/kubernetes/autoscaler/blob/f16d0c32389ea2a45d60d58a55f513f2d2b94915/vertical-pod-autoscaler/deploy/vpa-v1-crd-gen.yaml).
- RBAC and deployment derive from the same release's
  [vpa-rbac.yaml](https://github.com/kubernetes/autoscaler/blob/f16d0c32389ea2a45d60d58a55f513f2d2b94915/vertical-pod-autoscaler/deploy/vpa-rbac.yaml)
  and [recommender-deployment.yaml](https://github.com/kubernetes/autoscaler/blob/f16d0c32389ea2a45d60d58a55f513f2d2b94915/vertical-pod-autoscaler/deploy/recommender-deployment.yaml).
- Official multiarchitecture image digest verified with `docker buildx imagetools
  inspect registry.k8s.io/autoscaling/vpa-recommender:1.7.3`:
  `sha256:3b207e6e719e8a88b96b5777afa6f6fb261e73669fa39f487c04560d85bf2e7d`.
- VPA 1.7 supports Kubernetes 1.35–1.37; the current cluster is 1.35.

## Reconciliation order

Reconcile this directory first. Wait for both CRDs to become `Established` and
the recommender deployment to become ready. Reconcile `policies/` afterwards,
using a separate Flux Kustomization with `dependsOn` on the controller installation.
This prevents server-side dry-run failures for unknown VPA kinds on first install.
The namespace `immich-pilot` must already exist for its scoped Role and RoleBinding.

## Before enabling updates

`maxAllowed` limits recommended **requests**. `RequestsAndLimits` preserves each
container's existing limit-to-request ratio: server CPU 4:1, server memory 3:1,
and machine-learning CPU/memory 4:1. Simply changing `Off` to an automatic mode
could therefore produce limits much larger than the bounds written here. Revisit
the ratio, absolute LimitRange constraints and node capacity before doing so.

Kubernetes 1.35 supports stable in-place resizing. VPA `InPlaceOrRecreate` is GA
since 1.6 but may evict when resizing is infeasible; `InPlace` never falls back to
eviction but remains alpha in 1.7 and needs its feature gate. Single-replica
workloads also require checking the updater's disruption/min-replica policy.
Neither mode creates spare CPU on a saturated node. See upstream
[features](https://github.com/kubernetes/autoscaler/blob/f16d0c32389ea2a45d60d58a55f513f2d2b94915/vertical-pod-autoscaler/docs/features.md).
