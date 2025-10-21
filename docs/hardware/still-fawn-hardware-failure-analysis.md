# Still-Fawn Hardware Failure Analysis

## Failure Summary
- **Date**: October 6, 2025
- **Node**: still-fawn (Intel Core i5-4460, 32GB RAM upgrade)
- **Status**: Complete system failure - hardware shutdown, no network response
- **Total Failures**: 3+ spontaneous shutdowns during k3s recovery operations
- **Root Cause**: Power supply instability, cannot handle increased load

## Chronology of Events

### Initial State (Pre-Failure)
- **Hardware**: Intel Core i5-4460, 24GB → 32GB RAM upgrade
- **Workload**: k3s Kubernetes node, Proxmox VMs, stable operation
- **Power Supply**: Aging unit from 2014 hardware generation

### Failure Sequence

#### Failure 1: Memory Overcommit
- **Time**: During RAM upgrade implementation
- **Trigger**: Allocated 38GB to VMs exceeding 32GB physical RAM
- **Memory Allocation**: k3s VM (20GB) + PBS (6GB) + other VMs (12GB) = 38GB
- **Result**: System degradation, forced VM shutdown corrupted k3s etcd

#### Failure 2: First Hardware Shutdown
- **Time**: During k3s node recovery operations
- **Context**: Attempting to rejoin still-fawn node to cluster using k3sup
- **Status**: Still-fawn.maas became unreachable (100% packet loss)
- **Recovery**: Manual system restart required

#### Failure 3: Second Hardware Shutdown
- **Time**: During continued k3s recovery
- **Context**: System appeared stable, k3s services starting
- **Pattern**: Spontaneous shutdown during moderate load operations
- **Memory Config**: 24GB k3s VM + 2GB PBS = 26GB allocated (under 32GB limit)

#### Failure 4: Third Hardware Shutdown (Final)
- **Time**: After removing 8GB RAM module (back to 24GB total)
- **Context**: Testing theory that extra RAM was causing power draw issues
- **Result**: System still shut down spontaneously
- **Conclusion**: Power supply cannot handle normal operational load

### Current Status
```bash
# Network connectivity test
$ ping -c 3 still-fawn.maas
PING still-fawn.maas (192.168.4.17): 56 data bytes
Request timeout for icmp_seq 0
Request timeout for icmp_seq 1
--- still-fawn.maas ping statistics ---
3 packets transmitted, 0 packets received, 100.0% packet loss
```

## Hardware Analysis

### Power Supply Assessment
- **Generation**: 2014-era hardware (Intel i5-4460)
- **Age**: 11+ years of continuous operation
- **Load Characteristics**: 
  - RTX 3070 GPU passthrough (220W TDP)
  - k3s VM with 24GB RAM allocation
  - Multiple Proxmox containers
  - ZFS storage operations on 20TB array

### Failure Pattern Analysis
1. **Progressive Degradation**: Multiple shutdowns with increasing frequency
2. **Load Sensitivity**: Failures occur during:
   - Memory intensive operations
   - Kubernetes cluster operations
   - VM restart sequences
3. **Power Draw Correlation**: Even after RAM reduction, system cannot sustain normal load
4. **No Graceful Shutdown**: Abrupt power loss, no system logs or shutdown sequences

### Technical Diagnosis
- **Primary**: Power supply unit (PSU) failure under load
- **Secondary**: Possible motherboard power delivery issues
- **Ruled Out**: Memory issues (failures continued after RAM removal)

## Impact Assessment

### Immediate Impacts
- **k3s Cluster**: Reduced to 2 nodes (k3s-vm-chief-horse, k3s-vm-pve)
- **AI Workloads**: RTX 3070 GPU unavailable for Ollama, Stable Diffusion
- **Storage**: 20TB ZFS pool inaccessible
- **Monitoring**: Prometheus storage on still-fawn unavailable

### Service Dependencies
- **Ollama LLM Service**: Requires GPU node for inference
- **Stable Diffusion**: Requires RTX 3070 for image generation
- **Monitoring Stack**: Prometheus data on still-fawn storage
- **Development Environment**: Webtop container on still-fawn

## Hardware Replacement Requirements

### Minimum Specifications
- **CPU**: Modern multi-core (8+ cores recommended)
- **RAM**: 32GB+ DDR4/DDR5
- **GPU**: RTX 4060+ or equivalent for AI workloads
- **Storage**: NVMe SSD + HDD array capability
- **Power Supply**: 750W+ 80+ Gold certified for reliability

### Workload Requirements
- **AI Inference**: 8GB+ VRAM for 34B parameter models
- **Kubernetes**: Multi-VM hosting with 24GB+ allocation per VM
- **Storage**: ZFS pool support for 20TB+ arrays
- **Network**: Gigabit Ethernet for cluster communication

## Replacement Options Analysis

### Option 1: Best Buy RTX 4070 Ti Super System
- **Price**: $1,898
- **Specs**: Intel i9-14900KF, 64GB RAM, RTX 4070 Ti Super 16GB, 2TB SSD
- **Pros**: 16GB VRAM, proven availability, warranty
- **Cons**: Higher cost, Intel 14th gen potential issues

### Option 2: Amazon Refurbished RTX 5060 System
- **Price**: ~$1,400 (estimated)
- **Specs**: RTX 5060 8GB, varies by listing
- **Pros**: Lower cost, latest GPU architecture
- **Cons**: 8GB VRAM limitation, suspicious refurbished status for new release

### Option 3: Dell Workstation with Upgrade Path
- **Price**: $800-1,200 base + GPU upgrade
- **Specs**: Xeon processors, workstation reliability
- **Pros**: Professional grade, expansion capability
- **Cons**: Older platform, requires GPU purchase

## Recommendations

### Immediate Actions
1. **Power Down still-fawn**: Prevent further damage from power cycling
2. **Cluster Stabilization**: Ensure 2-node cluster remains operational
3. **Data Recovery Planning**: Prepare for potential disk recovery if needed

### Replacement Strategy
1. **Priority**: RTX 4070 Ti Super system for proven 16GB VRAM capability
2. **Alternative**: Wait for legitimate RTX 5060 Ti 16GB availability
3. **Budget Option**: Dell workstation + separate RTX 4060 Ti 16GB

### Migration Planning
1. **Data Migration**: ZFS pool transfer to new system
2. **VM Migration**: Export/import Proxmox VMs
3. **k3s Rejoin**: Use k3sup for clean cluster integration
4. **Service Restoration**: Prioritize Ollama and monitoring stack

## Lessons Learned

### Infrastructure Design
- **Power Supply**: Critical component for system stability
- **Hardware Age**: 10+ year systems require replacement planning
- **Load Testing**: Validate power delivery under full workload

### Operations
- **Graceful Degradation**: Need procedures for node loss scenarios
- **Backup Systems**: Critical services need redundant hosting
- **Monitoring**: Power/thermal monitoring for aging hardware

## Related Documentation
- [Still-Fawn RAM Upgrade Documentation](../infrastructure/still-fawn-ram-upgrade-32gb.md)
- [K3s Cluster Architecture](../architecture/kubernetes-architecture.md)
- [Hardware Replacement Procedures](../hardware/hardware-replacement-guide.md)

---

**Status**: Hardware Failed - Replacement Required  
**Next Action**: Hardware procurement decision  
**Documentation Date**: October 6, 2025  
**Maintainer**: Homelab Infrastructure Team