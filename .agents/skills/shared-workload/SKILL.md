---
name: shared-workload
description: Run or tune a homelab AI workload alongside other callers, check its telemetry and peer impact, and verify its media publications against the existing OpenLABEL store.
---

From the repo root, use the [agent journey](../../../docs/guides/shared-workload-agent.md). Run `python3 scripts/perf/workload.py start` with the actual workload, resource, stage IDs and run ID. Use `--live` for current activity and `--output-kind media` for media publications.

Execute the requested job through its existing supervisor. Before a tuning trial, run `python3 scripts/perf/workload.py diagnose --session PATH`. Run `python3 scripts/perf/workload.py review --session PATH` on the closed trial window. Follow the returned probe or fleet decision and record the owner’s actual allocation and verified output.

[Decision workflow](../../../docs/methodology/distributed-ai-performance.md) · [Field dictionary](../../../docs/reference/workload-telemetry.md) · [Publication contract](../../../docs/architecture/media-workload-contract.md)
