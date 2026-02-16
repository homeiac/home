# GitOps for Non-GitOps: Deploying to Bare Metal Hosts Without Ansible or Terraform

*How I use Kubernetes Jobs to deploy scripts to Proxmox hosts, keeping everything in Git without the complexity of traditional configuration management tools.*

## The Problem

I have a homelab with Proxmox hosts running services that can't (or shouldn't) run in Kubernetes:
- NUT (Network UPS Tools) for UPS monitoring - needs direct USB access
- Host-level monitoring agents
- Hardware-specific scripts

The traditional solutions are:
- **Ansible**: Powerful but complex. Playbooks, inventories, vaults, idempotency concerns, Python dependencies.
- **Terraform**: Great for provisioning, awkward for configuration management.
- **Shell scripts + cron**: Works but not GitOps. Changes aren't tracked, no audit trail.

I wanted something simpler: **scripts in Git that automatically deploy to hosts when I push changes.**

## The Solution: Host Script Deployer Pattern

The idea is simple:
1. Scripts and configs live in Git
2. Docker image bakes them in
3. K8s Job SSHs to host and deploys them
4. Push to Git → image builds → Job runs → host updated

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
                              ▼ update image tag, reconcile
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
│  /etc/cron.d/           # Local scheduled tasks                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Implementation

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

## The Workflow

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

3. **CI builds new image**
   ```
   ghcr.io/myorg/pve-nut:abc1234 → ghcr.io/myorg/pve-nut:def5678
   ```

4. **Update image tag in GitOps**
   ```bash
   # Edit gitops/.../job-deploy.yaml
   # Change image: ghcr.io/myorg/pve-nut:def5678
   git commit -m "deploy: update nut to def5678"
   git push
   ```

5. **Delete old Job, reconcile Flux**
   ```bash
   kubectl delete job nut-deploy -n monitoring
   flux reconcile kustomization flux-system --with-source
   ```

6. **Job runs, host is updated**
   ```
   [2024-02-16 19:32:35] Deployment complete!
   [2024-02-16 19:32:35] Scripts deployed to: /opt/nut/scripts/
   ```

## Optional: Flux Image Automation

If you install Flux's image-reflector-controller and image-automation-controller, you can automate step 4:

```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImagePolicy
metadata:
  name: pve-nut
spec:
  imageRepositoryRef:
    name: pve-nut
  filterTags:
    pattern: '^[a-f0-9]{7}$'  # Match SHA tags only
  policy:
    alphabetical:
      order: desc
```

Then Flux automatically commits image tag updates. I chose not to use this (yet) to keep the setup simpler.

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

## Conclusion

You don't need Ansible or Terraform to GitOps your hosts. A Docker image with scripts, a K8s Job with SSH access, and a CI pipeline gives you:

- **Everything in Git** - scripts, configs, deployment manifests
- **Clear audit trail** - git log shows what changed when
- **Simple tooling** - Bash, Docker, K8s (things you already know)
- **Unified workflow** - same git push → deploy cycle as your apps

The complexity is proportional to the problem. For "put these files on that host and restart a service", this is enough.

---

*This post describes the setup I use for NUT UPS monitoring in my homelab. The full implementation is in my [home repo](https://github.com/homeiac/home/tree/master/scripts/pve-nut).*
