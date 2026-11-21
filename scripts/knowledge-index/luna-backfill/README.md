# Luna submission worker

Piglet owns the work queue, the $250 estimated-cost ledger and the Luna Parquet dataset. The Git policy chooses the host that submits to Enterprise Codex. The Mac and still-fawn use the same worker code.

## Prepare still-fawn

From the pinned Git revision, run `CB_HOST=root@<piglet> python3 install.py --prepare-only`. Then run `python3 install-still-fawn.py --runner <still-fawn IP> --piglet <piglet IP>` using the repository inventory. The installer verifies the pinned Codex release digest, creates an unprivileged Linux account, tests its restricted SSH connection to Piglet and enables the systemd timer. The runner SSH key and Codex sign-in live under `/var/lib/ki-luna` on still-fawn. The Piglet SSH account can invoke only the ledger bridge from the still-fawn address.

Sign in interactively on still-fawn under the service account by running `sudo -u ki-luna -H /opt/knowledge-index/luna-backfill/bin/codex login --device-auth`. Complete the browser step with the intended Enterprise workspace. The timer checks login status before executing the worker.

## Cut over

Push `enabled: false` in `policy.json` and wait for the existing Mac batch to finish. Verify there are zero sent and reserved leases on Piglet before unloading the Mac launch agent. Push `runner: still-fawn` and `enabled: true`, then start the service or let the timer pick up the change. Verify the runner metric reports still-fawn and that the persisted caption count advances. The Mac worker loaded before runner selection was added defaults to the Mac and must be unloaded before enabling still-fawn.

The service allocates no GPU on still-fawn. It submits to Enterprise Codex with the saved context and writes through the same Piglet ledger.
