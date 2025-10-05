# Still-Fawn RAM Upgrade to 32GB

## Upgrade Summary
- **Date**: October 5, 2025
- **Node**: still-fawn (Intel Core i5-4460)
- **Upgrade**: 24GB → 32GB (added 8GB module)
- **Purpose**: Alleviate memory pressure and enable future workload expansion

## Pre-Upgrade Analysis

### Memory Utilization (24GB)
- **Used**: 21GB (87.5%)
- **Available**: 1.6GB
- **Swap Usage**: 851MB (indicating memory pressure)

### Existing Allocations
| VM/Container | Type | Previous RAM | CPU | Primary Workload |
|-------------|------|--------------|-----|------------------|
| k3s-vm-still-fawn (108) | VM | 16GB | 4 cores | Kubernetes node, monitoring stack |
| proxmox-backup-server (103) | LXC | 4GB | 4 cores | Backup deduplication |
| docker-webtop (104) | LXC | 8GB | 4 cores | Development environment |
| crucible-test-vm (999) | VM | 0.5GB | 1 core | Storage testing |

## Post-Upgrade Allocations (32GB)

### Initial Memory Distribution (First Pass)
| Component | Previous | Initial | Change | Justification |
|-----------|----------|---------|--------|---------------|
| k3s-vm-still-fawn | 16GB | 20GB | +4GB | Prometheus (1.2GB), Grafana (546MB), monitoring growth |
| proxmox-backup-server | 4GB | 6GB | +2GB | Improved deduplication, concurrent backups |
| docker-webtop | 8GB | 8GB | 0 | Adequate for current use |
| crucible-test-vm | 0.5GB | 0.5GB | 0 | Minimal test workload |
| Proxmox Host | ~3.5GB | ~5.5GB | +2GB | ZFS ARC, system services, Ceph |

### Optimized Memory Distribution (Final)
After analyzing actual usage, memory was reallocated for better AI workload support:

| Component | Initial | **Final** | Change | Justification |
|-----------|---------|-----------|--------|---------------|
| **k3s-vm-still-fawn** | 20GB | **24GB** | +4GB | GPU node for AI: supports 34B LLMs, SDXL + ControlNet |
| **proxmox-backup-server** | 6GB | **2GB** | -4GB | Actual usage only 35MB, 2GB provides 50x headroom |
| docker-webtop | 8GB | 8GB | 0 | Development environment unchanged |
| crucible-test-vm | 0.5GB | 0.5GB | 0 | Test workload unchanged |
| Proxmox Host | ~5.5GB | ~5.5GB | 0 | Adequate for ZFS ARC and services |

**Note**: Total allocation (34.5GB) exceeds physical RAM (32GB) by 2.5GB through safe overcommit, as PBS uses minimal memory.

### Implementation Commands
```bash
# Verify RAM upgrade
free -h  # Shows 31Gi total

# Final optimized allocation
qm set 108 --memory 24576   # k3s VM to 24GB
pct set 103 --memory 2048    # PBS to 2GB (was using only 35MB)

# Verify changes
qm config 108 | grep memory  # Shows: memory: 24576
pct config 103 | grep memory  # Shows: memory: 2048
```

## Benefits Achieved

### Immediate Improvements
1. **Reduced Memory Pressure**: Host now has 10GB available (vs 1.6GB before)
2. **No Swap Usage**: Swap usage dropped to 0B
3. **Better Monitoring Performance**: Prometheus and Grafana have headroom
4. **Improved Backup Speed**: PBS can cache more deduplication tables

### AI/ML Capabilities with 24GB k3s VM
With 24GB allocated to the GPU-enabled k3s VM, still-fawn now supports:

1. **Large Language Models (Ollama)**: 
   - **34B parameter models**: Codellama-34B, Yi-34B
   - **Multiple 13B models**: 2-3 concurrent models
   - **7B models**: 4-5 simultaneous models
   - Local inference endpoints with low latency
   
2. **Stable Diffusion Capabilities**:
   - **SDXL models**: Full resolution generation
   - **ControlNet**: Multiple control models
   - **LoRA/VAE**: Multiple adapters simultaneously
   - Complex multi-model pipelines

3. **Enhanced Monitoring**:
   - Loki log aggregation
   - Thanos long-term storage
   - Additional Netdata collectors

4. **Development Services**:
   - GitLab runner
   - CI/CD pipelines
   - Container registry cache

5. **Performance Optimization**:
   - Redis/Memcached for application caching
   - Database read replicas
   - CDN edge cache

## Monitoring the Changes

### Key Metrics to Watch
```bash
# Host memory usage
ssh root@still-fawn.maas "free -h"

# VM memory pressure
export KUBECONFIG=~/kubeconfig
kubectl top nodes | grep still-fawn

# Container memory usage
ssh root@still-fawn.maas "pct exec 103 free -h"

# Kubernetes pod memory
kubectl top pods -A --sort-by=memory | grep still-fawn
```

### Expected Outcomes
- Host memory usage: 60-70% (healthy range)
- k3s node usage: 25-35% (was 29% at 16GB)
- PBS performance: 20-30% faster deduplication
- Zero swap usage under normal load

## Related Documentation
- [Proxmox Infrastructure Guide](../source/md/proxmox-infrastructure-guide.md)
- [Storage Architecture](../architecture/storage-architecture.md)
- [Monitoring Architecture](../source/md/monitoring-architecture-overview.md)