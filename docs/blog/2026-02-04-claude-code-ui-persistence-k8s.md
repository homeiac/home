# Why Your AI Coding Agent Keeps Forgetting Who You Are (And How to Fix It)

**Date**: February 4, 2026
**Author**: Claude + Human collaboration
**Tags**: kubernetes, k8s, persistence, pvc, claude-code, devpod, coder, init-container, stateful-workloads

---

## The Problem: Death by a Thousand Logins

You deploy an AI coding agent (Claude Code UI, in our case) to Kubernetes. It works. You authenticate. You start working. Then the pod restarts -- maybe a node drain, maybe OOMKill, maybe Flux reconciled a new image -- and you're greeted with:

```
Missing API key · Run /login
```

Again.

Every. Single. Time.

This isn't a Claude-specific problem. It's the fundamental tension between Kubernetes wanting pods to be ephemeral and developer tools needing state. IDE servers (code-server, VS Code Server), DevPod, Coder, Jupyter -- they all hit the same wall. The home directory is where auth tokens, CLI configs, shell history, and SSH keys live. Lose the home directory, lose your session.

## The Naive Approaches (And Why They Fail)

### Attempt 1: Mount Just the Auth DB

Our first try was obvious: the Claude CLI stores its auth state in `~/.claude/auth.db`. Just mount a PVC at `~/.claude/`:

```yaml
volumeMounts:
  - name: claude-data
    mountPath: /home/claude/.claude
```

Problem: The Claude CLI *also* reads `~/.claude.json` (a config file in the home directory root, not inside `.claude/`). And `~/.local/share/claude/` holds the CLI binary and version info. And `~/.ssh/` needs to persist for git operations. We were playing whack-a-mole with mount paths.

### Attempt 2: Symlinks

Next idea: keep one PVC and create symlinks for each file the CLI expects:

```bash
ln -sf /persistent/.claude.json /home/claude/.claude.json
ln -sf /persistent/auth.db /home/claude/.claude/auth.db
```

Problem: The native CLI installer writes files atomically (write temp file, rename). Symlinks pointing at a PVC break this because the rename crosses filesystem boundaries. The installer silently fails, and you're back to `/login`.

### Attempt 3: ConfigMap / Secret Injection

Mount the auth token as a Kubernetes Secret:

```yaml
env:
  - name: CLAUDE_API_KEY
    valueFrom:
      secretKeyRef:
        name: claude-auth
        key: token
```

Problem: The Claude Code UI doesn't use a simple API key. It has an OAuth flow that produces session tokens stored in a SQLite database. You can't reduce this to a single environment variable.

## The Solution: Persist the Entire Home Directory

The pattern that actually works comes from DevPod and Coder: **mount the PVC at the user's home directory**. Not at a subdirectory. Not with symlinks. The whole thing.

```
Before (broken):
  PVC → /home/claude/.claude/    (misses ~/.claude.json, ~/.local/, ~/.ssh/)

After (works):
  PVC → /home/claude/            (catches everything)
```

But this creates a new problem: on first boot, the PVC is empty. The container image ships files in `/home/claude/` (like `.bashrc`, `.profile`, tool configs), but mounting a PVC over that directory hides them completely.

## The Init Container Strategy

The fix is a multi-phase init container that seeds the PVC from the container image on first run, then preserves user state on subsequent restarts:

```
Pod Lifecycle
=============

Init Container (runs as root)
  |
  Phase 1: First run?
  |  YES → cp -a /home/claude/. /mnt/home/   (seed from image)
  |         touch /mnt/home/.home-initialized
  |  NO  → Phase 2
  |
  Phase 2: Image updated?
  |  → Copy new files from image that don't exist on PVC
  |  → Never overwrite user-modified files
  |
  Phase 3: Auth DB
  |  → Copy auth.db from image if PVC copy is empty
  |
  Phase 4: SSH keys
  |  → Copy keys from Kubernetes Secrets to PVC
  |  → Set permissions (700 dir, 600 private key)
  |  → Generate SSH config
  |
  Phase 5: Projects
  |  → Clone/update repos from configmap list
  |
  Phase 6: Environment
  |  → Copy .env from SOPS-encrypted secret
  |
  Main Container (runs as uid 1001)
    → Home directory is fully populated
    → Auth persists across restarts
    → SSH keys are in place
    → Projects are cloned
```

The key detail is the PVC mount path:

```yaml
# Init container mounts PVC at /mnt/home (not /home/claude)
# so the IMAGE's /home/claude is still readable for seeding
initContainers:
  - name: init-home
    volumeMounts:
      - name: claude-home
        mountPath: /mnt/home        # PVC here

# Main container mounts PVC at /home/claude
# This IS the user's home directory now
containers:
  - name: claudecodeui
    volumeMounts:
      - name: claude-home
        mountPath: /home/claude      # PVC here
```

The init container sees the image's `/home/claude` (for copying defaults) and the PVC at `/mnt/home` (for writing). The main container sees the PVC at `/home/claude` (fully populated).

## Phase 2: Image Updates Without Data Loss

The trickiest part is handling image updates. When we ship a new container image with updated tooling or configs, those new files need to appear on the PVC without destroying the user's existing data:

```bash
# Phase 2: Merge new files from image updates
cd /home/claude
find . -type f 2>/dev/null | while read f; do
  if [ ! -e "/mnt/home/$f" ]; then
    mkdir -p "/mnt/home/$(dirname "$f")"
    cp -a "$f" "/mnt/home/$f"
    echo "Added new file from image: $f"
  fi
done
```

The rule is simple: if a file exists on the PVC, the user's version wins. If a file exists in the image but not on the PVC, it gets copied over. This handles:

- New tools added to the image
- New default configs shipped with updates
- User customizations preserved across upgrades

What it doesn't handle (intentionally): if we ship a *fix* to an existing config file, it won't overwrite the user's copy. For those cases, the migration section at the top of the init script handles explicit data transformations.

## Migration: Old Layout to New Layout

When changing the PVC mount point, you need a one-time migration for existing data. Our old layout had the PVC at `~/.claude/` with files at the PVC root. The new layout has the PVC at `~/` with files under `.claude/`:

```bash
# Old: PVC root had auth.db, ssh/, .env directly
# New: These live under .claude/ on the PVC
if [ -f /mnt/home/auth.db ] && [ ! -f /mnt/home/.home-initialized ]; then
  echo "Migrating PVC from old layout to new layout..."
  mkdir -p /mnt/home/.claude
  for item in auth.db ssh project-config.json .env; do
    if [ -e "/mnt/home/$item" ]; then
      mv "/mnt/home/$item" "/mnt/home/.claude/$item"
    fi
  done
fi
```

The guard condition (`auth.db at root` AND `no .home-initialized flag`) ensures this only runs once and only on PVCs that have the old layout.

## Two PVCs: Home and Projects

We use two separate PVCs:

```yaml
volumes:
  - name: claude-home
    persistentVolumeClaim:
      claimName: claude-data-blue      # Home directory state
  - name: claude-projects
    persistentVolumeClaim:
      claimName: claude-projects-blue   # Git repositories
```

Why separate them?

1. **Different lifecycle**: Home directory state is user config. Projects are git repos that can be re-cloned. You might want to wipe projects without losing auth.
2. **Different sizing**: Git repos can grow large. Home directory state is small. Separate PVCs let you size each independently.
3. **Blue/green deploys**: We run blue/green deployments. The `-blue` suffix lets us create a `-green` deployment with its own PVCs for testing, then swap.

The mount order matters in the main container:

```yaml
volumeMounts:
  - name: claude-home
    mountPath: /home/claude           # Mounted first
  - name: claude-projects
    mountPath: /home/claude/projects  # Mounted over subdirectory
```

Kubernetes handles nested mounts correctly. The projects PVC overlays the `projects/` subdirectory within the home PVC.

## What Persists (And What Doesn't)

After implementing this pattern, here's what survives a pod restart:

| Persists (PVC) | Regenerated (init container) |
|---|---|
| `~/.claude.json` (CLI config) | SSH keys (from K8s Secrets) |
| `~/.claude/auth.db` (session tokens) | SSH config (generated) |
| `~/.local/share/claude/` (CLI binary) | `.env` (from SOPS Secret) |
| `~/.bashrc`, `~/.profile` (shell config) | `known_hosts` (scanned at boot) |
| Shell history | Git repo updates (fetch + reset) |
| Any user-created files | |

The distinction: PVC data is the source of truth for user state. Secrets and ConfigMaps are the source of truth for credentials. The init container reconciles them on every boot.

## The Proof

```
$ kubectl delete pod -n claudecodeui claudecodeui-blue-xxx
pod "claudecodeui-blue-xxx" deleted

# Pod restarts...

$ # Open Claude Code UI
# No login prompt. Session restored. Shell history intact.
```

## Lessons Learned

**1. Don't try to enumerate what needs persisting.** We wasted three commits trying to mount individual paths (`~/.claude/`, then adding `~/.claude.json`, then `~/.local/share/`). Every CLI update could add a new path. Mount the whole home directory.

**2. The DevPod/Coder pattern exists for a reason.** This isn't a novel problem. Dev environment platforms solved it years ago: PVC at home, init container for seeding, merge logic for updates.

**3. Init containers should be idempotent.** Every phase checks whether it needs to run. First boot seeds. Subsequent boots merge. Migrations check guard conditions. You can delete the pod 100 times and the init container does the right thing each time.

**4. Separate concerns into PVCs.** Mixing ephemeral project data with persistent user state in one PVC creates awkward tradeoffs on cleanup and sizing.

**5. The commit history tells the story.** Our path to this solution:

```
d3e0820 fix: symlink Claude CLI credentials for native installer
35be877 fix: mount Claude CLI credentials directory from PVC
6fbd230 fix: remove broken symlink approach for Claude CLI credentials
5096b94 fix: persist entire home directory on PVC (DevPod/Coder pattern)
```

Four commits. Three "fix" prefixes. Each one a lesson in why partial persistence doesn't work.

## Applying This Pattern to Your Own Workloads

This isn't specific to Claude Code UI. Any stateful developer tool running in Kubernetes benefits from the same approach:

1. **PVC at the home directory** -- not at individual config paths
2. **Init container seeds from image** -- so the PVC isn't empty on first boot
3. **Merge logic for updates** -- new image files appear without overwriting user data
4. **Credentials from Secrets** -- refreshed on every boot, not persisted as user data
5. **Guard conditions on migrations** -- so layout changes are safe and idempotent

The alternative is what we had before: a developer tool that forgets who you are every time Kubernetes does its job.

## Files Reference

| File | Purpose |
|------|---------|
| `gitops/clusters/homelab/apps/claudecodeui/blue/deployment-blue.yaml` | Deployment with init container and PVC mounts |
| `gitops/clusters/homelab/apps/claudecodeui/blue/pvc-blue.yaml` | PVC definitions for home and projects |
| `docs/blog/2026-02-03-github-ssh-access-k8s-pods.md` | Related: SSH key persistence pattern |
