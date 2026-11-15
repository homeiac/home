# Runbook: Recover the SOPS age key (new or lost laptop)

**Use this when:** `sops -d` fails with "failed to get the data key" / "no identity matched", or you are
on a new machine, or `~/.config/sops/age/keys.txt` is missing.

**The key:** one age key. Its public key is the recipient in `.sops.yaml`:
`age1uwvq3llqjt666t4ckls9wv44wcpxxwlu8svqwx5kc7v76hncj94qg3tsna`.
It decrypts every `*.sops.yaml` in this public repo. Flux uses the same key from the cluster.

## Where copies of the key live

| # | Copy | Needs | Restore command |
|---|---|---|---|
| A | **Google Drive** and **OneDrive**: `homelab-recovery/sops-age-key.txt.age` (passphrase-encrypted) | a browser + the escrow passphrase (password manager) | `scripts/sops/restore-age-key.sh --from-file <download>` |
| B | K8s secret `flux-system/sops-age` (key `age.agekey`) | SSH as root to pumped-piglet | `scripts/sops/restore-age-key.sh --from-cluster` |
| C | Crucible on pve: `/mnt/crucible-storage/secrets/sops/age.key` | SSH as root to pve | `scripts/sops/restore-age-key.sh --from-crucible` |

**Which one:** if this machine can SSH to the Proxmox hosts, use **B** (or C). If not — e.g. the laptop
that held the SSH key is gone — use **A**. Every path runs the same checks before installing.

## Steps (copy A — no homelab access needed)

1. Get the repo and tools:
   ```bash
   git clone https://github.com/homeiac/home && cd home
   brew install age sops            # Linux: install age + sops from your package manager / GitHub releases
   ```
2. In a browser, sign in to Google Drive (or OneDrive), open the folder `homelab-recovery/`, and
   download `sops-age-key.txt.age`. (`RECOVERY-README.txt` next to it has the expected sha256.)
3. Optional integrity check: `shasum -a 256 ~/Downloads/sops-age-key.txt.age` matches the README.
4. Restore (asks for the escrow passphrase):
   ```bash
   ./scripts/sops/restore-age-key.sh --from-file ~/Downloads/sops-age-key.txt.age
   ```
   It decrypts to a temp dir, checks the public key matches `.sops.yaml`, test-decrypts a committed
   secret, then installs `~/.config/sops/age/keys.txt` (0600). It refuses to overwrite a *different*
   existing key unless you pass `--force` (the old one is kept as `.bak-<time>`).
5. Confirm: `sops -d gitops/clusters/homelab/apps/samba/secrets/samba-users.sops.yaml >/dev/null && echo OK`
6. Delete the download: `rm ~/Downloads/sops-age-key.txt.age`.

## Steps (copy B or C — homelab reachable)

```bash
./scripts/sops/restore-age-key.sh --from-cluster     # or --from-crucible
```
Override hosts if IPs changed: `K3S_HOST=root@<pumped-piglet> CRUCIBLE_HOST=root@<pve>`.

## After recovering on a new laptop: regain SSH to the hosts

The escrow holds **only** the age key. The SSH key for the Proxmox hosts was on the old laptop. To get
back in: open the Proxmox web UI of any host (`https://<host>:8006`, user `root@pam`, root password from
your password manager) → node → **Shell** → append the new laptop's public key to
`/root/.ssh/authorized_keys` (Proxmox syncs `/etc/pve/priv/authorized_keys` across the cluster).
Then `scripts/crucible/sync-secrets-to-crucible.sh` to refresh the Crucible copy.

## Keeping the escrow current

- **Create / refresh** (interactive, you choose the passphrase):
  `scripts/sops/escrow-age-key-to-cloud.sh`
- **Check it's still there** (read-only, no passphrase): `scripts/sops/escrow-age-key-to-cloud.sh --verify`
- **If the key is ever rotated:** re-run the escrow, `scripts/crucible/sync-secrets-to-crucible.sh`, and
  update the cluster secret (`scripts/k3s/setup-sops-encryption.sh`).
- The nightly cloud backup also copies `homelab-recovery/` into the homelab backup (still encrypted).

## If every copy is lost

The encrypted secrets in git cannot be decrypted. Generate a new key
(`scripts/k3s/setup-sops-encryption.sh`), update `.sops.yaml`, and re-create each secret from its source
(each `*.sops.yaml` names its creating script in `kustomization.yaml` comments).

Story and design: `docs/blog/2026-11-15-the-key-that-unlocks-everything.md`
