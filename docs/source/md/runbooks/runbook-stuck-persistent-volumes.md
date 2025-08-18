# Runbook: Cleaning Up Stuck Persistent Volumes and Volume Attachments

## Overview

This runbook provides step-by-step procedures for removing persistent volumes (PVs), persistent volume claims (PVCs), and volume attachments that are stuck in `Terminating` or `Released` states and won't delete normally.

## When to Use This Runbook

### Symptoms
- PVs stuck in `Released` or `Terminating` state
- Volume attachments that won't delete
- Kubernetes controller errors about missing volumes
- Storage migration cleanup needed

### Common Scenarios
- Storage class migrations (e.g., Longhorn → local-path)
- CSI driver removal/replacement
- Node decommissioning with attached volumes
- Failed application deployments leaving orphaned storage

## Prerequisites

- `kubectl` access to the cluster with admin privileges
- Understanding of the storage being cleaned up
- **CRITICAL**: Verify data is backed up or no longer needed

## Investigation Phase

### 1. Identify Stuck Resources

```bash
# List all persistent volumes and their states
kubectl get pv

# Look for volumes in Released/Terminating state
kubectl get pv | grep -E "(Released|Terminating)"

# List volume attachments
kubectl get volumeattachment

# Check for specific storage class issues
kubectl get pv | grep longhorn  # Replace with your storage class
```

### 2. Understand What's Using the Volumes

```bash
# Check if any pods are still using the volumes
kubectl get pods --all-namespaces -o json | \
  jq -r '.items[] | select(.spec.volumes[]?.persistentVolumeClaim.claimName == "PVC_NAME") | "\(.metadata.namespace)/\(.metadata.name)"'

# List PVCs and their binding status
kubectl get pvc --all-namespaces

# Check for related storage class objects
kubectl get storageclass
```

### 3. Review Controller Logs

```bash
# Check k3s/k8s controller logs for volume-related errors
kubectl logs -n kube-system -l component=controller-manager --tail=100 | grep -i volume

# For k3s specifically:
journalctl -u k3s --since "1 hour ago" | grep -i "VerifyVolumesAreAttached"
```

## Cleanup Procedures

### Method 1: Standard Deletion (Try First)

```bash
# Delete PVCs first (if they exist and are bound)
kubectl delete pvc PVC_NAME -n NAMESPACE

# Delete the PV
kubectl delete pv PV_NAME

# Delete volume attachments
kubectl delete volumeattachment VA_NAME
```

### Method 2: Force Deletion

If standard deletion hangs or fails:

```bash
# Force delete with grace period
kubectl delete pv PV_NAME --force --grace-period=0
kubectl delete volumeattachment VA_NAME --force --grace-period=0
```

### Method 3: Finalizer Removal (Last Resort)

When resources are stuck in `Terminating` state:

#### For Persistent Volumes:
```bash
# Remove finalizers from PV
kubectl patch pv PV_NAME -p '{"metadata":{"finalizers":null}}'

# Alternative: Edit manually to remove finalizers
kubectl edit pv PV_NAME
# Delete the finalizers array or set it to []
```

#### For Volume Attachments:
```bash
# Remove finalizers from volume attachment
kubectl patch volumeattachment VA_NAME -p '{"metadata":{"finalizers":null}}'
```

#### Batch Processing:
```bash
# Remove finalizers from multiple volume attachments
for va in VA_NAME_1 VA_NAME_2 VA_NAME_3; do 
  kubectl patch volumeattachment $va -p '{"metadata":{"finalizers":null}}'
done

# Remove finalizers from multiple PVs
for pv in PV_NAME_1 PV_NAME_2 PV_NAME_3; do
  kubectl patch pv $pv -p '{"metadata":{"finalizers":null}}'
done
```

## Complete Example: Longhorn Cleanup

Based on the August 17, 2025 incident:

```bash
# 1. Identify stuck Longhorn resources
kubectl get pv | grep longhorn
kubectl get volumeattachment | grep longhorn

# 2. Force delete volume attachments
kubectl delete volumeattachment \
  csi-11c20d5f0fcf00e7ccf70b86310bbf1d6f8071d90fdb197a42243e99dddb42e4 \
  csi-2c3445b0a88f972d1aa405b6894130a408439c8cd73c3f6423dee39187197e65 \
  csi-a191520de6fc8b44379c136bfd1a93b0e8945df5529aa4a7e078f1d729456645 \
  --force --grace-period=0

# 3. Delete persistent volumes
kubectl delete pv \
  pvc-a5c2b843-2c17-4081-94b0-302a94451c9e \
  pvc-cc498c64-a1dd-475d-b990-7935e9f23b3e \
  pvc-eb7a4cde-95cf-484d-b74d-6a2da38588ee

# 4. If stuck in Terminating, remove finalizers
kubectl patch pv pvc-a5c2b843-2c17-4081-94b0-302a94451c9e -p '{"metadata":{"finalizers":null}}'
kubectl patch pv pvc-cc498c64-a1dd-475d-b990-7935e9f23b3e -p '{"metadata":{"finalizers":null}}'
kubectl patch pv pvc-eb7a4cde-95cf-484d-b74d-6a2da38588ee -p '{"metadata":{"finalizers":null}}'

# 5. Remove volume attachment finalizers if needed
for va in csi-11c20d5f0fcf00e7ccf70b86310bbf1d6f8071d90fdb197a42243e99dddb42e4 \
          csi-2c3445b0a88f972d1aa405b6894130a408439c8cd73c3f6423dee39187197e65 \
          csi-a191520de6fc8b44379c136bfd1a93b0e8945df5529aa4a7e078f1d729456645; do
  kubectl patch volumeattachment $va -p '{"metadata":{"finalizers":null}}'
done
```

## Verification

### Confirm Cleanup Success

```bash
# Verify no stuck volumes remain
kubectl get pv | grep -E "(Released|Terminating)"

# Verify no problematic volume attachments
kubectl get volumeattachment | grep STORAGE_CLASS_NAME

# Check controller logs for reduced errors
kubectl logs -n kube-system -l component=controller-manager --tail=50 | grep -i volume
```

### Validate Application Health

```bash
# Check that applications using new storage are healthy
kubectl get pods --all-namespaces | grep -v Running

# Verify PVCs are bound to correct storage
kubectl get pvc --all-namespaces -o wide
```

## Troubleshooting

### Common Issues

1. **"Resource not found" errors during deletion**
   - Resource may have been partially cleaned up
   - Continue with remaining resources

2. **Finalizer removal doesn't work**
   - Check if CSI driver is still running and blocking deletion
   - May need to stop or remove CSI driver components first

3. **Volume attachments recreate themselves**
   - Pod may still be running and requesting the volume
   - Delete the pod first, then clean up volume attachments

4. **Node-specific volume attachment issues**
   - Volume may be attached at the node level
   - Check node storage status: `kubectl describe node NODE_NAME`

### Emergency Commands

```bash
# Nuclear option: Remove all finalizers from all resources of a type
kubectl get pv -o name | xargs -I {} kubectl patch {} -p '{"metadata":{"finalizers":null}}'

# Force delete all volume attachments for a specific driver
kubectl get volumeattachment -o json | \
  jq -r '.items[] | select(.spec.attacher=="driver.longhorn.io") | .metadata.name' | \
  xargs kubectl delete volumeattachment --force --grace-period=0
```

## Prevention

### Best Practices

1. **Storage Migration Checklist**
   - Document all PVs before migration
   - Verify application migration completion
   - Check for orphaned volume attachments
   - Monitor controller logs post-migration

2. **Monitoring**
   - Alert on PVs in Released state > 1 hour
   - Monitor volume attachment errors
   - Track storage class usage over time

3. **Documentation**
   - Document storage dependencies before changes
   - Maintain runbooks for each storage system
   - Test cleanup procedures in non-production

## Related Documentation

- [RCA: High CPU/Memory Usage - August 17, 2025](../../rca/rca-2025-08-17-high-cpu-memory.md)
- [Kubernetes Storage Concepts](https://kubernetes.io/docs/concepts/storage/)
- [CSI Volume Lifecycle](https://kubernetes-csi.github.io/docs/volume-lifecycle.html)

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2025-08-18 | 1.0 | Initial version based on Longhorn cleanup incident |

---

**⚠️ Warning**: Always verify that data is backed up before deleting persistent volumes. This runbook involves potentially destructive operations that can result in data loss if used incorrectly.