# fun-bedbug Thermal Management Runbook

## Hardware

| Component | Details |
|-----------|---------|
| Model | ATOPNUC MA90 |
| CPU | AMD A9-9400 APU (dual-core Bristol Ridge, ~2016) |
| TDP | 15W |
| Cooling | Internal fan (no RPM monitoring/PWM) |
| Role | K3s quorum-only node (VMID 114) |

## Thermal Thresholds

| Threshold | Temperature |
|-----------|-------------|
| Normal | < 70°C |
| High | 70°C |
| Critical | 100°C |

## Diagnosis

### Check Current Temperature
```bash
ssh root@fun-bedbug.maas "sensors | grep -E 'temp1|edge'"
```

### Check VM CPU Load
```bash
ssh root@fun-bedbug.maas "qm guest exec 114 -- top -bn1 | head -12"
```

### Check Host CPU Load
```bash
ssh root@fun-bedbug.maas "top -bn1 | head -15"
```

## Mitigations Applied

### 1. Reduced VM to 1 vCPU (2026-01-18)

The K3s VM was consuming 88% CPU with 2 vCPUs on a 2-core host. Reduced to 1 vCPU since this is a quorum-only node.

**Config**: `gitops/clusters/homelab/instances/k3s-vm-fun-bedbug.yaml`

```yaml
cpu:
  - cores: 1
    type: host
```

### 2. Excluded from DaemonSets (2026-01-18)

Added node label to exclude from CPU-heavy monitoring DaemonSets:

```bash
kubectl label node k3s-vm-fun-bedbug node-role.homelab/quorum-only=true
```

**Excluded DaemonSets**:
- `netdata-child` (default namespace) - saved ~25% CPU
- `gpu-operator-node-feature-discovery-worker` (gpu-operator namespace) - saved ~17% CPU

Both DaemonSets patched with nodeAffinity:
```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: node-role.homelab/quorum-only
              operator: DoesNotExist
```

### 3. External Cooling (Recommended)

Add a 120mm USB fan pointed at the case vents. Expected improvement: 5-10°C.

## Results

### Phase 1: vCPU Reduction (2026-01-18)

| Metric | Before | After |
|--------|--------|-------|
| vCPUs | 2 | 1 |
| Load Average | 2.90 | 1.04 |
| CPU Idle | 27% | 50% |
| Temperature | 92°C | 89-90°C |

### Phase 2: Thermal Paste Replacement (2026-01-26)

| Metric | Before | After |
|--------|--------|-------|
| Temperature (idle) | 89-90°C | ~50°C |
| Temperature (VM running) | 92°C+ | **54.5°C** |
| Improvement | - | **-37.5°C** |

The original thermal paste was dried out after years of operation. Replacement with fresh paste dramatically improved thermal performance.

## Completed Improvements

1. ~~External USB fan~~ - Not needed after thermal paste replacement
2. **Dust cleaning** - Done 2026-01-26
3. **Thermal paste** - Replaced 2026-01-26, dramatic improvement

## Future Improvements

1. **D-Bus monitoring** - Add check for socket existence after reboot (see RCA)

## Re-enabling DaemonSets

If you need to run netdata/NFD on this node again:

```bash
# Remove the exclusion label
kubectl label node k3s-vm-fun-bedbug node-role.homelab/quorum-only-

# Pods will automatically schedule on next reconciliation
```

## Related

- Crossplane VM config: `gitops/clusters/homelab/instances/k3s-vm-fun-bedbug.yaml`
- K3s cluster config: `proxmox/homelab/config/k3s.yaml`
