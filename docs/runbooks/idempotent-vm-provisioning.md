# Idempotent VM Provisioning Runbook

**Last Updated:** 2025-11-12
**GitHub Issue:** #159

## Quick Start

```bash
cd /Users/10381054/code/home/proxmox/homelab
poetry run python -m homelab.main
```

## Common Scenarios

### Scenario 1: Fresh Setup
**Situation:** No VMs exist yet

**Command:**
```bash
poetry run python -m homelab.main
```

**What Happens:**
- Downloads Ubuntu cloud image
- Uploads to all nodes
- Creates VMs on each node
- Joins all VMs to k3s cluster

**Time:** ~10-15 minutes

---

### Scenario 2: Stuck VM (Original Issue)
**Situation:** VM stuck on boot, won't start

**Command:**
```bash
poetry run python -m homelab.main
```

**What Happens:**
- Detects VM is stopped/unhealthy
- Deletes stuck VM
- Recreates with proper config
- Joins to k3s cluster

**Time:** ~5-8 minutes for one VM

---

### Scenario 3: Add New Node
**Situation:** New Proxmox node added to cluster

**Steps:**
1. Add to `.env`:
   ```bash
   NODE_N=new-node-name
   STORAGE_N=local-zfs
   CPU_RATIO_N=0.8
   MEMORY_RATIO_N=0.8
   ```

2. Run provisioning:
   ```bash
   poetry run python -m homelab.main
   ```

**What Happens:**
- Detects new node in config
- Creates VM on new node
- Joins to k3s cluster

---

### Scenario 4: Existing VMs All Healthy
**Situation:** Running provisioning on already-provisioned infrastructure

**Command:**
```bash
poetry run python -m homelab.main
```

**What Happens:**
- Checks health of all VMs: ✅ healthy
- Checks cluster membership: ✅ already in cluster
- Skips all operations
- **Total time: <30 seconds**

---

## Troubleshooting

### Issue: SSL Certificate Errors
**Symptom:** `SSL routines::certificate verify failed`

**Resolution:** System automatically falls back to CLI commands via SSH. No action needed.

**Verification:**
```bash
# Check logs for "using CLI fallback" message
poetry run python -m homelab.main 2>&1 | grep "CLI fallback"
```

---

### Issue: K3s Join Fails
**Symptom:** VM created but not in cluster

**Check:**
1. Verify `K3S_EXISTING_NODE_IP` is set in `.env`
2. Verify SSH access to existing node:
   ```bash
   ssh ubuntu@192.168.4.212 'sudo cat /var/lib/rancher/k3s/server/node-token'
   ```

3. Manually check cluster:
   ```bash
   export KUBECONFIG=~/kubeconfig
   kubectl get nodes
   ```

**Recovery:** Fix `.env` and re-run provisioning

---

### Issue: VM Not Detected as Unhealthy
**Symptom:** VM clearly broken but not recreated

**Manual Check:**
```bash
ssh root@<node>.maas "qm status <vmid>"
```

**Current Health Detection:**
- ✅ Stopped VMs → recreated
- ✅ Paused VMs → recreated
- ✅ Running VMs → kept
- ⚠️ Unknown states → kept (safe default)

**Manual Override:**
```bash
cd proxmox/homelab
poetry run python scripts/delete_vm.py <node-name> <vmid>
poetry run python -m homelab.main
```

---

## Implementation Notes

**Health Check Logic:**
- Running VM = healthy (skip)
- Stopped VM = unhealthy (recreate)
- Paused VM = unhealthy (recreate)
- Unknown state = don't delete (safe)

**Network Validation:**
- Checks all bridges exist before VM creation
- Skips VM creation if bridge missing
- Example: Requires vmbr0 on all nodes

**K3s Join Logic:**
- Gets token from existing node once
- Reuses token for all new nodes
- Individual node failures don't stop workflow
- Skips join if K3S_EXISTING_NODE_IP not set

---

## Code References

**Main workflow:** `src/homelab/main.py:main()`
**Health checking:** `src/homelab/health_checker.py:VMHealthChecker`
**VM deletion:** `src/homelab/vm_manager.py:delete_vm()`
**K3s join:** `src/homelab/k3s_manager.py:K3sManager`

**Tests:** All modules have 100% test coverage in `tests/`

---

## Tags
vm-provisioning, proxmox, k3s, kubernetes, idempotent, infrastructure-as-code, homelab, automation
