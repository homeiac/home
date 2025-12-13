# Blueprint: K8s Workload Migration Between Nodes (with USB Hardware)

**Date**: December 2025
**Last Used**: 2025-12-13 (Frigate + Coral TPU: pumped-piglet → still-fawn)
**Status**: Validated with lessons learned

---

## Problem Statement

Migrating K8s workloads with USB hardware (like Coral TPU) between nodes requires:
1. USB passthrough reconfiguration at VM level
2. PVC handling (local-path storage is node-bound!)
3. GitOps manifest updates
4. Verification of hardware access

---

## CRITICAL PRE-FLIGHT CHECKS

**These were MISSED in the 2025-12-13 migration, causing 30+ minutes of debugging!**

### 1. SSH Connectivity to Target VM
```bash
# Check SSH first
ssh -o ConnectTimeout=5 ubuntu@k3s-vm-<target> "uptime"

# If SSH broken, have QEMU guest agent fallback:
ssh root@<proxmox-host>.maas "qm guest exec <VMID> -- <command>"
```
**Lesson**: Scripts 06-08 failed because SSH to K3s VMs was broken. Had to rewrite mid-migration.

### 2. PVC/PV Node Affinity (CRITICAL!)
```bash
# Check where PVs are bound
kubectl get pv -o custom-columns='NAME:.metadata.name,NODE:.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values[0]'
```

| Storage Class | Node Affinity | Migration Action |
|---------------|---------------|------------------|
| `local-path` | YES (node-bound) | **Must delete and recreate PVCs** |
| `nfs` | No | No action needed |
| `longhorn` | No | No action needed |

**Lesson**: Pod stuck in Pending for 15 minutes because PVs had node affinity to old node.

### 3. Secrets Verification
```bash
kubectl get secret -n <namespace>
```
Secrets are namespace-scoped, not node-scoped - they should work, but verify.

### 4. Hardware Requirements on Target
```bash
# Check USB devices on target host
ssh root@<target-host>.maas "lsusb | grep -E '<vendor-id>'"

# Check /dev/dri for GPU
ssh root@<target-host>.maas "ls -la /dev/dri/"
```

---

## Scripts Required

**Directory**: `scripts/<workload>/<migration-name>/`

| Script | Purpose | Notes |
|--------|---------|-------|
| `00-preflight-checks.sh` | Verify SSH, PVCs, secrets, hardware | **Run first!** |
| `01-remove-usb-from-source.sh` | Remove USB passthrough from source VM | |
| `02-remove-source-label.sh` | Remove K8s node label | |
| `03-check-hardware-on-host.sh` | Verify hardware on target host | |
| `04-add-usb-passthrough.sh` | Add USB passthrough to target VM | Include usb3=1 flag |
| `05-reboot-vm.sh` | Reboot target VM | |
| `06-wait-for-vm.sh` | Wait for VM online | **Use guest agent fallback!** |
| `07-check-hardware-in-vm.sh` | Verify hardware in VM | **Use guest agent!** |
| `08-install-drivers.sh` | Install drivers if needed | **Use guest agent!** |
| `09-label-node.sh` | Label K8s node | |
| `10-deploy-and-verify.sh` | Flux reconcile + verify | |
| `11-recreate-pvcs.sh` | **Delete and recreate PVCs** | **CRITICAL for local-path!** |

---

## Phase 0: Pre-Flight Checks

### 0.1 Script: `00-preflight-checks.sh`
```bash
#!/bin/bash
set -euo pipefail
export KUBECONFIG=~/kubeconfig

NAMESPACE="frigate"
TARGET_VM="k3s-vm-still-fawn"
TARGET_HOST="still-fawn"
TARGET_VMID="108"

echo "=== Pre-Flight Checks ==="

# 1. Check SSH
echo "Checking SSH connectivity..."
if ssh -o ConnectTimeout=5 ubuntu@${TARGET_VM} "uptime" 2>/dev/null; then
    echo "✅ SSH works"
    VM_ACCESS="ssh"
else
    echo "⚠️  SSH broken, will use guest agent"
    VM_ACCESS="qemu"
fi

# 2. Check PVC node affinity
echo ""
echo "Checking PVC node affinity..."
kubectl get pv -o json | jq -r ".items[] | select(.spec.claimRef.namespace==\"${NAMESPACE}\") | \"\(.metadata.name): \(.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values[0] // \"no-affinity\")\""
echo "⚠️  If using local-path, PVCs must be deleted and recreated!"

# 3. Check secrets
echo ""
echo "Checking secrets..."
kubectl get secret -n ${NAMESPACE}

# 4. Check hardware on target host
echo ""
echo "Checking hardware on target host..."
ssh root@${TARGET_HOST}.maas "lsusb" | head -5

echo ""
echo "=== Pre-flight complete ==="
echo "VM_ACCESS=${VM_ACCESS}"
```

---

## Phase 1: Cleanup Source Node

1. Scale down workload
2. Remove USB passthrough from source VM
3. Remove K8s node label

---

## Phase 2: Physical Hardware Move

User physically moves USB hardware from source to target server.

---

## Phase 3: Setup Target Node

1. Verify hardware on host
2. Add USB passthrough to VM (with usb3=1 flag!)
3. Reboot VM
4. Wait for VM (use guest agent if SSH broken)
5. Verify hardware in VM
6. Install drivers if needed
7. Label K8s node

**IMPORTANT**: Use QEMU guest agent if SSH broken:
```bash
# Instead of:
ssh ubuntu@k3s-vm-target "lsusb"

# Use:
ssh root@target-host.maas "qm guest exec <VMID> -- lsusb"
```

---

## Phase 4: Handle PVCs (CRITICAL for local-path!)

### Script: `11-recreate-pvcs.sh`
```bash
#!/bin/bash
set -euo pipefail
export KUBECONFIG=~/kubeconfig

NAMESPACE="frigate"
PVCS="frigate-config frigate-media"

echo "=== Recreating PVCs for target node ==="

# Delete PVCs (idempotent)
kubectl delete pvc ${PVCS} -n ${NAMESPACE} --ignore-not-found=true

# Wait for cleanup
sleep 5

# Force Flux to recreate
flux reconcile kustomization flux-system --with-source

# Wait for recreation
for i in {1..30}; do
    if kubectl get pvc ${PVCS} -n ${NAMESPACE} &>/dev/null; then
        echo "PVCs created."
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

kubectl get pvc -n ${NAMESPACE}
```

---

## Phase 5: Update GitOps Manifests

### deployment.yaml
- Remove source-specific runtime class (e.g., `runtimeClassName: nvidia`)
- Change nodeSelector to target node
- Remove source-specific resource limits (e.g., GPU limits)

### configmap.yaml
- Update hardware acceleration settings (e.g., `preset-nvidia-h264` → `preset-vaapi`)

---

## Phase 6: Deploy & Verify

```bash
flux reconcile kustomization flux-system --with-source
kubectl wait --for=condition=ready pod -l app=<workload> -n <namespace> --timeout=120s
kubectl get pods -n <namespace> -o wide
# Verify hardware-specific functionality
```

---

## Lessons Learned (2025-12-13 Migration)

### What Went Wrong

| Issue | Time Lost | Root Cause | Prevention |
|-------|-----------|------------|------------|
| SSH broken to K3s VMs | 10 min | Unknown SSH issue | Always check SSH first, have guest agent fallback |
| PVC node affinity | 15 min | local-path creates node-bound PVs | Check PV node affinity, add PVC recreation step |
| Using one-liners | 5 min | Expedience over process | ALWAYS use scripts, even for simple commands |
| Missing secrets check | 0 min (lucky) | Assumed they'd work | Add to pre-flight checklist |

### What Went Right

1. Coral USB passthrough worked first try (usb3=1 flag)
2. libedgetpu already installed
3. GitOps/Flux worked smoothly
4. Created idempotent PVC recreation script during troubleshooting

### Key Takeaways

1. **ALWAYS run pre-flight checks** before any migration
2. **local-path storage = node-bound PVs** - must delete and recreate
3. **Have guest agent fallback** for all VM access scripts
4. **Use scripts, not one-liners** - even for simple commands
5. **Verify, don't assume** - check SSH, PVCs, secrets before starting

---

## Rollback Procedure

1. Revert GitOps manifests
2. Move hardware back to source
3. Re-add USB passthrough to source VM
4. Recreate PVCs (if deleted)
5. Reconcile Flux

---

## Tags

k8s, kubernetes, migration, node-migration, pvc, local-path, node-affinity, usb-passthrough, coral, tpu, qemu-guest-agent, blueprint, lessons-learned
