# Claude Code UI - K8s Deployment

Web interface for Claude Code, deployed to K8s with OAuth subscription auth.

## Prerequisites

- K8s cluster with Traefik ingress
- GitHub token with `write:packages` scope (for GHCR push)
- Claude Pro/Max subscription

## Quick Start

### 1. Build and Push Docker Image

```bash
# Set GitHub token
export GITHUB_TOKEN="ghp_..."

# Build and push
./scripts/claudecodeui/build-and-push.sh
```

### 2. Enable in GitOps

Edit `gitops/clusters/homelab/kustomization.yaml`:
```yaml
- apps/claudecodeui  # Uncomment this line
```

Commit and push:
```bash
git add gitops/
git commit -m "feat: enable claudecodeui deployment"
git push
```

### 3. Wait for Flux to Deploy

```bash
# Watch deployment
KUBECONFIG=~/kubeconfig kubectl get pods -n claudecodeui -w
```

### 4. Complete OAuth Login

```bash
# Exec into pod
KUBECONFIG=~/kubeconfig kubectl exec -it -n claudecodeui deploy/claudecodeui -- bash

# Run claude CLI to trigger OAuth
claude

# It will fail to open browser and print:
# "Open this URL in your browser: https://..."
# "Then enter the code: XXXX-XXXX"

# 1. Copy the URL, open in your browser
# 2. Log in with your Claude.ai account
# 3. Copy the code displayed
# 4. Paste it back in the terminal
```

### 5. Access Web UI

Add DNS override in OPNsense:
- Host: `claude`
- Domain: `app.homelab`
- IP: `192.168.4.50` (Traefik)

Then access: http://claude.app.homelab

## Architecture

```
Browser → Traefik (192.168.4.50) → claudecodeui:3001
                                        ↓
                                  Claude CLI
                                        ↓
                              ~/.claude (OAuth creds)
                                        ↓
                                  Anthropic API
```

## Persistence

Two PVCs:
- `claude-data` (10Gi): OAuth credentials in `~/.claude`
- `claude-projects` (50Gi): Project files

## Troubleshooting

### Re-authenticate
```bash
kubectl exec -it -n claudecodeui deploy/claudecodeui -- claude logout
kubectl exec -it -n claudecodeui deploy/claudecodeui -- claude
```

### Check logs
```bash
kubectl logs -n claudecodeui deploy/claudecodeui -f
```

### Verify ingress
```bash
kubectl get ingress -n claudecodeui
curl -v http://claude.app.homelab
```
