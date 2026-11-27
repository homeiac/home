# The Key That Unlocks Everything: Making Sure a Dead Laptop Can't Lock You Out of Your Homelab

**Date:** 2026-11-15
**Tags:** sops, age, gitops, secrets, disaster-recovery, homelab, backup

> My homelab keeps its secrets in a public Git repo, encrypted with SOPS and one age key. That's a
> great pattern right up until the laptop holding the key dies. I had three copies of the key and
> realized two of them were behind a door whose only key was… on the laptop.

## TL;DR

- With SOPS + age, **one private key** decrypts every secret in your GitOps repo. Lose every copy and
  your committed secrets are unrecoverable noise.
- Count your copies by **what you need to reach them**, not by how many there are. Mine: laptop, a
  Kubernetes secret, and a homelab storage box. The last two need SSH, and the SSH key was on the laptop.
- Fix: a **passphrase-encrypted** copy in **two different clouds** (Google Drive + OneDrive), reachable
  from any browser, plus **one restore script** that verifies the key before installing it, plus a
  **runbook** that an AI assistant or future-you can follow without guessing.

## The setup (aliases)

| Alias | What it is |
|---|---|
| `<laptop>` | Where `~/.config/sops/age/keys.txt` lives and where you run `sops` |
| `<cluster>` | K3s + Flux; Flux decrypts SOPS secrets with the same key stored as secret `flux-system/sops-age` |
| `<secrets-box>` | A homelab storage location you already sync secrets to |
| `<backup-host>` | Any always-on homelab box with `rclone` remotes for Google Drive and OneDrive |

## The audit: "how many copies do I have, really?"

| Copy | What you need to reach it | Survives "laptop gone"? |
|---|---|---|
| `<laptop>:~/.config/sops/age/keys.txt` | the laptop | ❌ by definition |
| K8s secret `flux-system/sops-age` | SSH to a cluster host → `kubectl` | ⚠️ only if *another* machine has SSH access |
| `<secrets-box>` | SSH to the host | ⚠️ same |

Three copies, one shared dependency. That's a single point of failure dressed up as redundancy.

## Design decisions

1. **Offsite and browser-reachable.** Google Drive *and* OneDrive, so one account lockout isn't fatal.
2. **Never upload the raw key.** The repo is public; the key in a cloud account means a phished cloud
   password = every homelab secret. So the key is wrapped with `age -p` (scrypt passphrase). The
   passphrase lives in a password manager, which you already have to be able to recover anyway.
3. **Prove the passphrase before uploading.** The script decrypts its own output and compares it
   with the original before anything leaves the machine. A typo'd passphrase discovered during a
   disaster is the worst possible time.
4. **Verify the upload byte-for-byte**, from both clouds, by downloading and hashing.
5. **Restore = verify, then install.** Whatever the source, the restore script checks the candidate
   (a) is an age key, (b) has the public key listed in `.sops.yaml`, (c) actually decrypts a real
   committed secret — and only then writes `keys.txt`. It refuses to overwrite a different key.
6. **One obvious entry point.** A runbook, linked from the repo's `CLAUDE.md`, so an AI coding session
   on a fresh laptop goes straight to the right procedure instead of "helpfully" generating a new key
   (which would orphan every committed secret).

## Step by step: build it

### 1. Make the escrow (once, interactive)

```bash
./scripts/sops/escrow-age-key-to-cloud.sh
```
What happens:
```text
Encrypting ~/.config/sops/age/keys.txt (public key age1…).
Choose a strong passphrase and SAVE IT IN YOUR PASSWORD MANAGER now.
Enter passphrase: ********
Confirm passphrase: ********
Type the passphrase once more to prove the file decrypts:
Enter passphrase: ********
Round-trip OK.
Uploading to gdrive:homelab-recovery/
Uploading to onedrive:homelab-recovery/
Verifying uploads
  gdrive:   homelab-recovery/sops-age-key.txt.age sha256=…
  onedrive: homelab-recovery/sops-age-key.txt.age sha256=…
OK: escrow present and identical in gdrive onedrive
```
The upload goes through `rclone` on `<backup-host>` (the encrypted bytes are streamed over SSH), so
the laptop needs no cloud credentials. Next to the key, a `RECOVERY-README.txt` (no secrets) says what
the file is, its sha256, the public key it must match, and the four restore commands.

### 2. Check it occasionally (read-only)

```bash
./scripts/sops/escrow-age-key-to-cloud.sh --verify
```
No passphrase needed: it confirms both cloud copies exist, are identical, and are age files.

### 3. Restore on a new machine

```bash
git clone https://github.com/<you>/<repo> && cd <repo>
brew install age sops
# browser: download homelab-recovery/sops-age-key.txt.age from Drive or OneDrive
./scripts/sops/restore-age-key.sh --from-file ~/Downloads/sops-age-key.txt.age
```
```text
Decrypting … (type the escrow passphrase from your password manager):
Candidate public key: age1…
Verified: decrypts gitops/…/homelab-env.sops.yaml
Installed ~/.config/sops/age/keys.txt (0600).
```
If the homelab is reachable, the same script restores from the other copies:
`--from-cluster` (Kubernetes secret) or `--from-crucible` (`<secrets-box>`), with the same checks.

### 4. Get SSH back

The escrow intentionally holds only the age key. On Proxmox, the web UI (root + password from the
password manager) has a shell; append the new laptop's public key to `/root/.ssh/authorized_keys`,
which Proxmox shares across the cluster (`/etc/pve/priv/authorized_keys`).

## Gotchas I hit building this

- **"Same key" isn't "same file".** My three copies had identical secret keys but different
  `# created:` comment lines, so a byte comparison said "different key" and refused to restore.
  Compare the `AGE-SECRET-KEY-1…` line (or the derived public key), not the file.
- **`git ls-files '*.sops.yaml'` matches `.sops.yaml` itself** — the config file. Pick a test file that
  actually contains `ENC[AES256_GCM`.
- **Don't let automation "fix" a missing key by generating one.** A new key decrypts nothing that's
  already committed. Say so in `CLAUDE.md`/your README in one line.

## Checklist

- [ ] Escrow created; passphrase saved in the password manager *and* tested by the round-trip
- [ ] `--verify` passes for both clouds
- [ ] Restore tested into a scratch path: `SOPS_AGE_KEY_FILE=/tmp/x/keys.txt ./scripts/sops/restore-age-key.sh --from-cluster`
- [ ] Runbook linked from the repo's top-level instructions
- [ ] You know how to regain SSH without the old laptop

Runbook: [`docs/runbooks/sops-age-key-recovery.md`](https://github.com/homeiac/home/blob/master/docs/runbooks/sops-age-key-recovery.md)
