# Luna submission worker

Piglet owns the work queue, the $250 estimated-cost ledger and the Luna Parquet dataset. The Git policy chooses the host that submits to Enterprise Codex. The Mac and still-fawn use the same worker code.

## Prepare still-fawn

From the pinned Git revision, run `CB_HOST=root@<piglet> python3 install.py --prepare-only`. Then run `python3 install-still-fawn.py --runner <still-fawn IP> --piglet <piglet IP>` using the repository inventory. The installer verifies the pinned Codex release digest, creates an unprivileged Linux account, tests its restricted SSH connection to Piglet and enables the systemd timer. The runner SSH key and Codex sign-in live under `/var/lib/ki-luna` on still-fawn. The Piglet SSH account can invoke only the ledger bridge from the still-fawn address.

Sign in interactively on still-fawn under the service account by running `sudo -u ki-luna -H /opt/knowledge-index/luna-backfill/bin/codex login --device-auth`. Complete the browser step with the intended Enterprise workspace. The timer checks login status before executing the worker.

## Cut over

Push `enabled: false` in `policy.json` and wait for the existing Mac batch to finish. Verify there are zero sent and reserved leases on Piglet before unloading the Mac launch agent. Push `runner: still-fawn` and `enabled: true`, then start the service or let the timer pick up the change. Verify the runner metric reports still-fawn and that the persisted caption count advances. The Mac worker loaded before runner selection was added defaults to the Mac and must be unloaded before enabling still-fawn.

The service allocates no GPU on still-fawn. It submits to Enterprise Codex with the saved context and writes through the same Piglet ledger.

## Measure a concurrency change

Set `parallel`, `batch_size`, and `frame_slots` in the Git policy. The worker reads each new commit between batches. The shared ledger supports up to 48 reservations per batch and the worker allows up to 20 concurrent tasks. The $250 budget includes reserved work and every settled request.

Read the service journal with `journalctl -u knowledge-index-luna.service -o cat --since <trial-start>` on still-fawn and pass it to `python3 scripts/knowledge-index/luna-backfill/measure.py`. It reports media mix, saved throughput, estimated cost per caption and preparation and model-response latency for each tier. On Nov 21, 4, 8 and 20 slots delivered approximately 31, 53 and 66 saves/min. At 20, frame preparation and time waiting for it took longer than the median model request. The samples had different photo/video mixes. Keep the current placement while Piglet preparation limits throughput.

The follow-up held request concurrency at 20. Four frame slots and 24-job batches saved 62.6/min. Six frame slots and 24-job batches saved 55.9/min. Four frame slots and 48-job batches saved 69.3/min. At a common 85% photo and 15% video mix, estimated cost was $0.000583 per caption with 24 jobs and $0.000581 with 48. Bonsai saved 112 and 128 photos in equal four-minute windows before and during the 48-job trial. These are sequential production samples. The production policy uses 20 request slots, four frame slots, and 48-job batches.
