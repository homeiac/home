# k3s Migration Guide: etcd to SQLite Backend

## ⚠️ Critical Warning

**This migration requires complete cluster recreation** - k3s does NOT support direct etcd → SQLite migration. Only SQLite → etcd is officially supported.

**Expected Downtime**: 4-8 hours (potentially 12+ with rollback)  
**Risk Level**: Medium-High (data loss possible without perfect backups)  
**Complexity**: Very High (essentially rebuilding entire cluster)

## When to Consider This Migration

### Good Candidates
- Single-node requirements acceptable
- Development/testing environments
- Low API request volume (<100 QPS)
- Minimal operational overhead priority
- Frequent etcd performance issues

### Poor Candidates
- Production workloads requiring HA
- High API request volumes (>200 QPS)
- Complex multi-service dependencies
- Limited backup/restore experience
- Tight downtime constraints

## Alternative: Optimize Current etcd Setup

Before considering migration, try etcd optimization:
- Configure smart ballooning (memory pressure fix)
- Reduce etcd snapshot frequency
- Tune compaction intervals
- Add etcd operation monitoring

**Recommendation**: Most homelab setups should optimize rather than migrate.

## Migration Architecture Change

**Before Migration**:
```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Master 1  │  │   Master 2  │  │   Master 3  │
│    etcd     │◄─┤    etcd     │──┤    etcd     │
└─────────────┘  └─────────────┘  └─────────────┘
       │                │                │
   ┌───▼────┐      ┌────▼───┐       ┌────▼───┐
   │Worker 1│      │Worker 2│       │Worker 3│
   └────────┘      └────────┘       └────────┘
```

**After Migration**:
```
      ┌─────────────┐
      │   Master 1  │
      │   SQLite    │
      └─────────────┘
             │
    ┌────────┼────────┐
    │        │        │
┌───▼────┐ ┌─▼──────┐ ┌▼───────┐
│Worker 1│ │Worker 2│ │Worker 3│ 
└────────┘ └────────┘ └────────┘
```

## Pre-Migration Assessment

### 1. Document Current Architecture
```bash
# Identify all cluster nodes
kubectl get nodes -o wide

# Check k3s server endpoints
kubectl cluster-info

# Document current resource usage
kubectl top nodes
kubectl get pods --all-namespaces -o wide
```

### 2. Inventory Critical Applications
```bash
# List all namespaces and applications
kubectl get namespaces
kubectl get deployments,statefulsets,daemonsets --all-namespaces

# Document persistent volumes
kubectl get pv,pvc --all-namespaces

# Export critical configurations
kubectl get configmaps,secrets --all-namespaces -o yaml > backup-configs.yaml
```

### 3. Test Backup Procedures
```bash
# etcd snapshot backup
sudo k3s etcd-snapshot save pre-migration-backup

# Verify snapshot
sudo k3s etcd-snapshot ls

# Test application-level backups (example for key services)
kubectl get deployment/ollama -o yaml > ollama-deployment.yaml
kubectl get service/ollama -o yaml > ollama-service.yaml
```

## Complete Migration Process

### Phase 1: Comprehensive Backup

#### 1.1 etcd Snapshot
```bash
# Create etcd snapshot on all masters
ssh root@k3s-master-1 "k3s etcd-snapshot save migration-backup-$(date +%Y%m%d-%H%M%S)"
ssh root@k3s-master-2 "k3s etcd-snapshot save migration-backup-$(date +%Y%m%d-%H%M%S)" 
ssh root@k3s-master-3 "k3s etcd-snapshot save migration-backup-$(date +%Y%m%d-%H%M%S)"

# Copy snapshots to safe location
scp root@k3s-master-1:/var/lib/rancher/k3s/server/db/snapshots/* ./etcd-backups/
```

#### 1.2 Application Data Backup
```bash
# Install Velero for comprehensive backup (recommended)
kubectl apply -f https://github.com/vmware-tanzu/velero/releases/download/v1.12.0/00-prereqs.yaml

# Configure Velero with local storage
velero install --provider aws --bucket k3s-backups --secret-file credentials-velero

# Create complete cluster backup
velero backup create pre-migration-full --include-namespaces='*'

# Alternative: Manual exports for critical applications
kubectl get all --all-namespaces -o yaml > cluster-full-export.yaml
kubectl get pv,pvc --all-namespaces -o yaml > storage-export.yaml
```

#### 1.3 Node Certificates and Configuration
```bash
# Backup k3s configuration and certificates
ssh root@k3s-master-1 "tar czf /tmp/k3s-config-backup.tar.gz /var/lib/rancher/k3s/server/"
scp root@k3s-master-1:/tmp/k3s-config-backup.tar.gz ./

# Document network configuration
kubectl get services --all-namespaces -o yaml > services-export.yaml
kubectl get ingress --all-namespaces -o yaml > ingress-export.yaml
```

### Phase 2: New Cluster Creation

#### 2.1 Choose New Master Node
```bash
# Select one of the current masters as new single master
# Recommended: Use the node with best hardware or lowest ID

NEW_MASTER_IP="192.168.4.236"  # Your current kubeconfig endpoint
NEW_MASTER_HOSTNAME="k3s-vm-pve"
```

#### 2.2 Stop Old Cluster (Point of No Return)
```bash
# Gracefully stop k3s on all nodes
ssh root@k3s-master-1 "systemctl stop k3s"
ssh root@k3s-master-2 "systemctl stop k3s" 
ssh root@k3s-master-3 "systemctl stop k3s"
ssh root@k3s-worker-1 "systemctl stop k3s-agent"
ssh root@k3s-worker-2 "systemctl stop k3s-agent"
```

#### 2.3 Clean New Master Node
```bash
# On the chosen new master, clean previous installation
ssh root@$NEW_MASTER_HOSTNAME "
  /usr/local/bin/k3s-uninstall.sh || true
  rm -rf /var/lib/rancher/k3s/*
  rm -rf /etc/rancher/k3s/*
"
```

#### 2.4 Install New Single-Master Cluster
```bash
# Install k3s with SQLite backend (default for single server)
ssh root@$NEW_MASTER_HOSTNAME "
  curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.28.4+k3s2 sh -s - server \
    --cluster-init=false \
    --datastore-endpoint='' \
    --write-kubeconfig-mode=644
"

# Get node token for workers
NEW_NODE_TOKEN=$(ssh root@$NEW_MASTER_HOSTNAME "cat /var/lib/rancher/k3s/server/node-token")
```

### Phase 3: Worker Node Reconnection

#### 3.1 Clean and Rejoin Workers
```bash
# For each worker node
for WORKER in k3s-worker-1 k3s-worker-2 k3s-worker-3; do
  ssh root@$WORKER "
    /usr/local/bin/k3s-agent-uninstall.sh || true
    rm -rf /var/lib/rancher/k3s/*
    rm -rf /etc/rancher/k3s/*
  "
  
  # Rejoin to new master
  ssh root@$WORKER "
    curl -sfL https://get.k3s.io | K3S_URL=https://$NEW_MASTER_IP:6443 \
      K3S_TOKEN=$NEW_NODE_TOKEN sh -
  "
done
```

#### 3.2 Convert Former Masters to Workers
```bash
# Former masters become workers (optional)
for MASTER in k3s-master-2 k3s-master-3; do
  ssh root@$MASTER "
    /usr/local/bin/k3s-uninstall.sh || true
    rm -rf /var/lib/rancher/k3s/*
    rm -rf /etc/rancher/k3s/*
    
    curl -sfL https://get.k3s.io | K3S_URL=https://$NEW_MASTER_IP:6443 \
      K3S_TOKEN=$NEW_NODE_TOKEN sh -
  "
done
```

### Phase 4: Application Restoration

#### 4.1 Verify Cluster Health
```bash
# Update kubeconfig (should be same endpoint)
scp root@$NEW_MASTER_HOSTNAME:/etc/rancher/k3s/k3s.yaml ~/.kube/config
sed -i 's/127.0.0.1/'$NEW_MASTER_IP'/g' ~/.kube/config

# Verify nodes
kubectl get nodes
kubectl cluster-info
```

#### 4.2 Restore Applications
```bash
# Option A: Velero restore (recommended)
velero restore create migration-restore --from-backup pre-migration-full

# Option B: Manual restoration
kubectl apply -f cluster-full-export.yaml
kubectl apply -f storage-export.yaml
kubectl apply -f services-export.yaml
```

#### 4.3 Verify Application Health
```bash
# Check all pods are running
kubectl get pods --all-namespaces

# Verify services are accessible
kubectl get services --all-namespaces

# Test critical applications
curl http://ollama.homelab:11434/api/version  # Example
```

## Rollback Strategy

### Emergency Rollback (If Migration Fails)

#### Option 1: Restore from etcd Snapshot
```bash
# Stop failed new cluster
ssh root@$NEW_MASTER_HOSTNAME "systemctl stop k3s"

# Restore original master
ssh root@k3s-master-1 "
  /usr/local/bin/k3s-uninstall.sh || true
  k3s server --cluster-restore migration-backup-TIMESTAMP
"

# Restart other masters
ssh root@k3s-master-2 "systemctl start k3s"
ssh root@k3s-master-3 "systemctl start k3s"
```

#### Option 2: VM Snapshots (If Available)
```bash
# Restore all k3s VMs from pre-migration snapshots
# This is the fastest rollback method if VM snapshots were taken
```

### Planned Rollback (After Testing)

If you want to return to multi-master after testing:

```bash
# Take SQLite backup first
cp /var/lib/rancher/k3s/server/db/state.db ./sqlite-backup.db

# Follow standard k3s SQLite → etcd migration process
# (This IS officially supported)
```

## Risk Mitigation

### Data Loss Prevention
1. **Multiple backup methods**: etcd snapshots + Velero + manual exports
2. **VM snapshots**: Snapshot all VMs before starting migration
3. **Test restores**: Verify backups can be restored before migration
4. **Staged approach**: Test on smaller cluster first if possible

### Downtime Minimization
1. **Pre-download images**: Pull container images during backup phase
2. **DNS preparation**: Ensure DNS records point to correct endpoints
3. **Application-level HA**: Design apps to handle control plane outages
4. **Communication**: Notify users of maintenance window

### Testing Strategy
1. **VM snapshot testing**: Clone VMs and test full procedure
2. **Backup validation**: Verify all backups before migration
3. **Rollback testing**: Practice rollback procedures
4. **Application testing**: Verify critical apps work post-migration

## Post-Migration Validation

### Cluster Health Checks
```bash
# Node status
kubectl get nodes -o wide

# System pods
kubectl get pods -n kube-system

# Resource usage
kubectl top nodes
kubectl top pods --all-namespaces
```

### Application Validation
```bash
# Service connectivity
kubectl get services --all-namespaces
nslookup ollama.homelab  # Test DNS resolution

# Persistent data
kubectl get pv,pvc --all-namespaces
kubectl exec -it <pod> -- ls -la /data  # Verify data persistence
```

### Performance Testing
```bash
# API server responsiveness
time kubectl get pods --all-namespaces

# Storage performance
kubectl run disk-test --image=busybox --rm -it -- dd if=/dev/zero of=/tmp/test bs=1M count=100

# Memory usage comparison
free -h  # Should be lower than before
```

## Monitoring and Alerting

### SQLite Monitoring
```bash
# Monitor SQLite database size
watch "ls -lh /var/lib/rancher/k3s/server/db/state.db"

# Check for SQLite locks or corruption
sqlite3 /var/lib/rancher/k3s/server/db/state.db "PRAGMA integrity_check;"
```

### Performance Monitoring
```bash
# API response times
curl -w "@curl-format.txt" -o /dev/null -s https://$NEW_MASTER_IP:6443/api/v1/nodes

# Resource usage trending
kubectl top nodes --use-protocol-buffers
```

## Conclusion

This migration is **high risk, high complexity** and should only be attempted if:

1. **Current etcd issues are severe and unresolvable**
2. **Extended downtime is acceptable**
3. **Comprehensive backups and rollback plans are tested**
4. **Team has experience with cluster rebuilds**

**Alternative recommendation**: Optimize current etcd setup with smart ballooning, tuning, and monitoring rather than migration.

---

**⚠️ Important**: This procedure has **not been tested in your specific environment**. Always test in a non-production environment first and ensure comprehensive backups before proceeding.