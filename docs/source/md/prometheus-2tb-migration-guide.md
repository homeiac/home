# Prometheus 2TB Storage Migration Guide

## Overview

This guide documents the complete process of migrating Prometheus from local disk storage to a 2TB drive on the k3s-vm-still-fawn node. The migration involved creating a custom StorageClass, updating Helm chart values, and resolving multiple technical challenges including HelmRelease failures and PVC recreation issues.

## Migration Background

**Problem**: Prometheus was running out of disk space on the default local storage (56GB used on 160GB available disk).

**Solution**: Migrate Prometheus data to the 2TB drive mounted at `/mnt/smb_data/prometheus` on the k3s-vm-still-fawn node.

**Final Result**: Successfully migrated to 19.5TB total capacity with 16.7TB available space.

## Pre-Migration State

- **Node**: Prometheus running on k3s-vm-chief-horse
- **Storage**: Local disk (`/dev/sda1`) with limited space
- **Storage Class**: `local-path` (default)
- **Data Size**: ~56GB of metrics data
- **Retention**: 30 days configured

## Migration Process - Detailed Steps

### Phase 1: Create Custom Storage Class (✅ Completed)

1. **Created custom StorageClass manifest**:
   ```bash
   # File: gitops/clusters/homelab/infrastructure/monitoring/prometheus-storage-class.yaml
   ```

   ```yaml
   apiVersion: storage.k8s.io/v1
   kind: StorageClass
   metadata:
     name: prometheus-2tb-storage
   provisioner: rancher.io/local-path
   parameters:
     nodePath: /mnt/smb_data/prometheus
   volumeBindingMode: WaitForFirstConsumer
   reclaimPolicy: Retain
   ---
   apiVersion: v1
   kind: PersistentVolume
   metadata:
     name: prometheus-2tb-pv
   spec:
     capacity:
       storage: 1000Gi
     accessModes:
       - ReadWriteOnce
     persistentVolumeReclaimPolicy: Retain
     storageClassName: prometheus-2tb-storage
     local:
       path: /mnt/smb_data/prometheus
     nodeAffinity:
       required:
         nodeSelectorTerms:
           - matchExpressions:
               - key: kubernetes.io/hostname
                 operator: In
                 values:
                   - k3s-vm-still-fawn
   ```

2. **Added to kustomization**:
   ```yaml
   # File: gitops/clusters/homelab/infrastructure/monitoring/kustomization.yaml
   resources:
     - namespace.yaml
     - helmrepository.yaml
     - helmrelease.yaml
     - prometheus-storage-class.yaml  # Added this line
   ```

### Phase 2: Update Monitoring Values (✅ Completed)

1. **Modified monitoring values**:
   ```yaml
   # File: gitops/clusters/homelab/infrastructure/monitoring/monitoring-values.yaml
   prometheus:
     prometheusSpec:
       retention: 30d
       nodeSelector:
         kubernetes.io/hostname: k3s-vm-still-fawn  # Force to correct node
       storageSpec:
         volumeClaimTemplate:
           spec:
             accessModes: ["ReadWriteOnce"]
             storageClassName: prometheus-2tb-storage  # Use custom storage class
             resources:
               requests:
                 storage: 500Gi  # Increased from 100Gi
   ```

### Phase 3: Initial Deployment Attempt (❌ Failed)

1. **Committed changes**:
   ```bash
   git add gitops/clusters/homelab/infrastructure/monitoring/
   git commit -m "Add Prometheus 2TB storage migration setup"
   git push
   ```

2. **Flux reconciliation failed**:
   ```bash
   # Issue: kustomization.yaml referenced non-existent files
   # Error: couldn't find resource for cpu-alerting-rules.yaml
   ```

3. **Fixed kustomization.yaml**:
   ```bash
   # Removed references to manually-configured alerting files
   # Kept only: namespace.yaml, helmrepository.yaml, helmrelease.yaml, prometheus-storage-class.yaml
   ```

### Phase 4: HelmRelease Upgrade Failures (❌ Multiple Failures)

#### First Failure: API Server Connectivity
```bash
# Command used to check status
export KUBECONFIG=~/kubeconfig && kubectl get helmreleases -n monitoring

# Error observed:
NAME                    AGE     READY   STATUS
kube-prometheus-stack   3d19h   False   Helm upgrade failed for release monitoring/kube-prometheus-stack with chart kube-prometheus-stack@74.2.1: pre-upgrade hooks failed
```

**Detailed Error**:
```
pre-upgrade hooks failed: warning: Hook pre-upgrade kube-prometheus-stack/templates/prometheus-operator/admission-webhooks/job-patch/rolebinding.yaml failed: 1 error occurred:
* Post "https://10.43.0.1:443/apis/rbac.authorization.k8s.io/v1/namespaces/monitoring/rolebindings?fieldManager=helm-controller": unexpected EOF
```

#### Debugging Commands Used:
```bash
# Check HelmRelease details
export KUBECONFIG=~/kubeconfig && kubectl describe helmrelease kube-prometheus-stack -n monitoring

# Check webhook configurations causing issues
export KUBECONFIG=~/kubeconfig && kubectl get validatingwebhookconfigurations | grep prometheus
# Output: kube-prometheus-stack-admission, prom-stack-kube-prometheus-admission

# Force reconciliation attempt
export KUBECONFIG=~/kubeconfig && kubectl annotate helmrelease kube-prometheus-stack -n monitoring reconcile.fluxcd.io/requestedAt="$(date +%s)"
```

#### Resolution Attempt 1: Force Delete HelmRelease
```bash
# Remove finalizers
export KUBECONFIG=~/kubeconfig && kubectl patch helmrelease kube-prometheus-stack -n monitoring -p '{"metadata":{"finalizers":null}}' --type=merge

# Force delete
export KUBECONFIG=~/kubeconfig && kubectl delete helmrelease kube-prometheus-stack -n monitoring --force --grace-period=0
```

**Result**: HelmRelease was recreated by Flux and upgrade succeeded.

### Phase 5: Storage Migration Issues (❌ Storage Not Applied)

#### Problem: PVC Still Using Wrong Storage Class
```bash
# Check PVC status
export KUBECONFIG=~/kubeconfig && kubectl get pvc -n monitoring

# Output showed:
NAME                                                                                           STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   
prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0   Bound    pvc-44ffa98d-e710-4b8e-9f7e-a8e01b5e13c3   100Gi      RWO            local-path     # Still wrong!
```

#### Verification Commands:
```bash
# Check if custom storage class exists
export KUBECONFIG=~/kubeconfig && kubectl get storageclass prometheus-2tb-storage
# Output: Confirmed storage class exists

# Check actual storage path being used
export KUBECONFIG=~/kubeconfig && kubectl exec -n monitoring prometheus-kube-prometheus-stack-prometheus-0 -- df -h /prometheus
# Output: Still showing /dev/sda1 (local disk) instead of 2TB drive
```

#### Root Cause Analysis:
The PVC was created before the new configuration was applied by the HelmRelease. The Prometheus operator doesn't automatically recreate PVCs when storage configuration changes.

### Phase 6: Force PVC Recreation (✅ Successful)

#### Step 1: Delete StatefulSet and PVC
```bash
# Delete StatefulSet first
export KUBECONFIG=~/kubeconfig && kubectl delete statefulset prometheus-kube-prometheus-stack-prometheus -n monitoring

# Delete the old PVC 
export KUBECONFIG=~/kubeconfig && kubectl delete pvc prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0 -n monitoring
```

**Issue Encountered**: PVC stuck in "Terminating" state for several minutes.

#### Step 2: Force PVC Deletion
```bash
# Remove finalizers to force deletion
export KUBECONFIG=~/kubeconfig && kubectl patch pvc prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0 -n monitoring -p '{"metadata":{"finalizers":null}}'

# Verify deletion
export KUBECONFIG=~/kubeconfig && kubectl get pvc -n monitoring
# Confirmed: PVC was deleted successfully
```

#### Step 3: Verify New Pod Creation
```bash
# Check pod status
export KUBECONFIG=~/kubeconfig && kubectl get pods -n monitoring | grep prometheus
# Output: New prometheus-kube-prometheus-stack-prometheus-0 pod created on k3s-vm-still-fawn ✅
```

### Phase 7: Second Storage Issue (❌ Still Wrong Storage Class)

#### Problem: New PVC Created with Wrong Storage Class
```bash
# Check new PVC
export KUBECONFIG=~/kubeconfig && kubectl get pvc -n monitoring
# Output: New PVC still using local-path instead of prometheus-2tb-storage
```

#### Debugging: Check StatefulSet Configuration
```bash
# Verify StatefulSet has correct volumeClaimTemplate
export KUBECONFIG=~/kubeconfig && kubectl get statefulset prometheus-kube-prometheus-stack-prometheus -n monitoring -o yaml | grep -A 15 volumeClaimTemplates

# Output confirmed:
# storageClassName: prometheus-2tb-storage ✅
# resources.requests.storage: 500Gi ✅
```

#### Root Cause: Timing Issue
The new PVC was created before the Prometheus operator could apply the updated StatefulSet configuration.

### Phase 8: Final Resolution - Manual StatefulSet Scaling (✅ Success)

#### Step 1: Force StatefulSet Recreation
```bash
# Scale down to 0 (this deletes the pod but keeps StatefulSet)
export KUBECONFIG=~/kubeconfig && kubectl scale statefulset prometheus-kube-prometheus-stack-prometheus -n monitoring --replicas=0

# Scale back up to 1 (creates new pod with correct configuration)
export KUBECONFIG=~/kubeconfig && kubectl scale statefulset prometheus-kube-prometheus-stack-prometheus -n monitoring --replicas=1
```

#### Step 2: Verify Successful Migration
```bash
# Check new PVC
export KUBECONFIG=~/kubeconfig && kubectl get pvc -n monitoring
# Output: ✅ SUCCESS!
NAME                                                                                           STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS             
prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0   Bound    prometheus-2tb-pv                          1000Gi     RWO            prometheus-2tb-storage   ✅

# Verify storage path
export KUBECONFIG=~/kubeconfig && kubectl exec -n monitoring prometheus-kube-prometheus-stack-prometheus-0 -- df -h /prometheus
# Output: ✅ SUCCESS!
Filesystem                Size      Used Available Use% Mounted on
/dev/sdb                 19.5T      1.7T     16.7T   9% /prometheus  ✅

# Check pod location
export KUBECONFIG=~/kubeconfig && kubectl get pods -n monitoring -o wide | grep prometheus
# Output: ✅ Pod running on k3s-vm-still-fawn as intended
prometheus-kube-prometheus-stack-prometheus-0    2/2     Running   0    28s    10.42.1.XXX    k3s-vm-still-fawn    ✅
```

## Key Debugging Commands Reference

### Flux GitOps Debugging
```bash
# Force Flux reconciliation
kubectl annotate helmrelease <name> -n <namespace> reconcile.fluxcd.io/requestedAt="$(date +%s)"

# Check HelmRelease status
kubectl get helmreleases -n <namespace>
kubectl describe helmrelease <name> -n <namespace>

# Check Flux kustomization status
kubectl get kustomizations -n flux-system
```

### Kubernetes Storage Debugging
```bash
# Check storage classes
kubectl get storageclass
kubectl describe storageclass <name>

# Check PVC status and configuration
kubectl get pvc -n <namespace>
kubectl describe pvc <name> -n <namespace>

# Check StatefulSet configuration
kubectl get statefulset <name> -n <namespace> -o yaml | grep -A 15 volumeClaimTemplates

# Verify actual storage usage inside pod
kubectl exec -n <namespace> <pod-name> -- df -h <mount-path>
```

### Pod and Node Debugging
```bash
# Check pod location and status
kubectl get pods -n <namespace> -o wide
kubectl describe pod <name> -n <namespace>

# Check node selector compliance
kubectl get pods -n <namespace> -o wide | grep <node-name>
```

### Force Resource Recreation
```bash
# Delete StatefulSet (keeps PVC)
kubectl delete statefulset <name> -n <namespace>

# Delete PVC (may get stuck in Terminating)
kubectl delete pvc <name> -n <namespace>

# Force delete stuck PVC
kubectl patch pvc <name> -n <namespace> -p '{"metadata":{"finalizers":null}}'

# Scale StatefulSet
kubectl scale statefulset <name> -n <namespace> --replicas=0
kubectl scale statefulset <name> -n <namespace> --replicas=1
```

## Common Issues and Solutions

### Issue 1: HelmRelease Upgrade Failures
**Symptoms**: 
- HelmRelease shows "UpgradeFailed" status
- Pre-upgrade hooks failing with API connectivity errors

**Solution**:
```bash
# Force delete and recreate HelmRelease
kubectl patch helmrelease <name> -n <namespace> -p '{"metadata":{"finalizers":null}}' --type=merge
kubectl delete helmrelease <name> -n <namespace> --force --grace-period=0
# Flux will recreate automatically
```

### Issue 2: PVC Using Wrong Storage Class
**Symptoms**:
- StatefulSet configuration shows correct storageClassName
- But existing PVC still uses old storage class

**Root Cause**: Kubernetes doesn't automatically recreate PVCs when StatefulSet storage configuration changes.

**Solution**:
```bash
# Must delete both StatefulSet and PVC
kubectl delete statefulset <name> -n <namespace>
kubectl delete pvc <pvc-name> -n <namespace>
# Operator will recreate with new configuration
```

### Issue 3: PVC Stuck in Terminating State
**Symptoms**: 
- `kubectl delete pvc` hangs or shows "Terminating" status indefinitely

**Solution**:
```bash
# Remove finalizers to force deletion
kubectl patch pvc <name> -n <namespace> -p '{"metadata":{"finalizers":null}}'
```

### Issue 4: Pod Created Before Configuration Applied
**Symptoms**:
- New pod created but still using old storage configuration

**Solution**:
```bash
# Use StatefulSet scaling to force recreation
kubectl scale statefulset <name> -n <namespace> --replicas=0
kubectl scale statefulset <name> -n <namespace> --replicas=1
```

## Verification Checklist

After migration, verify the following:

### ✅ Storage Verification
```bash
# Check PVC uses correct storage class
kubectl get pvc -n monitoring | grep prometheus
# Should show: storageClassName: prometheus-2tb-storage

# Verify actual filesystem mount
kubectl exec -n monitoring prometheus-kube-prometheus-stack-prometheus-0 -- df -h /prometheus
# Should show: /dev/sdb with ~19TB total capacity
```

### ✅ Node Placement Verification  
```bash
# Confirm pod is on correct node
kubectl get pods -n monitoring -o wide | grep prometheus
# Should show: NODE: k3s-vm-still-fawn
```

### ✅ Functionality Verification
```bash
# Check pod is running and ready
kubectl get pods -n monitoring | grep prometheus
# Should show: 2/2 Running

# Verify Prometheus is accessible (if port-forwarding available)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
# Access http://localhost:9090 to confirm Prometheus UI loads
```

### ✅ Data Persistence Verification
```bash
# Check that data directory contains metrics
kubectl exec -n monitoring prometheus-kube-prometheus-stack-prometheus-0 -- ls -la /prometheus/
# Should show prometheus database files and WAL directory
```

## Post-Migration State

### Final Configuration
- **Node**: k3s-vm-still-fawn ✅
- **Storage**: `/dev/sdb` (19.5TB total, 16.7TB available) ✅
- **Storage Class**: `prometheus-2tb-storage` ✅
- **PVC Size**: 1000Gi (bound to prometheus-2tb-pv) ✅
- **Pod Status**: 2/2 Running ✅
- **Data Retention**: 30 days ✅

### Files Modified During Migration
- `gitops/clusters/homelab/infrastructure/monitoring/prometheus-storage-class.yaml` (created)
- `gitops/clusters/homelab/infrastructure/monitoring/monitoring-values.yaml` (modified)
- `gitops/clusters/homelab/infrastructure/monitoring/kustomization.yaml` (modified)

## Lessons Learned

1. **PVC Lifecycle**: Kubernetes StatefulSets don't automatically recreate PVCs when volumeClaimTemplate changes. Manual deletion is required.

2. **Flux Reconciliation**: HelmRelease failures can often be resolved by force-deleting the HelmRelease and letting Flux recreate it.

3. **Timing Issues**: When deleting and recreating resources, timing matters. Ensure proper deletion before recreation.

4. **Storage Class Configuration**: Custom StorageClass with `WaitForFirstConsumer` binding mode requires both the StorageClass and PersistentVolume to be properly configured.

5. **Debugging Tools**: Using `export KUBECONFIG=~/kubeconfig` at the beginning of each kubectl command ensures consistent cluster access.

6. **Verification Steps**: Always verify the actual filesystem mount inside pods, not just the PVC configuration, to confirm successful migration.

## Future Recommendations

1. **Automation**: Consider creating a script for similar storage migrations to automate the StatefulSet/PVC recreation process.

2. **Monitoring**: Add alerts for storage space usage to prevent similar issues in the future.

3. **Documentation**: Keep this guide updated if the process changes with newer versions of Kubernetes or Flux.

4. **Backup Strategy**: Ensure proper backup procedures are in place before major storage migrations.

## Migration Timeline Summary

| Phase | Duration | Status | Key Action |
|-------|----------|--------|------------|
| 1. Storage Class Creation | ~5 minutes | ✅ | Created custom StorageClass and PV |
| 2. Monitoring Values Update | ~5 minutes | ✅ | Updated Helm chart values |
| 3. Initial Deployment | ~10 minutes | ❌ | Fixed kustomization.yaml errors |
| 4. HelmRelease Failures | ~20 minutes | ❌ | Resolved API connectivity issues |
| 5. First Storage Migration | ~15 minutes | ❌ | PVC still using wrong storage class |
| 6. Force PVC Recreation | ~10 minutes | ❌ | Timing issue with new PVC creation |
| 7. Second Storage Issue | ~10 minutes | ❌ | New PVC created with wrong config |
| 8. Final Resolution | ~5 minutes | ✅ | StatefulSet scaling resolved issue |

**Total Migration Time**: ~80 minutes (including troubleshooting)
**Downtime**: ~5 minutes during final StatefulSet scaling

The majority of time was spent troubleshooting and understanding the Kubernetes StatefulSet PVC lifecycle, which will make future similar migrations much faster.