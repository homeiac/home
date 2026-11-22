# Caption worker: Git controls the host service

Flux applies a ConfigMap and a Job. The Job connects to the Proxmox host and installs
the caption code, settings and a permanent `knowledge-index-enrich.service`.
Systemd starts it at boot after the data mounts and restarts it if it exits.
A CronJob checks every five minutes and repairs drift. An unchanged deployment
does not restart the worker; dispatch-policy changes reload within 30 seconds.

The old worker was created with `systemd-run --collect`. Its unit disappeared at
the November 22 reboot. A surviving model override could not start a missing unit.

## Change or pause the worker

1. Edit `config.json` here (`enabled: false` pauses it), the canonical Python under
   `../enrichers/`, or `../bonsai-dispatch-policy.json`.
2. Run `python3 scripts/knowledge-index/caption-gitops/generate.py` from the repo.
3. Run the checks below, review, commit and push to the PR branch. The existing
   `photo-enrichment-preview` Flux source follows `codex/photo-enrichment-217`.
4. Inspect the `caption-worker-*` Job and `caption-worker-reconcile` CronJob in
   namespace `monitoring`. The host records its applied hash in
   `/opt/knowledge-index/caption-gitops/applied.json`.

The generated resources are under
`gitops/clusters/homelab/apps/photo-enrichment/caption-worker/`.
The Job and ConfigMap names include the bundle hash, so a new revision gets a new
rollout Job. Flux prunes the previous revision. A host lock serializes installers.
Before replacing anything, the installer backs up code, the unit and legacy
drop-ins under `/opt/knowledge-index/backups/caption-gitops-*`. Startup failure
restores the previous files and service state. Revert the Git change to roll back
an accepted revision permanently.

The model remains Bonsai, with two RTX requests and optional Mac assistance.
Keep `enricher=gemma4-e2b-p1`: this is the existing completed-work identity despite
its old name. Changing it would queue the library again. A process lock prevents
two local workers from writing this index at once. Queue selection skips successful
items with the same source, path, size and enricher; failed items remain retryable.

## One-time host access bootstrap

The existing Python environment, data mounts and `/etc/default/knowledge-index`
must already exist. `KI_OLLAMA_URL` stays on the host. This does not provision a
fresh host or reinstall its runtime dependencies.

After checking `proxmox/inventory.txt`, run:

```sh
CB_HOST=root@<inventory-host> python3 scripts/knowledge-index/caption-gitops/bootstrap.py
```

This backs up root's authorized keys, installs the fixed SSH entry point and adds
one dedicated key with a forced command, LAN/pod source restriction and forwarding
disabled. The encrypted Kubernetes credential is reused on reruns. Only SOPS
ciphertext is stored in Git. The key authorizes deployment of Python running as
root, so repository writes and the decrypted credential are privileged access.
The bootstrap does not start the worker; Flux's Job does that. Updates to the
bootstrap installer itself use `bootstrap.py --installer-only`, which leaves the
deployment key unchanged. A full bootstrap rerun needs the SOPS decryption identity
to reuse the encrypted key. No host Docker is needed.

## Check recovery and duplicates

```sh
python3 scripts/knowledge-index/caption-gitops/generate.py --check
python3 scripts/knowledge-index/caption-gitops/test_gitops.py  # requires DuckDB
kubectl kustomize gitops/clusters/homelab/apps/photo-enrichment/caption-worker >/dev/null
CB_HOST=root@<inventory-host> bash scripts/knowledge-index/caption-gitops/audit-host.sh snapshot
# After the rollout, and again after a worker restart:
CB_HOST=root@<inventory-host> bash scripts/knowledge-index/caption-gitops/audit-host.sh verify
CB_HOST=root@<inventory-host> bash scripts/knowledge-index/check-caption-health.sh
KUBECONFIG=~/kubeconfig bash scripts/knowledge-index/caption-gitops/check-flux.sh
# Optional controlled restart, then rerun the audit after new batches appear:
CB_HOST=root@<inventory-host> bash scripts/knowledge-index/caption-gitops/check-host.sh --restart
```

The audit snapshots completed Parquet filenames before recovery. It counts all
new successful rows and checks their identities against both prior output and
other new rows. It does not print photo names or descriptions. Existing historical
duplicates do not become new failures. The snapshot command refuses to overwrite
its baseline at `/var/tmp/caption-gitops-recovery-baseline.json`.

The service uses `RequiresMountsFor`, `WantedBy=multi-user.target`, and a 60-second
restart delay. Checking `systemctl is-enabled`, the permanent `FragmentPath`, a
fresh heartbeat and new Parquet after a service restart verifies recovery without
rebooting the Proxmox host or disturbing its other workloads.
