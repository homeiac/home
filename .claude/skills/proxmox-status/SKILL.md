---
name: proxmox-status
description: Check Proxmox cluster status including quorum, node health, and VM/CT summary
disable-model-invocation: true
allowed-tools: Bash(ssh:*), Bash(bash scripts/proxmox/check-cluster-status.sh:*), Bash(./scripts/proxmox/check-cluster-status.sh:*)
---

# Check Proxmox Cluster Status

Run the cluster status script and present the results:

```bash
./scripts/proxmox/check-cluster-status.sh
```

After running, summarize:
1. Cluster quorum state (quorate or not, how many nodes voting)
2. Any offline nodes
3. Node resource usage — flag any nodes with RAM above 90% or CPU above 80%
4. Any stopped VMs/CTs
5. Overall cluster health assessment
