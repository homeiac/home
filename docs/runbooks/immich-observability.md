# Immich bottlenecks and VPA

The Photo App dashboard (`/d/photo-app/photo-app`) starts with live Immich queue
backlog, successful thumbnail jobs/minute, estimated drain time, CPU throttling,
usage versus limits, and VPA recommendations. Its Immich-only value stream map
keeps the import branch readable. Knowledge Index includes the same branch in
the complete pipeline map. Both dashboard ConfigMaps are managed by the
`photo-enrichment-preview` Flux Kustomization while PR #218 is unmerged.

## Diagnose stalled thumbnails

Run `scripts/knowledge-index/check-immich-observability.py` with `~/kubeconfig`.
It checks each new dashboard query against live Prometheus without photo API
credentials or data writes. A missing series fails validation; it is not treated
as a zero queue. Check telemetry health before interpreting backlog.

- Positive backlog with zero throughput: inspect active/failed states, pod logs,
  CPU throttled periods, memory/limits and storage errors.
- Throttled CPU with backlog: the hard CPU limit is restricting that workload.
  Compare node headroom before raising limits. VPA cannot create extra CPU.
- Nonzero throughput: drain estimate uses the recent five-minute rate and assumes
  no additional arrivals. It varies with image/video work and ML contention.
- No failed jobs does not mean progress. Retained failed jobs are a gauge, not
  an error rate. Rate counters are native Immich worker metrics.

Prometheus alerts cover a stalled thumbnail queue, CPU throttling while queued,
and missing queue telemetry. These are diagnostic signals, not automatic job
retries or resource mutations. Existing legacy Photo App traces/logs are separate
from Immich; these changes do not claim distributed tracing of Immich jobs.

## GitOps and generation

Sources are under `scripts/knowledge-index/`:
`gen-immich-observer.py`, `immich-queue-metrics.mjs`, `immich_dashboard.py`,
`gen-photo-app-dashboard.py`, and `gen-dashboard.py`.
Generated manifests live under `gitops/clusters/homelab/apps/photo-enrichment/`.
Regenerate `immich-observer.yaml`, `dashboard.yaml`, and
`knowledge-index-dashboard.yaml` from their respective generators before committing.
The observer only reads Redis queue lengths and the two VPA objects. It exports
no photos, paths, identities or credentials. No external service is called.

VPA 1.7.3 is installed with only its recommender. Server and ML policies remain
`Off`; no updater or admission controller is deployed. Read `vpa/README.md`
before enabling updates: request caps are not absolute limit caps when existing
limit/request ratios are preserved. Collect an import and ordinary-browsing
baseline before changing policy.

Verified deployment on 2026-11-19: cluster K3s 1.35.0, both VPA recommendations
available, queue telemetry healthy, and browser-rendered backlog and graphs.
Initial server target was about 2.82 CPU / 2.13 GiB; ML target hit its 2 CPU cap.
These are early samples, not final sizing guidance. All persistent configuration
was deployed through commits and Flux; the earlier thumbnail reprioritization
was a separate one-time supported BullMQ queue operation.
