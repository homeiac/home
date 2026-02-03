# GitHub SSH Access from Kubernetes Pods: The Right Way

**Date**: February 3, 2026
**Author**: Claude + Human collaboration
**Tags**: kubernetes, k8s, ssh, github, git, gitops, sops, secrets, flux, pod, authentication

---

## The Problem: HTTPS+PAT is a Crutch

Most guides for accessing private GitHub repos from Kubernetes pods suggest injecting a Personal Access Token into the HTTPS clone URL:

```bash
git clone https://${GH_TOKEN}@github.com/org/repo.git
```

This works for cloning, but breaks down fast:

- **Push doesn't work** without extra credential helpers
- The PAT leaks into `git remote -v` output unless you scrub it after clone
- `git pull`, `git fetch`, `git push` all need the token re-injected or a credential store
- Rotating the token means updating every pod that uses it

SSH keys solve all of these. One key, one setup, and `git clone`, `pull`, `push`, `fetch` all just work.

## Architecture

```
Pod Startup Flow
================

1. SOPS-encrypted Secret in Git
   (safe to commit - only values encrypted)
         |
         v
2. Flux decrypts at deploy time
   (age key stored in K8s secret)
         |
         v
3. Init container copies keys to PVC
   (survives pod restarts)
         |
         v
4. Main container uses SSH for git
   (GIT_SSH_COMMAND points to config)
```

The key insight: store SSH keys as a SOPS-encrypted Kubernetes Secret. Flux decrypts it automatically. An init container copies the keys to a PVC-backed directory with correct permissions. The main container references them via `GIT_SSH_COMMAND`.

## Step 1: Generate the SSH Key and Encrypt It

Create a script that generates an ED25519 key pair, wraps it in a Kubernetes Secret YAML, and encrypts with SOPS:

```bash
#!/bin/bash
set -euo pipefail

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Generate key pair
ssh-keygen -t ed25519 -C "mypod@cluster" -f "$TMPDIR/id_ed25519" -N "" -q

PRIVATE_KEY=$(cat "$TMPDIR/id_ed25519")
PUBLIC_KEY=$(cat "$TMPDIR/id_ed25519.pub")

# Build the K8s Secret YAML
cat > "$TMPDIR/secret.yaml" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: github-ssh-key
  namespace: myapp
type: Opaque
stringData:
  id_ed25519: |
$(echo "$PRIVATE_KEY" | sed 's/^/    /')
  id_ed25519.pub: "$PUBLIC_KEY"
EOF

# Encrypt and move to GitOps repo
cp "$TMPDIR/secret.yaml" gitops/apps/myapp/secrets/github-ssh-key.sops.yaml
sops --encrypt --in-place gitops/apps/myapp/secrets/github-ssh-key.sops.yaml

# Output the public key so you can register it on GitHub
echo "$PUBLIC_KEY"
```

The encrypted file is safe to commit. SOPS only encrypts the `stringData` values -- metadata stays readable for git diffs.

## Step 2: Register the Public Key on GitHub

Take the public key output from step 1 and add it to GitHub. With `gh` CLI:

```bash
gh ssh-key add /path/to/key.pub --title "mypod@cluster"
```

Or manually at https://github.com/settings/keys.

For an org-owned deploy key (read/write to a single repo), use:

```bash
gh repo deploy-key add /path/to/key.pub --repo org/repo --title "mypod" --allow-write
```

## Step 3: ConfigMap for GitHub Host Keys

Don't skip `known_hosts`. Without it you'll get either an interactive prompt (which hangs in a container) or you'll need `StrictHostKeyChecking=no` (which defeats the point of SSH).

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: github-known-hosts
  namespace: myapp
data:
  known_hosts: |
    github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl
    github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=
    github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=
```

Get the latest keys from `ssh-keyscan github.com` if these are stale.

## Step 4: The Init Container

The init container runs as root to fix file permissions, then the main container runs as a non-root user. This is the critical wiring:

```yaml
initContainers:
  - name: init-ssh
    image: alpine/git:latest
    securityContext:
      runAsUser: 0
    command:
      - sh
      - -c
      - |
        SSH_DIR="/data/ssh"
        mkdir -p "$SSH_DIR"

        # Copy keys from mounted secret
        if [ -f /ssh-secret/id_ed25519 ]; then
          cp /ssh-secret/id_ed25519 "$SSH_DIR/id_ed25519"
          cp /ssh-secret/id_ed25519.pub "$SSH_DIR/id_ed25519.pub"
          chmod 700 "$SSH_DIR"
          chmod 600 "$SSH_DIR/id_ed25519"
          chmod 644 "$SSH_DIR/id_ed25519.pub"
        fi

        # Copy known_hosts from configmap
        if [ -f /ssh-known-hosts/known_hosts ]; then
          cp /ssh-known-hosts/known_hosts "$SSH_DIR/known_hosts"
          chmod 644 "$SSH_DIR/known_hosts"
        fi

        # Generate SSH config
        cat > "$SSH_DIR/config" <<'SSHEOF'
        Host github.com
          HostName github.com
          User git
          IdentityFile /home/app/.data/ssh/id_ed25519
          UserKnownHostsFile /home/app/.data/ssh/known_hosts
          StrictHostKeyChecking yes
        SSHEOF
        sed -i 's/^        //' "$SSH_DIR/config"
        chmod 600 "$SSH_DIR/config"

        # Fix ownership (1000 = app user in main container)
        chown -R 1000:1000 "$SSH_DIR"
    volumeMounts:
      - name: app-data
        mountPath: /data
      - name: github-ssh-key
        mountPath: /ssh-secret
        readOnly: true
      - name: github-known-hosts
        mountPath: /ssh-known-hosts
        readOnly: true
```

Why copy to a PVC instead of mounting the secret directly?

1. **Permissions**: Kubernetes secret mounts are world-readable by default. SSH requires `600`.
2. **Persistence**: The PVC survives pod restarts. No re-setup needed.
3. **Mutability**: You can add `known_hosts` entries at runtime (e.g., scanning additional hosts).

## Step 5: Main Container Configuration

Two environment variables wire everything up:

```yaml
containers:
  - name: app
    env:
      - name: GIT_SSH_COMMAND
        value: "ssh -F /home/app/.data/ssh/config"
      - name: GIT_AUTHOR_NAME
        value: "my-bot"
      - name: GIT_COMMITTER_NAME
        value: "my-bot"
      - name: GIT_AUTHOR_EMAIL
        value: "noreply@example.com"
      - name: GIT_COMMITTER_EMAIL
        value: "noreply@example.com"
    volumeMounts:
      - name: app-data
        mountPath: /home/app/.data
```

`GIT_SSH_COMMAND` tells git to use your custom SSH config. Every git operation -- clone, fetch, pull, push -- uses this automatically.

For plain `ssh` commands (not through git), symlink `~/.ssh` to the same directory in your init container:

```bash
ln -sf /home/app/.data/ssh /home/app/.ssh
chown -h 1000:1000 /home/app/.ssh
```

## Step 6: Volume Definitions

```yaml
volumes:
  - name: app-data
    persistentVolumeClaim:
      claimName: app-data
  - name: github-ssh-key
    secret:
      secretName: github-ssh-key
      optional: true
      defaultMode: 0600
  - name: github-known-hosts
    configMap:
      name: github-known-hosts
      optional: true
```

`optional: true` lets the pod start even if the secret doesn't exist yet. Useful for bootstrapping.

## Step 7: Clone via SSH in the Init Container

With SSH configured, the init container can clone directly:

```bash
export GIT_SSH_COMMAND="ssh -F $SSH_DIR/config"

if [ ! -d "$CLONE_DIR/.git" ]; then
  git clone git@github.com:org/repo.git "$CLONE_DIR"
else
  git -C "$CLONE_DIR" fetch origin
  git -C "$CLONE_DIR" reset --hard origin/main
fi
```

No PAT injection. No credential scrubbing. The remote URL stays clean:

```
$ git remote -v
origin  git@github.com:org/repo.git (fetch)
origin  git@github.com:org/repo.git (push)
```

And push just works:

```
$ git push origin main
Enumerating objects: 5, done.
...
```

## The SOPS Encryption Layer

The whole thing hinges on SOPS keeping the private key safe in git. Here's what the encrypted file looks like:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: github-ssh-key
  namespace: myapp
type: Opaque
stringData:
  id_ed25519: ENC[AES256_GCM,data:longbase64string...,tag:...,type:str]
  id_ed25519.pub: ENC[AES256_GCM,data:shortbase64...,tag:...,type:str]
sops:
  age:
    - recipient: age1abc...xyz
      enc: |
        -----BEGIN AGE ENCRYPTED FILE-----
        ...
        -----END AGE ENCRYPTED FILE-----
```

Metadata is plaintext (so git diffs make sense). Only `stringData` values are encrypted. Flux has the age private key as a cluster secret and decrypts automatically during reconciliation.

Your `.sops.yaml` at the repo root controls this:

```yaml
creation_rules:
  - path_regex: .*.yaml
    encrypted_regex: ^(data|stringData)$
    age: age1yourpublickeyhere
```

## Common Pitfalls

**1. Forgetting `known_hosts`**

Without it, SSH prompts for host verification interactively. In a container with no TTY, this just hangs forever. Always include GitHub's host keys via a ConfigMap.

**2. Wrong file permissions**

SSH is picky. The private key must be `600`, the `.ssh` directory must be `700`. Kubernetes secret volume mounts default to `644` which SSH rejects. That's why the init container copies to a PVC.

**3. Using `pull --ff-only` on restarts**

If the pod has local commits (or the remote was force-pushed), `git pull --ff-only` fails. Use `fetch` + `reset --hard` in the init container instead. The PVC preserves the working directory across restarts.

**4. Forgetting `safe.directory`**

If the init container clones as root but the main container runs as uid 1000, git complains about ownership mismatch. Fix with:

```bash
git config --global --add safe.directory '*'
```

**5. Not making the secret `optional: true`**

If the secret doesn't exist yet and isn't optional, the pod won't start at all. Use `optional: true` so you can deploy the app first and add the secret later.

## End-to-End Automation

Wrap the whole workflow in one script:

```
deploy-github-ssh-secret.sh
  |
  +-- gh auth token | setup-github-ssh-secret.sh
  |     +-- ssh-keygen (generate key pair)
  |     +-- build K8s Secret YAML
  |     +-- sops --encrypt (encrypt via age)
  |     +-- output public key to stdout
  |
  +-- gh ssh-key add (register pubkey on GitHub)
  +-- git add + commit + push (SOPS file only)
  +-- flux reconcile (trigger deployment)
  +-- kubectl rollout status (wait for pod)
  +-- verify-github-auth.sh (test from inside pod)
```

One command. No manual steps. No copy-pasting keys between terminals.

## Summary

| Component | Purpose |
|-----------|---------|
| ED25519 key pair | Authentication to GitHub |
| SOPS-encrypted K8s Secret | Safe storage in git |
| Flux decryption | Automatic secret deployment |
| Init container | Copy keys to PVC with correct permissions |
| `GIT_SSH_COMMAND` env var | Tell git to use your SSH config |
| `~/.ssh` symlink | Make plain `ssh` commands work too |
| `known_hosts` ConfigMap | Prevent interactive host verification |
| `optional: true` on volumes | Graceful bootstrapping |

The HTTPS+PAT approach is fine for read-only clones. But if your pod needs to push, pull, and manage branches -- SSH keys are the right tool. SOPS makes them safe to store in GitOps.
