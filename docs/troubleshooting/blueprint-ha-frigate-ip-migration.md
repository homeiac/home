# Blueprint: Home Assistant Frigate IP Migration

**Date**: December 2025
**Last Used**: 2025-12-13
**Status**: Active

---

## Problem Statement

Home Assistant Frigate integration pointing to wrong K8s service IP:
- `frigate-coral` service (192.168.4.83) has no running pods
- `frigate` service (192.168.4.82) is the active instance with Coral TPU

**Impact**: HA loses Frigate events, cameras, and face recognition.

---

## Architecture

```
K8s Cluster (k3s-vm-still-fawn)
├── frigate deployment (app=frigate)
│   └── Pod: frigate-* (RUNNING)
│       └── Coral TPU: 28ms inference
│
├── Services:
│   ├── frigate: 192.168.4.82:5000 ← CORRECT
│   └── frigate-coral: 192.168.4.83:5000 ← NO PODS
│
Home Assistant (192.168.4.240)
└── Frigate Integration
    └── URL: 192.168.4.XX:5000
```

---

## Pre-Flight Checks

| Check | Command | Expected |
|-------|---------|----------|
| Find running Frigate | `kubectl get pods -n frigate` | Pod with STATUS=Running |
| Get correct service IP | `kubectl get svc -n frigate` | LoadBalancer EXTERNAL-IP |
| Test service endpoint | `curl http://IP:5000/api/stats` | JSON with detectors |
| Current HA config | Via QEMU guest exec | Current URL |

---

## Fix Steps

### Step 1: Identify correct IP
```bash
KUBECONFIG=~/kubeconfig kubectl get svc -n frigate -o wide
# Find service with running pods behind it
```

### Step 2: Run migration script
```bash
./scripts/frigate/update-ha-frigate-url.sh "OLD_URL" "NEW_URL"
```

The script:
1. Shows current config via QEMU
2. Creates timestamped backup
3. Updates URL with sed
4. Verifies change
5. Restarts HA
6. Waits for HA to come back

---

## Verification

```bash
./scripts/frigate/check-ha-frigate-integration.sh
```

Expected:
- Frigate entities present (sensor.frigate_*)
- Frigate cameras detected
- Coral inference speed showing

---

## Rollback

```bash
./scripts/ha-frigate-migration/rollback-ha-frigate-url.sh
```

The script:
1. Finds the most recent backup automatically
2. Shows current vs backup URLs for confirmation
3. Restores the backup
4. Restarts HA and waits for it to come back
5. Verifies the rollback

---

## Common Mistakes

1. **Stale service**: Using old frigate-coral IP when pods moved
2. **DNS before ready**: Using hostname when DNS not configured
3. **No backup**: Config corruption without backup

---

## Scripts

| Script | Purpose |
|--------|---------|
| `update-ha-frigate-url.sh` | Automated URL migration via QEMU |
| `rollback-ha-frigate-url.sh` | Rollback to previous backup |
| `check-ha-frigate-integration.sh` | Verify HA integration status |
| `verify-frigate-k8s.sh` | Health check K8s Frigate |
| `99-validate-deliverables.sh` | Validate documentation |

---

## Security Constraints

- No secrets in scripts (uses .env file)
- QEMU guest agent access controlled via Proxmox
- Backup before any modification
