# Live Bonsai dispatch tuning

The summary worker polls `bonsai-dispatch-policy.json` from the preview Git branch at queue-read boundaries. It checks at most once every 30 seconds. A changed policy takes effect after its outstanding requests finish. Git fetch failures retain the latest valid settings.

- `mode` sets `batch` or `continuous`. Continuous mode fetches more work when a slot needs it while other requests are still in flight.
- `page_size` sets the number of items per queue read while the Mac is available. Zero selects four items per available slot, with a minimum of one Parquet batch.
- `mac_routing` sets `fifo` or `photo-first`. The latter sends the first available photo to the Mac and gives the RTX a better chance to pick up videos.

Push a change to one setting at a time. In Grafana, note the **Bonsai dispatch policy applied** time and watch the two-minute rate, GPU slot occupancy and Mac availability. Compare a full window after the applied time to an earlier window with both GPUs available. Check media mix as well as throughput. A comparison can be saved with:

```bash
CB_HOST=root@<piglet> python3 scripts/knowledge-index/measure-bonsai-dispatch.py \
  --before <baseline-window-end-UTC> --after <candidate-window-end-UTC> \
  --minutes 10 > /private/tmp/bonsai-trial.json
```

The report uses the same Prometheus counters as Grafana, then verifies saved rows and media mix directly in Parquet. Its GPU rate excludes cache and Luna. If a trial hurts throughput or leaves more slots idle for a comparable mix, restore the previous policy in Git and verify the reported policy and rate again.
