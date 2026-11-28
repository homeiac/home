# Shared workloads in the homelab

## C4 context · who owns the change?

```mermaid
C4Context
    Person(agent, "Workload agent", "Runs the requested job and checks the evidence")
    System(owner, "Workload supervisor", "Cricket Indexer, Knowledge Index or Waffles")
    System(review, "Performance review", "Read-only diagnosis and trial assessment")
    System_Ext(peers, "Other workload owners", "Supply verified output and service budgets")
    Rel(agent, owner, "Submits work through its adapter")
    Rel(agent, review, "Runs checks")
    Rel(owner, review, "Supplies OTLP and verified windows")
    Rel(peers, review, "Supply caller census and peer windows")
    UpdateLayoutConfig($c4ShapeInRow="2")
```

## C4 containers · where does evidence go?

```mermaid
C4Container
    Container(worker, "Worker and writer", "Native or Kubernetes", "Claim jobs and commit results")
    ContainerDb(ledger, "Completion ledger", "Workload-owned", "Durable output and readback")
    Container(collector, "OTel Collector", "Photo observability stack", "Receives instrumented signals")
    Container(obs, "Observability stores", "Tempo, Loki, Prometheus", "Grafana reads traces, logs and rates")
    Container(cli, "Workload CLI", "Python", "Reviews closed captures and peer windows")
    Rel(worker, ledger, "Commits output")
    Rel(worker, collector, "Exports telemetry", "OTLP")
    Rel(collector, obs, "Exports signals")
    Rel(worker, cli, "Adapter supplies closed files", "OTLP JSONL")
    Rel(ledger, cli, "Adapter supplies verified windows")
    UpdateLayoutConfig($c4ShapeInRow="2")
```

## C4 deployment · who shares the hardware?

```mermaid
C4Deployment
    Container(cricket, "Cricket Indexer", "Caller", "Analyses video")
    Container(ki, "Knowledge Index", "Caller", "Publishes captions")
    Deployment_Node(mac, "Mac M5", "Native host") {
        Container(bonsai, "Bonsai server", "Shared slots", "Serves both indexers")
        Container(dog, "Waffles worker", "Native process", "Uses Metal directly")
        Container(metal, "Metal device", "Shared GPU", "Runs model stages")
    }
    Rel(cricket, bonsai, "Requests slots")
    Rel(ki, bonsai, "Requests slots")
    Rel(bonsai, metal, "Submits work")
    Rel(dog, metal, "Submits work")
    UpdateLayoutConfig($c4ShapeInRow="2")
```

These are possible routes. The [registry](../../scripts/perf/shared-workloads.json) also covers pumped-piglet’s RTX and its Frigate and Immich peers. Determine activity from timestamped observations. A live snapshot covers aggregate activity; a matched trial also needs each affected caller’s quality and service measurements.

| Boundary | Runs today | Adapter work |
|---|---|---|
| Observe | Collector stack, Prometheus observer, OTLP file checks | Propagate caller identity and close windows per producer |
| Tune | Caption controller can add, recheck and remove one lane | Wire fleet review and resource coordination into each owner |
| Publish | OpenLABEL reference checker and PostgreSQL scene writer | Emit producer manifests for legacy outputs |

[Operating workflow](../methodology/distributed-ai-performance.md) · [Agent journey](../guides/shared-workload-agent.md) · [Media publication](media-workload-contract.md)
