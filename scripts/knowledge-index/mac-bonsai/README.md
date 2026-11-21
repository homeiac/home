# Mac Bonsai backfill

Piglet selects pending media, decodes it, and sends the same summary prompt to either the RTX Ollama worker or the Mac Metal worker. Only Piglet writes the resulting Parquet batches. The model column distinguishes `bonsai-27b` and `bonsai-27b-metal`. Grafana counts each backend after the write completes and reports cache hits separately.

The Mac launch agent reads `policy.json` on the preview branch every minute. `slots` sets server contexts of 8,192 tokens each. `offered` sets Piglet's maximum concurrent requests to the Mac. When the Mac sleeps or the policy is disabled, Piglet continues using the RTX. Interrupted Mac model requests return to the primary worker before persistence.

## Deployment

Run `CB_HOST=root@<inventory-host> python3 scripts/knowledge-index/mac-bonsai/install.py` on the Mac to install the checksum-pinned runtime and launch agent. This provisions a runtime key on the two hosts and forwards only the Piglet loopback inference port through SSH. To enable discovery on the Piglet worker, use `deploy-pipeline-preview.py --worker-only --mac-assist --parallel 2 --expected-worker-sha <deployed-sha256> --confirm-preview` with the same `CB_HOST`. Subsequent Mac slot and availability changes use the Git policy.

## Reproduce the experiment

Run `factorial.py --inputs <pilot media folder> --output <private evaluation folder>` with Python after installing the pinned model. Each block uses the same ten photos, two eight-frame clips and eight individual stills. One separate warmup precedes each cell. The second block reverses the order of configurations. It reshuffles the items once for all configurations in that block. Model input and output tokens and request timings are stored in the evaluation database. The experiment measures structured caption throughput and excludes library reads, clip decoding and Parquet writes.

The initial factors are two or twenty server slots and two or twenty offered requests, with a separate eight/eight trial. Sustained macOS memory pressure excludes that allocation and larger allocations from production. The runner completes the comparison at a lower upper level and tests one client per slot there. A production candidate must complete all 40 timed requests across both blocks with normal memory pressure. Among candidates within 5% of the fastest rate, the lowest pooled p95 latency wins, with peak resident memory as the tiebreaker.

Run `decision.py <evaluation folder>/factorial.sqlite3` for the comparison. Save the output as `decision.json` in the evaluation folder to include the selected configuration in the export. Run `export_eval.py <evaluation folder>/factorial.sqlite3 <output.duckdb>` for the per-item tokens and timings, configuration results and available hardware, network and production measurements. A trial marked “Not run” has no timing data.

## Cache diagnostics

The host simulates 64 MiB, 256 MiB and 1 GiB least-recently-used frame caches on requests that reach Metal after caption-cache lookup. Each entry retains a frame digest and JPEG size. Grafana shows the percentage of transmitted image bytes each capacity could reuse. The accompanying timing panel separates client wall time from the model's reported prompt and generation time.

For a faster, read-only sample on Piglet, run `replay_cache.py --index <index> --library <library> --enricher <id> --limit 512`. It decodes the next pending items and simulates sequential successful deliveries before backend selection or caption-cache lookup. For a link-only control, `CB_HOST=root@<inventory-host> python3 network_probe.py <pilot media folder> <output.json>` posts synthetic bodies sized to match the previews. These controls complement the live counters.

On November 21, 2026, the replay decoded 510 of 512 pending assets. A 64 MiB cache could have reused 8.6% of transmitted bytes in that sample, with the same result at 256 MiB and 1 GiB. The slowest of 54 network probes sized to those assets took 14 ms. Model requests took seconds. The production worker uses the existing caption cache and measures potential preview reuse without retaining media on the Mac.
