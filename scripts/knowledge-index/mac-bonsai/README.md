# Mac Bonsai backfill

Piglet selects pending media, decodes it, and sends the same summary prompt to either the RTX Ollama worker or the Mac Metal worker. Only Piglet writes the resulting Parquet batches. The model column distinguishes `bonsai-27b` and `bonsai-27b-metal`. Grafana counts each backend after the write completes and reports cache hits separately.

The Mac launch agent reads `policy.json` on the preview branch every minute. `slots` sets server contexts of 8,192 tokens each. `offered` sets Piglet's maximum concurrent requests to the Mac. When the Mac sleeps or the policy is disabled, Piglet continues using the RTX. Interrupted Mac model requests return to the primary worker before persistence.

## Deployment

Run `CB_HOST=root@<inventory-host> python3 scripts/knowledge-index/mac-bonsai/install.py` on the Mac to install the checksum-pinned runtime and launch agent. This provisions a runtime key on the two hosts and forwards only the Piglet loopback inference port through SSH. To enable discovery on the Piglet worker, use `deploy-pipeline-preview.py --worker-only --mac-assist --parallel 2 --expected-worker-sha <deployed-sha256> --confirm-preview` with the same `CB_HOST`. Subsequent Mac slot and availability changes use the Git policy.

## Reproduce the experiment

Run `factorial.py --inputs <pilot media folder> --output <private evaluation folder>` with Python after installing the pinned model. Each block uses the same ten photos, two eight-frame clips and eight individual stills. One separate warmup precedes each cell. The second block reverses the order of configurations. It reshuffles the items once for all configurations in that block. Model input and output tokens and request timings are stored in the evaluation database. The experiment measures structured caption throughput and excludes library reads, clip decoding and Parquet writes.

The initial factors are two or twenty server slots and two or twenty offered requests, with a separate eight/eight trial. Sustained macOS memory pressure excludes that allocation from further trials. When this happens, the runner completes the comparison at a lower upper level. A production candidate must complete all 40 timed requests across both blocks with normal memory pressure. Among candidates within 5% of the fastest rate, the lowest pooled p95 latency wins, with peak resident memory as the tiebreaker.

Run `decision.py <evaluation folder>/factorial.sqlite3` for the comparison and `export_eval.py <evaluation folder>/factorial.sqlite3 <output.duckdb>` to query the two benchmark tables with DuckDB. A trial marked “Not run” has no timing data.
