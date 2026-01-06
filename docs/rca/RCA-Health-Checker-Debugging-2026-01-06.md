# RCA: Frigate Health Checker Debugging Session

**Date:** 2026-01-06
**Duration:** ~45 minutes of unnecessary iteration
**Root Cause Category:** Process/Workflow gaps + Knowledge gaps

---

## Timeline of Failures

| Attempt | What Failed | Time Wasted | Root Cause |
|---------|-------------|-------------|------------|
| 1 | `bitnami/kubectl:1.28` doesn't exist | 5 min | Didn't verify image tag exists before committing |
| 2 | Tailscale exit node blocked local traffic | 10 min | Enabled exit node without understanding routing |
| 3 | `lachlanevenson/k8s-kubectl` has no bash | 5 min | Assumed alpine image has bash |
| 4 | `kubectl apply` changes reverted by Flux | 15 min | Forgot GitOps reconciliation overwrites manual changes |
| 5 | `grep -c` multi-line output | 5 min | Edge case in bash scripting |

**Total wasted time:** ~40 minutes

---

## Root Cause Analysis

### RC1: No Image Verification Before Commit

**What happened:**
- Original commit used `bitnami/kubectl:1.28`
- Tag doesn't exist (Bitnami only has `latest` + SHA digests)
- Discovered only after Flux deployed and pods failed

**Evidence:**
```
Failed to pull image "bitnami/kubectl:1.28": not found
```

**Why it happened:**
- I assumed semver tags exist without checking
- No pre-commit validation of container images

**Fix:**
```bash
# Before using any image tag, verify it exists:
curl -s "https://hub.docker.com/v2/repositories/ORG/REPO/tags?page_size=20" | jq -r '.results[].name'
```

**CLAUDE.md addition:**
```markdown
## Container Image Hygiene
Before using ANY container image in K8s manifests:
1. Verify the tag exists: `curl -s "https://hub.docker.com/v2/repositories/ORG/REPO/tags" | jq '.results[].name'`
2. Never use `latest` in production
3. For kubectl images, verify bash exists if script uses bash features
```

---

### RC2: Tailscale Exit Node Confusion

**What happened:**
- Cluster became unreachable (ping timeout to 192.168.4.x)
- I enabled Tailscale exit node thinking it would help
- Exit node actually BLOCKED local network traffic
- Spent 10 minutes debugging "network down"

**Evidence:**
```bash
# With exit node enabled - FAILS
ping 192.168.4.17  # timeout

# Without exit node - WORKS
ping 192.168.4.17  # 1.7ms
```

**Why it happened:**
- Didn't understand that exit nodes route ALL traffic through the exit node
- The exit node (ts-homelab-router) couldn't route back to my local 192.168.86.x network
- Should have checked: "Am I on the same LAN as the homelab?"

**The Right Mental Model:**
```
┌─────────────────────────────────────────────────────────────┐
│  Exit Node = ALL traffic goes through that node             │
│  Accept Routes = Only advertised subnets go through VPN     │
│                                                             │
│  If you're on 192.168.86.x (home WiFi) and homelab is on   │
│  192.168.4.x (wired LAN), you need routing, not exit node  │
└─────────────────────────────────────────────────────────────┘
```

**Fix:** Check network topology FIRST before changing Tailscale settings:
```bash
# What network am I on?
ifconfig en0 | grep "inet "

# Can I reach the target directly?
ping -c 1 192.168.4.17

# If yes: don't touch Tailscale
# If no: check if Tailscale advertises that route
tailscale status | grep 192.168.4
```

---

### RC3: Assumed Bash Exists in Alpine Image

**What happened:**
- Changed to `lachlanevenson/k8s-kubectl:v1.25.4`
- Pod failed: `/bin/bash: no such file or directory`
- Image is Alpine-based, only has `/bin/sh`

**Evidence:**
```
OCI runtime create failed: exec: "/bin/bash": stat /bin/bash: no such file or directory
```

**Why it happened:**
- Script uses bash features (`[[`, `(())`, arrays)
- Assumed all kubectl images have bash
- Didn't verify before selecting image

**The Right Approach:**
1. Check Dockerfile or image docs for base image
2. Alpine = `/bin/sh` only (unless bash explicitly installed)
3. Debian/Ubuntu = `/bin/bash` available
4. If script needs bash, verify: `docker run --rm IMAGE which bash`

**Good kubectl images with bash:**
- `dtzar/helm-kubectl:X.Y` - Alpine + bash installed
- `bitnami/kubectl:latest` - Has bash but no semver tags

---

### RC4: GitOps Overwrites Manual kubectl apply

**What happened:**
- Applied fixed CronJob with `kubectl apply`
- Verified: `kubectl get cronjob` showed new image
- Created job from CronJob
- Job used OLD image
- Repeated this 3-4 times before realizing Flux reverted changes

**Evidence:**
```bash
# I applied this:
kubectl apply -f cronjob-health.yaml  # image: dtzar/helm-kubectl:3.19

# But cluster showed:
kubectl get cronjob -o jsonpath='{..image}'
# bitnami/kubectl:1.28  <- Flux reverted to git state!
```

**Why it happened:**
- Flux reconciles every ~1 minute
- My manual apply was overwritten before I created the test job
- I forgot the fundamental GitOps principle: **git is the source of truth**

**The Right Workflow:**
```bash
# WRONG: Manual apply in GitOps environment
kubectl apply -f manifest.yaml  # Will be reverted!

# RIGHT: Commit → Push → Reconcile
git add manifest.yaml
git commit -m "fix: update image"
git push
flux reconcile kustomization flux-system --with-source
```

**CLAUDE.md addition:**
```markdown
## GitOps Workflow - NEVER FORGET
In this repo, Flux manages all K8s resources. Manual `kubectl apply` WILL BE REVERTED.

To apply changes:
1. Edit the YAML file
2. `git add && git commit && git push`
3. `flux reconcile kustomization flux-system --with-source`
4. Verify: `kubectl get <resource> -o yaml`

NEVER do `kubectl apply` expecting it to persist. It won't.
```

---

### RC5: grep -c Edge Case

**What happened:**
- `grep -c` returned `0\n0` instead of `0`
- Bash `[[` comparison failed with syntax error

**Evidence:**
```
Detection stuck events: 0
0 (threshold: 2)
/bin/bash: line 60: [[: 0
0: syntax error in expression
```

**Why it happened:**
- `echo "$LOGS"` had trailing content that caused grep to output multiple lines
- `grep -c` counts matches, but output format can vary

**Fix:**
```bash
# Before
STUCK_CT=$(echo "$LOGS" | grep -c "pattern" || echo 0)

# After - pipe through head -1 and set default
STUCK_CT=$(echo "$LOGS" | grep -c "pattern" 2>/dev/null | head -1 || echo 0)
STUCK_CT=${STUCK_CT:-0}
```

---

## Meta-Analysis: Why Did I Repeat Mistakes?

### Pattern 1: Test in Production Instead of Locally

I could have tested the container image locally:
```bash
docker run --rm dtzar/helm-kubectl:3.19 which bash
docker run --rm dtzar/helm-kubectl:3.19 bash -c 'echo "test"'
```

But I deployed to K8s first, waited for pod failure, then debugged.

### Pattern 2: Didn't Read Error Messages Carefully

The Flux labels were visible in `kubectl get cronjob -o yaml`:
```yaml
labels:
  kustomize.toolkit.fluxcd.io/name: flux-system
```

This should have reminded me: "Flux manages this resource!"

### Pattern 3: Assumed Instead of Verified

| Assumption | Reality |
|------------|---------|
| bitnami/kubectl has semver tags | Only `latest` + SHA |
| lachlanevenson has bash | Alpine, no bash |
| kubectl apply persists | Flux reverts in ~1 min |
| grep -c outputs clean integer | Can have newlines |

---

## Action Items

### Immediate (Add to CLAUDE.md)

1. **Container Image Checklist:**
   - Verify tag exists before using
   - Verify bash if script needs it
   - Never use `latest` in production

2. **GitOps Reminder:**
   - Manual `kubectl apply` = temporary
   - Always: commit → push → flux reconcile

3. **Network Debugging:**
   - Check local network first (`ifconfig`)
   - Don't change Tailscale without understanding current state

### Process Improvements

1. **Pre-commit hook for K8s manifests:**
   - Validate image tags exist
   - Could use `crane` or Docker Hub API

2. **Test container images locally first:**
   ```bash
   # Add to workflow before deploying
   docker run --rm IMAGE bash -c 'echo "bash works"'
   ```

---

## Lessons Learned

1. **GitOps means git is truth** - Never forget that manual changes are temporary
2. **Verify don't assume** - Check image tags, shells, network topology
3. **Read the labels** - `kustomize.toolkit.fluxcd.io` = Flux manages this
4. **Test locally first** - Docker run before K8s deploy
5. **Tailscale exit nodes block local traffic** - Use routes, not exit node, for same-LAN access

---

## Time Cost

- Actual debugging: ~15 minutes (legitimate investigation)
- Wasted on preventable issues: ~40 minutes
- **Efficiency ratio: 27%**

With the fixes above, this should have been a 15-minute task.
