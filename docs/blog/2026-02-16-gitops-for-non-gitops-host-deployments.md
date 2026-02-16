# Why Kubernetes Killed Ansible (You Just Haven't Noticed Yet)

**Date:** 2026-02-16
**Tags:** gitops, ansible, terraform, kubernetes, bare-metal, homelab, configuration-management, ssh, proxmox, automation, pyinfra, saltstack, daemonset, ansible-alternative

*Ansible is SSH + Python scripts with a YAML frontend. You already have something better.*

## The Dirty Secret

Ansible's value proposition was simple: "I'll make your server look like this desired state."

Docker said: "Just ship the desired state as an image."

For applications, Docker won completely. Nobody writes Ansible playbooks to install Node.js anymore. But for host configuration, Ansible survived—not because it's better, but because nobody realized Kubernetes already solves this problem.

Here's the thing: **if your hosts are Kubernetes nodes, you don't need Ansible at all.** And the handful of hosts that aren't in K8s? A simple Job + SSH pattern handles those without a 200MB Python framework.

## What Ansible Actually Does

Let's demystify this. When you run an Ansible playbook:

```yaml
- name: Install nginx
  apt:
    name: nginx
    state: present
```

Ansible:
1. Renders a Python script from the `apt` module
2. Base64 encodes it
3. SSHs to the host
4. Decodes and runs: `python3 /tmp/ansible-tmp-xxx/apt.py`
5. Parses JSON output
6. Deletes temp files

That's it. **SSH + Python scripts with extra steps.** The "modules" are just Python that gets copied over and executed.

You're paying for:
- Python on every target host
- YAML indentation hell
- Jinja2 templating quirks
- Galaxy dependency bloat
- 30-second startup times
- Ansible Tower at $50k+/year for a scheduler

In exchange for what? Cross-platform abstractions you don't use if all your hosts are Debian.

## The Two Worlds

Modern infrastructure has two types of hosts:

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   K8s Nodes: 50-500+ (98% of your hosts)                       │
│   └── Don't need Ansible. At all.                              │
│                                                                 │
│   Non-K8s Hosts: 3-10 (2% of your hosts)                       │
│   ├── Hypervisors (Proxmox, ESXi)                              │
│   ├── Network appliances                                        │
│   └── Bootstrap nodes                                           │
│   └── Simple SSH + scripts. No framework needed.               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

Ansible treats all 510 hosts the same: SSH keys, Python, inventory, credentials, Tower.

The smarter approach: **DaemonSets for K8s nodes (zero SSH, zero credentials), Jobs for the handful of bare-metal hosts.**

## Pattern 1: DaemonSet for K8s Nodes (The Ansible Killer)

For hosts that are Kubernetes nodes, you already have root access—the kubelet runs there. Use it:

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-configurator
  namespace: kube-system
spec:
  selector:
    matchLabels:
      app: node-configurator
  template:
    metadata:
      labels:
        app: node-configurator
    spec:
      hostPID: true
      hostNetwork: true
      tolerations:
        - operator: Exists  # Run on ALL nodes including masters
      containers:
        - name: configure
          image: ghcr.io/myorg/node-setup:v1.2.3
          securityContext:
            privileged: true
          volumeMounts:
            - name: host
              mountPath: /host
          command:
            - /bin/sh
            - -c
            - |
              chroot /host /bin/bash -c '
                # Install packages
                apt-get update && apt-get install -y htop iotop

                # Deploy configs
                cp /configs/sysctl.conf /etc/sysctl.d/99-custom.conf
                sysctl --system

                # Ensure services
                systemctl enable --now node-exporter
              '
              # Optionally: loop for continuous reconciliation
              sleep infinity
      volumes:
        - name: host
          hostPath:
            path: /
```

**No SSH. No credentials. No inventory. No Tower. No Python on targets.**

The pod runs directly on the node with `hostPath: /`. It *is* root on that machine. Update the image, K8s rolls it out. Done.

### Self-Healing Comes Free

```yaml
command:
  - /bin/sh
  - -c
  - |
    while true; do
      chroot /host /bin/bash -c '
        # Ensure config is correct
        diff -q /expected/app.conf /etc/app.conf || cp /expected/app.conf /etc/app.conf

        # Ensure service is running
        systemctl is-active myservice || systemctl start myservice
      '
      sleep 300
    done
```

Someone manually edits a config? Fixed in 5 minutes. Service crashes? Restarted. **Continuous state enforcement without Ansible re-runs.**

### Targeting Nodes (The "Roles" Problem)

Ansible has inventory groups. K8s has node selectors:

```yaml
# Target only GPU nodes
spec:
  template:
    spec:
      nodeSelector:
        node-type: gpu

# Or more complex targeting
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: role
                    operator: In
                    values: ["gpu", "ml-training"]
```

Yes, this is more verbose than Ansible's `hosts: gpu_nodes`. But you're trading one complexity (inventory files) for the same complexity (node labels) while **eliminating SSH, credentials, Tower, and Python dependencies.**

## Pattern 2: Jobs for Non-K8s Hosts (The Remaining 2%)

For hosts outside Kubernetes—hypervisors, network gear, bootstrap nodes—you need SSH. But you don't need Ansible:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GIT REPO                                     │
│  scripts/pve-nut/                                                    │
│  ├── Dockerfile                                                      │
│  ├── deploy.sh          # Orchestrator (runs in K8s)                │
│  ├── scripts/*.sh       # Scripts to deploy to host                 │
│  └── configs/           # Config files to deploy                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ git push triggers CI
┌─────────────────────────────────────────────────────────────────────┐
│                      CONTAINER REGISTRY                              │
│  ghcr.io/myorg/pve-nut:abc1234                                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ K8s Job runs
┌─────────────────────────────────────────────────────────────────────┐
│                         K8s JOB                                      │
│  - Mounts SSH key from Secret                                        │
│  - Runs deploy.sh                                                    │
│  - SCPs scripts/configs to host                                      │
│  - Restarts services as needed                                       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ SCP + SSH
┌─────────────────────────────────────────────────────────────────────┐
│                      PROXMOX HOST                                    │
│  /opt/nut/scripts/      # Deployed scripts                          │
│  /etc/nut/              # Deployed configs                          │
└─────────────────────────────────────────────────────────────────────┘
```

This is SSH + bash scripts. Same as Ansible underneath, minus the framework.

## Implementation (Job + SSH for Non-K8s Hosts)

### Directory Structure

```
scripts/pve-nut/
├── Dockerfile
├── deploy.sh
├── scripts/
│   ├── nut-notify.sh      # UPS event handler
│   ├── test-status.sh     # Health check
│   └── disaster-drill.sh  # Monthly SMS test
└── configs/
    ├── nut.conf
    ├── ups.conf
    └── upsmon.conf
```

### The Dockerfile

Minimal Alpine image with SSH client:

```dockerfile
FROM alpine:3.19@sha256:6baf43584bcb78f2e5847d1de515f23499913ac9f12bdf834811a3145eb11ca1

RUN apk add --no-cache openssh-client bash curl

WORKDIR /app
COPY deploy.sh /app/
COPY scripts/ /app/scripts/
COPY configs/ /app/configs/

RUN chmod +x /app/deploy.sh && \
    find /app/scripts -name "*.sh" -exec chmod +x {} \;

ENTRYPOINT ["/app/deploy.sh"]
```

Note the pinned SHA digest - no `latest` tags for reproducibility.

### The Deploy Script

The orchestrator that runs inside K8s and deploys to the host:

```bash
#!/bin/bash
set -e

HOST="${TARGET_HOST:?TARGET_HOST required}"
SSH_KEY="${SSH_KEY_PATH:-/ssh/id_rsa}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/nut}"
SSH_OPTS="-o StrictHostKeyChecking=no -i $SSH_KEY"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

log "Starting deployment to $HOST"

# Create directories
ssh $SSH_OPTS root@$HOST "mkdir -p $DEPLOY_DIR/{scripts,configs}"

# Deploy configs
for conf in /app/configs/*; do
    scp $SSH_OPTS "$conf" "root@$HOST:/etc/nut/"
    log "Deployed $(basename $conf)"
done

# Deploy scripts
for script in /app/scripts/*.sh; do
    scp $SSH_OPTS "$script" "root@$HOST:$DEPLOY_DIR/scripts/"
    ssh $SSH_OPTS root@$HOST "chmod +x $DEPLOY_DIR/scripts/$(basename $script)"
done

# Deploy secrets from environment
ssh $SSH_OPTS root@$HOST "cat > $DEPLOY_DIR/.env << EOF
SMS_GATEWAY_IP=${SMS_GATEWAY_IP:-}
SMS_GATEWAY_TOKEN=${SMS_GATEWAY_TOKEN:-}
EOF
chmod 600 $DEPLOY_DIR/.env"

# Setup local cron (recurring tasks stay on host, not K8s CronJob)
ssh $SSH_OPTS root@$HOST "cat > /etc/cron.d/nut-drill << 'EOF'
0 10 1-7 * 6 root [ \$(date +\%u) -eq 6 ] && $DEPLOY_DIR/scripts/disaster-drill.sh
EOF"

# Restart services
ssh $SSH_OPTS root@$HOST "systemctl restart nut-server nut-monitor"

log "Deployment complete!"
```

### The Kubernetes Job

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: nut-deploy
  namespace: monitoring
spec:
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: OnFailure
      imagePullSecrets:
        - name: ghcr-creds
      containers:
        - name: deploy
          image: ghcr.io/myorg/pve-nut:abc1234
          env:
            - name: TARGET_HOST
              value: "192.168.4.122"
          envFrom:
            - secretRef:
                name: sms-gateway-creds
          volumeMounts:
            - name: ssh-key
              mountPath: /ssh
              readOnly: true
      volumes:
        - name: ssh-key
          secret:
            secretName: pve-ssh-key
            defaultMode: 0600
```

### GitHub Actions

Build and push on changes to `scripts/pve-nut/`:

```yaml
name: Build PVE NUT Deployer

on:
  push:
    paths:
      - 'scripts/pve-nut/**'
    branches:
      - master

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/${{ github.repository_owner }}/pve-nut
          tags: type=sha,prefix=,format=short

      - uses: docker/build-push-action@v6
        with:
          context: scripts/pve-nut
          push: true
          tags: ${{ steps.meta.outputs.tags }}
```

## Key Design Decisions

### Why Jobs, Not CronJobs?

The old approach used hourly CronJobs to "sync" configs. Problems:
- Wasteful - runs even when nothing changed
- Slow feedback - changes take up to an hour
- No clear trigger - when did this config actually deploy?

Jobs run once when you update the image tag. Clear cause and effect.

### Why Local Crons for Recurring Tasks?

Some tasks need to run on a schedule (monthly disaster drills). You could use K8s CronJobs, but:
- They depend on K8s being healthy
- The whole point of a disaster drill is testing when infrastructure is DOWN
- Local crons on the host are simpler and more reliable for host-specific tasks

The deploy script sets up `/etc/cron.d/` entries on the host.

### Why Not Just Use Ansible?

Ansible is great. But for simple host deployments:

| Aspect | Ansible | Host Script Deployer |
|--------|---------|---------------------|
| Learning curve | Playbooks, roles, inventory, vault | Bash + Docker |
| Dependencies | Python, pip, ansible-galaxy | None (uses K8s) |
| Secrets | Ansible Vault or external | K8s Secrets (already have) |
| Audit trail | Separate from app GitOps | Same Git repo, same workflow |
| Trigger | Manual or separate CI | Push to Git |

For complex multi-host orchestration, use Ansible. For "deploy these scripts to this host", this pattern is simpler.

## The Real Comparison

| Aspect | DaemonSet + Job | Ansible + Tower |
|--------|-----------------|-----------------|
| **K8s nodes (500)** | 1 DaemonSet, no credentials | 500 SSH keys, inventory, Tower |
| **Bare metal (10)** | 10 SSH keys | 10 SSH keys (same) |
| **Central bottleneck** | None (K8s scheduler) | Tower (single point of failure) |
| **Credential management** | SOPS (already have) | Ansible Vault (another thing) |
| **Testing** | `docker run` locally | `--check` and pray |
| **Multi-team** | Each team owns their image | Shared Tower, shared playbooks |
| **Cost** | $0 (use existing K8s) | Tower license + infra |

### The Complexity Math

```
Ansible for 510 hosts:
├── 510 SSH keys to distribute
├── 510 hosts in inventory
├── Python on all targets
├── Tower/AWX cluster
├── Database for Tower
├── Load balancer for Tower
└── Backup for Tower state

DaemonSet + Job for 510 hosts:
├── 1 DaemonSet (500 K8s nodes) ─── zero credentials
├── 10 SSH keys (bare metal) ────── same as Ansible
└── Done
```

You eliminate 98% of credential management and all central infrastructure.

### The Testing Story

Ansible:
```bash
ansible-playbook site.yml --check   # Dry run (misses half the issues)
ansible-playbook site.yml --diff    # Shows changes (still runs against prod)
# Real testing = Molecule + Vagrant + prayer
```

Your pattern:
```bash
docker build -t my-deployer .
docker run -e TARGET_HOST=test-vm my-deployer
# Same image runs locally, in CI, in prod
```

### Multi-Team Reality

Team A writes a deployer. Team B runs it:

```yaml
# Team B doesn't care what's inside
spec:
  containers:
    - name: deploy
      image: ghcr.io/team-a/nut-deployer:v1.2.3  # Team A's problem
      env:
        - name: TARGET_HOST
          value: "192.168.4.122"                  # Team B's problem
```

Clear ownership. Clear interface. No "install Ansible 2.14 with these galaxy roles and hope the Python versions match."

### Nothing Stops You Using Ansible Inside

Here's the kicker: **your existing Ansible playbooks still work**:

```dockerfile
FROM alpine:3.19

RUN apk add --no-cache openssh-client ansible

COPY playbooks/ /app/playbooks/
COPY deploy.sh /app/

ENTRYPOINT ["/app/deploy.sh"]
```

```bash
# deploy.sh
ansible-playbook -i "$TARGET_HOST," playbooks/site.yml
```

The pattern is a **superset**. Use Ansible modules where they help. Use raw bash where they don't. The container doesn't care what's inside.

### Secrets Management

Secrets flow from K8s Secrets → environment variables → `.env` file on host:

```bash
# In deploy.sh
ssh $SSH_OPTS root@$HOST "cat > $DEPLOY_DIR/.env << EOF
SMS_GATEWAY_TOKEN=${SMS_GATEWAY_TOKEN:-}
EOF"

# In the actual script on the host
source /opt/nut/.env
curl -H "Authorization: $SMS_GATEWAY_TOKEN" ...
```

No secrets in Git. No separate vault. Uses the same K8s Secrets + SOPS encryption as everything else.

## The Workflow (Fully Automated)

The key insight: **Kubernetes Jobs are immutable**. When the image tag changes, Flux can't patch the existing Job—it fails with "spec.template: field is immutable."

The solution: Use a **separate Flux Kustomization with `force: true`** for the Job. This tells Flux to delete and recreate the Job when any immutable field changes.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FULLY AUTOMATED FLOW                               │
└─────────────────────────────────────────────────────────────────────────────┘

  1. PUSH CODE                    2. GHA BUILDS                3. IMAGE REPO SCANS
  ─────────────                   ─────────────                ───────────────────
  scripts/pve-nut/  ──push──►    ghcr.io/myorg/    ──scan──►   ImageRepository
  └── nut-notify.sh               pve-nut:def5678              "Found new tag!"
                                                                      │
                                                                      ▼
  6. JOB RUNS                     5. FLUX KUSTOMIZATION        4. IMAGE POLICY
  ───────────                     ─────────────────────        ────────────────
  Host is updated  ◄──create──   force: true                   "def5678 is latest"
  /opt/nut/scripts/              "Delete old Job,                    │
                                  create new one"              ▼
                                        ▲                ImageUpdateAutomation
                                        │                "Commit tag update"
                                        │                      │
                                        └──────────────────────┘
```

### Step 1: Flux Image Automation

Install the image automation controllers (add to gotk-components.yaml):

```bash
flux install --components-extra=image-reflector-controller,image-automation-controller --export > gotk-components.yaml
```

Create ImageRepository, ImagePolicy, and ImageUpdateAutomation:

```yaml
# flux-system/image-automation-pve-nut.yaml
---
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImageRepository
metadata:
  name: pve-nut
  namespace: flux-system
spec:
  image: ghcr.io/myorg/pve-nut
  interval: 5m
  secretRef:
    name: ghcr-creds  # For private registries
---
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImagePolicy
metadata:
  name: pve-nut
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: pve-nut
  filterTags:
    pattern: '^[a-f0-9]{7}$'  # Match only SHA tags (e.g., abc1234)
  policy:
    alphabetical:
      order: desc  # Newest SHA first
---
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImageUpdateAutomation
metadata:
  name: pve-nut
  namespace: flux-system
spec:
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: flux-system
  git:
    checkout:
      ref:
        branch: master
    commit:
      author:
        name: fluxcdbot
        email: fluxcd@homelab.local
      messageTemplate: "chore(flux): update pve-nut to {{range .Changed.Changes}}{{.NewValue}}{{end}}"
    push:
      branch: master
  update:
    path: ./gitops/clusters/homelab/infrastructure/nut-pve/deploy
    strategy: Setters
```

### Step 2: Add Image Policy Marker

In your Job manifest, add a marker comment so Flux knows where to update:

```yaml
# nut-pve/deploy/job-deploy.yaml
containers:
  - name: deploy
    image: ghcr.io/myorg/pve-nut:abc1234  # {"$imagepolicy": "flux-system:pve-nut"}
```

The comment `{"$imagepolicy": "flux-system:pve-nut"}` tells ImageUpdateAutomation to update this line when the policy resolves a new tag.

### Step 3: Separate Flux Kustomization with `force: true`

This is the critical piece. Create a **separate Flux Kustomization** just for the Job:

```yaml
# nut-pve-deploy/flux-kustomization.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: nut-pve-deploy
  namespace: flux-system
spec:
  interval: 5m
  path: ./gitops/clusters/homelab/infrastructure/nut-pve/deploy
  prune: true
  wait: true
  force: true  # <-- THE KEY: Recreates Job when image changes
  sourceRef:
    kind: GitRepository
    name: flux-system
  dependsOn:
    - name: flux-system  # Wait for secrets
```

When `force: true`:
1. Flux detects the Job spec changed (new image tag)
2. Flux **deletes** the old Job
3. Flux **creates** a new Job with the new image
4. Job runs, host is updated

**No manual deletion needed.**

### The Directory Structure

```
gitops/clusters/homelab/infrastructure/
├── nut-pve/                    # Secrets, monitoring, etc.
│   ├── kustomization.yaml
│   ├── secrets/
│   └── deploy/                 # Job lives here (separate path)
│       ├── kustomization.yaml
│       └── job-deploy.yaml
└── nut-pve-deploy/             # Flux Kustomization with force:true
    ├── kustomization.yaml
    └── flux-kustomization.yaml
```

The Job is in a **separate path** from other resources so `force: true` only affects the Job, not your secrets or services.

### The Complete Flow

1. **Edit scripts locally**
   ```bash
   vim scripts/pve-nut/scripts/nut-notify.sh
   ```

2. **Commit and push**
   ```bash
   git add scripts/pve-nut/
   git commit -m "fix: improve battery threshold logic"
   git push
   ```

3. **GHA builds new image** (automatic)
   ```
   ghcr.io/myorg/pve-nut:abc1234 → ghcr.io/myorg/pve-nut:def5678
   ```

4. **ImageRepository detects new tag** (automatic, every 5m)

5. **ImagePolicy selects it** (automatic)
   ```
   Latest: def5678
   ```

6. **ImageUpdateAutomation commits tag update** (automatic)
   ```
   chore(flux): update pve-nut to def5678
   ```

7. **Flux Kustomization (force:true) recreates Job** (automatic)
   ```
   Job nut-deploy deleted
   Job nut-deploy created
   ```

8. **Job runs, host is updated** (automatic)
   ```
   [2026-02-16 19:32:35] Deployment complete!
   ```

**Push code → host is updated. Zero manual steps.**

## Addressing the Weaknesses

The pattern has real limitations. Here's how I address them.

### Making Bash Idempotent

Ansible has built-in idempotency. In bash, you implement it manually:

```bash
# Directories - always idempotent
mkdir -p /opt/service

# Symlinks - idempotent with -sf
ln -sf /source /target

# Append only if not present
grep -qF "myline" /etc/config || echo "myline" >> /etc/config

# Package install - check first
dpkg -l | grep -q '^ii.*nginx ' || apt-get install -y nginx

# Systemd - already idempotent
systemctl enable --now nginx  # safe to run multiple times

# Config files - just overwrite (SCP is idempotent)
scp config.conf root@host:/etc/service/config.conf
```

The discipline is: every command must be safe to run twice. If it's not, add a guard condition.

### Drift Detection (Optional)

If someone manually edits a config on the host, this pattern won't detect it. For my homelab, I accept this. But if I needed drift detection, I'd add a check Job:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nut-drift-check
spec:
  schedule: "0 * * * *"  # Hourly
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: check
              image: ghcr.io/myorg/pve-nut:abc123
              command: ["/app/check-drift.sh"]
              # Compares current state to expected, alerts if different
```

The script would `ssh` to the host, `diff` the configs, and send an alert if they don't match. Push-based deployment, pull-based monitoring.

### Multi-Host Support

For multiple hosts, use an inventory ConfigMap:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: host-inventory
data:
  hosts.txt: |
    192.168.4.122
    192.168.4.123
    192.168.4.124
```

```bash
# In deploy.sh
while read HOST; do
  log "Deploying to $HOST"
  deploy_to_host "$HOST"
done < /inventory/hosts.txt
```

Still sequential, but handles multiple hosts. For parallel execution, you'd need something like GNU `parallel` or just... use Ansible.

### Rollback Strategy

Tag configs with the git SHA:

```bash
DEPLOY_VERSION=$(cat /app/VERSION)
ssh $SSH_OPTS root@$HOST "echo $DEPLOY_VERSION > $DEPLOY_DIR/.version"
```

To rollback, deploy the previous image:

```bash
PREVIOUS_SHA=$(git rev-parse HEAD~1)
# Update Job manifest to use ghcr.io/myorg/pve-nut:$PREVIOUS_SHA
kubectl delete job nut-deploy -n monitoring
flux reconcile kustomization flux-system --with-source
```

Not automatic, but traceable. Every deployed version is a git SHA that I can inspect.

## Reusing the Pattern

This pattern works for any "deploy stuff to a host" scenario:

```
scripts/pve-backup/      # Backup scripts for Proxmox
scripts/pve-monitoring/  # Custom monitoring agents
scripts/pve-gpu/         # GPU passthrough management
```

Each gets its own:
- Directory in `scripts/`
- GitHub Actions workflow
- K8s Job in GitOps

## Conclusion: Ansible Is a Solved Problem

Ansible was the right tool for 2010. Every server was a snowflake. You SSH'd in, ran Python scripts, hoped for idempotency.

Then Docker said "ship the whole environment" and Kubernetes said "here's a scheduler with root access to every node."

**For K8s nodes:** DaemonSets give you privileged access with zero credentials, self-healing reconciliation, and rolling updates. Ansible adds nothing.

**For bare metal:** A container with bash scripts over SSH does exactly what Ansible does, minus the framework overhead.

**For your existing playbooks:** Put them in a container and run them as a Job. The pattern is a superset.

### Why Ansible Persists

1. **Resume-driven development** - "Experience with Ansible" looks good
2. **Existing investment** - Companies have thousands of playbooks
3. **Fear of bash** - "Shell scripts don't scale" (they do)
4. **Vendor backing** - Red Hat sells Tower licenses

Not because SSH + scripts is insufficient.

### The Numbers

```
Your infrastructure:
├── K8s nodes: ~500 ────── DaemonSet (0 SSH keys, 0 inventory)
└── Bare metal: ~10 ────── Job + SSH (10 keys, same as Ansible)

Ansible complexity: O(n) for all hosts
This pattern:       O(1) for K8s + O(n) for the rest

You just eliminated 98% of credential management.
```

### The Real Question

It's not "can Ansible do more?" It can.

It's **"what's the cost of this complexity?"**

For configuring 500 K8s nodes, the cost of Ansible is: SSH keys everywhere, Python on every target, Tower infrastructure, inventory drift, central bottleneck.

The cost of a DaemonSet is: one YAML file.

---

*This post describes the fully automated GitOps setup I use for my homelab. DaemonSet for K8s node configuration, Job + SSH + Flux Image Automation for the Proxmox hosts. Push code, hosts are updated. Full implementation:*
- *[nut-pve deployer](https://github.com/homeiac/home/tree/master/gitops/clusters/homelab/infrastructure/nut-pve)*
- *[Flux image automation](https://github.com/homeiac/home/tree/master/gitops/clusters/homelab/flux-system/image-automation-pve-nut.yaml)*
- *[force:true Kustomization](https://github.com/homeiac/home/tree/master/gitops/clusters/homelab/infrastructure/nut-pve-deploy)*

## Further Reading

- [Ansible Alternatives (Spacelift)](https://spacelift.io/blog/ansible-alternatives) - comparison of configuration management tools
- [pyinfra](https://pyinfra.com/) - Python-based alternative that's "10x faster than Ansible"
- [Idempotent Bash Scripts](https://arslan.io/2019/07/03/how-to-write-idempotent-bash-scripts/) - techniques for writing safe-to-repeat scripts
- [shell-operator](https://github.com/flant/shell-operator) - if you want to build K8s operators in bash
- [mgmt](https://github.com/purpleidea/mgmt) - next-gen config management with real-time enforcement
