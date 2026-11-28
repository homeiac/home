# Running AI workloads on shared compute

## 1. Ingest and trace a job

```mermaid
flowchart LR
    In["Ingest asset + source version"] --> Q["Deduplicate and enqueue with trace context"]
    Q --> Claim["Claim eligible job with a lease"]
    Claim --> Stage["Trace fetch, decode and model stages"]
    Stage -->|Success| Write["Commit or publish once"]
    Stage -->|Retryable| Retry{"Attempts left?"}
    Retry -->|Yes| Q
    Retry -->|No| Skip["Record terminal failure; continue queue"]
    Write --> Verify["Read back verified output"]
    Stage -. "timed spans" .-> OT["OTel capture"]
    Verify -. "verified count" .-> Rate["Fleet throughput"]
```

This is the adapter contract for new work. Propagate the parent context to a separate writer. A retry gets a fresh attempt span. Store trace and asset IDs in private evidence; export bounded metric labels. [Field dictionary](../reference/workload-telemetry.md)

### Media publication gate

```mermaid
flowchart LR
    Fact["Effective correction and native evidence"] --> Owner{"Existing scene owned by another producer?"}
    Owner -->|Yes| Stop["Stop publication; reconcile explicitly"]
    Owner -->|No| Merge["Compose scene with the versioned vocabulary"]
    Merge --> Schema{"Valid OpenLABEL 1.0.0?"}
    Schema -->|No| Fix["Repair producer; retain last valid revision"]
    Schema -->|Yes| PG["Append PostgreSQL revision"]
    PG --> Read["Independent readback + producer manifest"]
    Read --> Check{"Run, digest, occurrence and relation endpoints match?"}
    Check -->|No| Fix
    Check -->|Yes| Quality["Evaluate meaning on reviewed examples"]
    Quality -->|Pass| Count["Count verified output in the trial"]
```

Declare `--output-kind media` at intake. The review command runs the shared checker when supplied the manifest, readback and pinned schema. Missing publication evidence prevents eligibility. Human corrections retain stable occurrence IDs across revisions. [Publication contract](../architecture/media-workload-contract.md)

## 2. Place the work

```mermaid
flowchart TD
    A["Agent receives a workload"] --> B["workload.py start --live"]
    B --> C["Expand serving pool → device → other callers"]
    C --> D{"Eligible backlog and measured headroom?"}
    D -->|No or unknown| E["Keep baseline allocation; measure backlog and headroom"]
    D -->|Yes| F["Select measured ceiling after peer reservations"]
    F --> G["Freeze input cohort, baseline rate and peer budgets"]
    G --> H["Run matched quality check on candidate and baseline"]
    H -->|Pass| I["Owner runs the canary alongside baseline workers"]
    H -->|Fail| J["Keep existing placement; journal result"]
```

`start` discovers registered peers. Add `--live` for current exporter observations. For a workload with a capacity adapter, the planner selects a pool from ready backlog and free worker equivalents. For Cricket, reserve scheduled and active demand, test the highest measured shared allowance, then sweep down one pool at a time. Repeat in reverse order and choose the fewest workers within 5% of the fastest repeatable qualifying rate. A caption controller that can actuate only one extra lane tests that increment against the same peer budgets. [Cricket operating policy](https://github.com/homeiac/home/blob/1587fbc1b7722c7ed2530deae46540cdc19e730f/docs/runbooks/shared-indexer-tuning.md) · [Agent commands](../guides/shared-workload-agent.md)

## 3. Trace the bottleneck

```mermaid
flowchart TD
    A["Verify the drop in durable completions"] --> B["Close one workload, host and run window"]
    B --> C["Compare time in queue, fetch, model and write"]
    C --> D{"What does the evidence support?"}
    D -->|Slow successful claim and large sort| E["Test indexed ready FIFO"]
    D -->|Model dominates and device busy without worker| F["Identify co-tenant; test isolated placement"]
    D -->|Ambiguous| G["Collect the requested plan, worker profile or device sample"]
    G --> B
    E --> H["Seal the proposed fix and acceptance gates"]
    F --> H
    H --> I["Run the trial; open outcome evidence afterwards"]
```

These are the two implemented diagnosis rules. A GPU sample alone cannot identify the competing process. In the Waffles replays, the indexed SELECT fell from 1,662 to 0.286 ms. Metal delivered 345 → 627 → 375 photos/min across busy, isolated and restored phases. [Receipts and replay commands](../experiments/waffles/otel-replay/README.md)

## 4. Tune live and scale

```mermaid
flowchart TD
    A["workload.py review"] --> B{"Valid stage, trace and metric fields?"}
    B -->|No| X["Correct exporter or capture; check again"]
    B -->|Yes| C{"Baseline and trial comparison supplied?"}
    C -->|No| O["observe_only"]
    C -->|Yes| D{"What happened across all affected callers?"}
    D -->|Measured loss or quality failure| R["rollback: owner removes the increment"]
    D -->|Missing peer or incomparable windows| H["hold: keep baseline and collect evidence"]
    D -->|Gates pass and diagnosis supports trial| E["eligible: repeat required windows and quality check"]
    E -->|Confirmed| P["Owner promotes; persist the new baseline"]
    E -->|Failed| R
    P --> J["Journal settings, per-workload rates, quality and final state"]
    R --> J
    P -->|Workload mix changes| N["Re-census callers and requalify the allocation"]
```

Compare each workload in its own units. For media producers, run `verify-media` against an independent PostgreSQL readback and check the reviewed output separately. The review command emits decisions. The owning supervisor changes capacity. [Telemetry fields](../reference/workload-telemetry.md) · [C4 architecture](../architecture/distributed-ai-workloads.md) · [Adapter inputs](../../scripts/perf/otel-diagnosis.md)
