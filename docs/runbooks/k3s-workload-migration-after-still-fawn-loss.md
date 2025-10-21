# Runbook: K3s Workload Migration After still-fawn Node Loss

**Date Created**: October 21, 2025
**Scenario**: still-fawn.maas node failure - migrate all K3s workloads to remaining nodes
**Status**: READY FOR EXECUTION

## Executive Summary

The still-fawn.maas Proxmox node has failed, taking down a K3s master node (k3s-vm-still-fawn). All GitOps-managed workloads are in Pending state waiting for node availability. This runbook provides a systematic migration plan to restore all services to the remaining 3-node K3s cluster.

**Current Cluster State:**
- ✅ k3s-vm-pve (192.168.4.238) - Ready
- ✅ k3s-vm-chief-horse (192.168.4.237) - Ready
- ✅ k3s-vm-pumped-piglet-gpu (192.168.4.210) - Ready, GPU-enabled (RTX 3070)
- ❌ k3s-vm-still-fawn - OFFLINE (node lost)

## Prerequisites

### Required Access
```bash
# Kubernetes access
export KUBECONFIG=~/kubeconfig
kubectl get nodes -o wide

# Proxmox access (for storage verification)
ssh root@pve.maas
ssh root@chief-horse.maas
ssh root@pumped-piglet.maas
```

### Verification Commands
```bash
# Check current cluster status
kubectl get nodes
kubectl get pods -A | grep Pending

# Check PVs and PVCs
kubectl get pv
kubectl get pvc -A

# Check GPU availability
kubectl describe node k3s-vm-pumped-piglet-gpu | grep nvidia.com/gpu
```

## Migration Strategy

### Phase 1: Remove Failed Node from Cluster

**Objective**: Clean up stale k3s-vm-still-fawn node from etcd and Kubernetes

```bash
# From any master node (pve or chief-horse)
ssh ubuntu@192.168.4.238

# Remove Kubernetes node
kubectl delete node k3s-vm-still-fawn

# Remove from etcd (if registered as etcd member)
# Install etcdctl if not present
cd /tmp
wget -q https://github.com/etcd-io/etcd/releases/download/v3.5.12/etcd-v3.5.12-linux-amd64.tar.gz
tar xzf etcd-v3.5.12-linux-amd64.tar.gz
sudo mv etcd-v3.5.12-linux-amd64/etcdctl /usr/local/bin/

# Check etcd members
export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key

etcdctl --endpoints=https://127.0.0.1:2379 member list -w table

# If still-fawn member exists, remove it
etcdctl --endpoints=https://127.0.0.1:2379 member remove <MEMBER_ID>
```

**Success Criteria**:
- `kubectl get nodes` shows only 3 nodes (pve, chief-horse, pumped-piglet-gpu)
- `etcdctl member list` shows only 3 members
- Cluster has quorum (2 of 3 needed)

### Phase 2: Storage Migration - Prometheus & Grafana

**Problem**: Prometheus and Grafana PVs likely bound to still-fawn node's local-path storage

#### Step 1: Identify Current PVs

```bash
# Check Prometheus PV
kubectl get pvc -n monitoring prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0 -o yaml

# Check Grafana PV
kubectl get pvc -n monitoring kube-prometheus-stack-grafana -o yaml

# Describe PVs to see nodeAffinity
kubectl describe pv <pv-name>
```

#### Step 2: Backup Existing Data (If Accessible)

**If still-fawn is temporarily recoverable:**

```bash
# SSH to still-fawn VM and backup
ssh ubuntu@<still-fawn-ip>

# Backup Prometheus data
sudo tar -czf /tmp/prometheus-backup.tar.gz -C /var/lib/rancher/k3s/storage/ <pv-directory>

# Backup Grafana data
sudo tar -czf /tmp/grafana-backup.tar.gz -C /var/lib/rancher/k3s/storage/ <pv-directory>

# Copy backups off node
scp ubuntu@<still-fawn-ip>:/tmp/*-backup.tar.gz ~/backups/
```

**If still-fawn is permanently lost:**
- Accept data loss for Prometheus (metrics are time-series, not critical for migration)
- Grafana dashboards are in GitOps config, will be restored automatically

#### Step 3: Delete Old PVCs and Recreate

```bash
# Scale down StatefulSets first
kubectl scale statefulset -n monitoring prometheus-kube-prometheus-stack-prometheus --replicas=0
kubectl scale deployment -n monitoring kube-prometheus-stack-grafana --replicas=0

# Wait for pods to terminate
kubectl wait --for=delete pod -n monitoring -l app=kube-prometheus-stack-prometheus --timeout=60s
kubectl wait --for=delete pod -n monitoring -l app.kubernetes.io/name=grafana --timeout=60s

# Delete PVCs (will trigger new PV creation on available nodes)
kubectl delete pvc -n monitoring prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0
kubectl delete pvc -n monitoring kube-prometheus-stack-grafana

# Delete bound PVs (stuck in Released state)
kubectl delete pv <prometheus-pv-name>
kubectl delete pv <grafana-pv-name>

# Scale back up (new PVCs will be created automatically)
kubectl scale statefulset -n monitoring prometheus-kube-prometheus-stack-prometheus --replicas=1
kubectl scale deployment -n monitoring kube-prometheus-stack-grafana --replicas=1
```

#### Step 4: Restore Data (If Backed Up)

```bash
# Wait for new PVs to be created and bound
kubectl get pvc -n monitoring -w

# Once bound, find new PV directory
NEW_PROMETHEUS_PV=$(kubectl get pvc -n monitoring prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0 -o jsonpath='{.spec.volumeName}')
NEW_GRAFANA_PV=$(kubectl get pvc -n monitoring kube-prometheus-stack-grafana -o jsonpath='{.spec.volumeName}')

# Find which node hosts new PVs
kubectl get pv $NEW_PROMETHEUS_PV -o jsonpath='{.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values[0]}'

# SSH to that node and restore data
ssh ubuntu@<new-node-ip>
sudo tar -xzf ~/backups/prometheus-backup.tar.gz -C /var/lib/rancher/k3s/storage/<new-pv-directory>
```

**Success Criteria**:
- Prometheus pod Running
- Grafana pod Running
- Prometheus metrics collecting
- Grafana accessible via ingress

### Phase 3: GPU Workload Migration

**Workloads**:
- Ollama (ollama namespace)
- Stable Diffusion WebUI (default namespace)

#### Step 1: Verify GPU Node Taints/Labels

```bash
# Check pumped-piglet-gpu node
kubectl describe node k3s-vm-pumped-piglet-gpu | grep -A 5 Taints
kubectl describe node k3s-vm-pumped-piglet-gpu | grep -A 10 Labels

# Verify GPU resources advertised
kubectl describe node k3s-vm-pumped-piglet-gpu | grep nvidia.com/gpu
# Should show: nvidia.com/gpu: 4
```

#### Step 2: Check Ollama Deployment

```bash
# Check current Ollama deployment
kubectl get deployment -n ollama ollama-gpu -o yaml | grep -A 10 resources

# Verify it requests GPU
# Should see:
#   resources:
#     limits:
#       nvidia.com/gpu: "1"
```

**If deployment doesn't have GPU request**, update GitOps config:

```yaml
# gitops/clusters/homelab/apps/ollama/deployment.yaml
spec:
  template:
    spec:
      nodeSelector:
        nvidia.com/gpu.present: "true"  # Ensure scheduling to GPU node
      containers:
      - name: ollama
        resources:
          limits:
            nvidia.com/gpu: "1"  # Request 1 GPU
```

```bash
# Commit and push GitOps change
git add gitops/clusters/homelab/apps/ollama/deployment.yaml
git commit -m "fix: ensure Ollama schedules to GPU node"
git push origin master

# Wait for Flux to reconcile (or force)
flux reconcile kustomization flux-system
```

#### Step 3: Check Stable Diffusion Deployment

```bash
# Find Stable Diffusion deployment
kubectl get deployment -A | grep stable-diffusion

# Check GPU request
kubectl get deployment -n <namespace> <deployment-name> -o yaml | grep -A 10 resources
```

**If missing GPU request**, update GitOps config similarly.

#### Step 4: Delete Pending Pods to Force Rescheduling

```bash
# Delete pending Ollama pod
kubectl delete pod -n ollama --all

# Delete pending Stable Diffusion pod
kubectl delete pod -n <namespace> -l app=stable-diffusion

# Watch for new pods to schedule
kubectl get pods -n ollama -w
kubectl get pods -n <namespace> -w
```

**Success Criteria**:
- Ollama pod Running on k3s-vm-pumped-piglet-gpu
- Stable Diffusion pod Running on k3s-vm-pumped-piglet-gpu
- Both accessible via LoadBalancer/Ingress
- GPU workloads functional (test inference)

### Phase 4: Non-GPU Workload Migration

**Workloads**:
- Webtop (webtop namespace)
- Samba (samba namespace)
- Netdata (default namespace)

#### Step 1: Check PVC Requirements

```bash
# Webtop PVCs
kubectl get pvc -n webtop

# Samba PVCs
kubectl get pvc -n samba

# Check if bound to still-fawn node
kubectl describe pv <pv-name> | grep nodeAffinity
```

#### Step 2: Delete and Recreate PVCs (If Bound to still-fawn)

```bash
# Scale down deployments
kubectl scale deployment -n webtop webtop --replicas=0
kubectl scale deployment -n samba samba --replicas=0

# Delete PVCs
kubectl delete pvc -n webtop <pvc-name>
kubectl delete pvc -n samba <pvc-name>

# Delete Released PVs
kubectl delete pv <pv-name>

# Scale back up (new PVCs created automatically)
kubectl scale deployment -n webtop webtop --replicas=1
kubectl scale deployment -n samba samba --replicas=1
```

#### Step 3: Verify Scheduling

```bash
# Watch pods schedule to available nodes
kubectl get pods -n webtop -o wide
kubectl get pods -n samba -o wide

# Should distribute across pve, chief-horse, pumped-piglet-gpu
```

**Success Criteria**:
- All pods Running
- Webtop accessible via ingress
- Samba shares accessible via LoadBalancer IP
- Services functional

### Phase 5: Verify Flux GitOps Reconciliation

```bash
# Check Flux kustomizations
flux get kustomizations

# Check HelmReleases
flux get helmreleases -A

# If any suspended or unhealthy, reconcile
flux reconcile kustomization flux-system
flux reconcile helmrelease -n monitoring kube-prometheus-stack
flux reconcile helmrelease -n metallb-system metallb
```

**Success Criteria**:
- All Flux kustomizations show "Applied"
- All HelmReleases show "Release reconciliation succeeded"

## Validation Checklist

### Infrastructure
- [ ] 3-node K3s cluster healthy (pve, chief-horse, pumped-piglet-gpu)
- [ ] etcd cluster quorate (2 of 3 minimum)
- [ ] Flux GitOps reconciling successfully
- [ ] MetalLB speaker pods on all 3 nodes
- [ ] Traefik ingress controller Running

### Monitoring Stack
- [ ] Prometheus pod Running
- [ ] Prometheus scraping targets
- [ ] Grafana pod Running
- [ ] Grafana dashboards accessible via https://grafana.homelab
- [ ] Alertmanager pod Running
- [ ] Email alerts configured and tested

### GPU Workloads
- [ ] Ollama pod Running on pumped-piglet-gpu
- [ ] Ollama accessible via http://ollama.homelab
- [ ] Ollama inference test passes: `curl -X POST http://ollama.homelab/api/generate -d '{"model":"llama2","prompt":"test"}'`
- [ ] Stable Diffusion pod Running on pumped-piglet-gpu
- [ ] Stable Diffusion WebUI accessible
- [ ] Image generation test passes

### Non-GPU Workloads
- [ ] Webtop pod Running
- [ ] Webtop accessible via ingress
- [ ] Webtop user sessions functional
- [ ] Samba pod Running
- [ ] Samba shares accessible: `smbclient -L //<samba-ip>`
- [ ] Netdata pods Running on all nodes
- [ ] Netdata parent dashboard accessible

### LoadBalancer Services
- [ ] All LoadBalancer services have EXTERNAL-IP assigned
- [ ] MetalLB address pool not exhausted
- [ ] DNS overrides in OPNsense updated if IPs changed

## Rollback Plan

If migration encounters critical issues:

### Emergency: Restore still-fawn Node

**If hardware is recoverable:**

```bash
# Power on still-fawn.maas
# SSH to still-fawn
ssh root@still-fawn.maas

# Start K3s VM
qm start <vm-id>

# Wait for node to rejoin cluster
kubectl get nodes -w

# Node will rejoin automatically if etcd member still registered
```

### Alternative: Accept Service Downtime

- GPU workloads (Ollama, Stable Diffusion) can run offline until migration completes
- Monitoring stack can be rebuilt from scratch if data loss acceptable
- Samba/Webtop depend on data importance

## Post-Migration Tasks

### 1. Update Documentation

```bash
# Update cluster node inventory
# docs/infrastructure/k3s-cluster-inventory.md

# Document new node assignments
# docs/runbooks/k3s-node-assignments.md
```

### 2. Reconfigure Monitoring Alerts

```bash
# Update alert rules for 3-node cluster
# gitops/clusters/homelab/infrastructure/monitoring/alerting-rules.yaml

# Adjust node down alerts (2 nodes required for quorum)
```

### 3. Capacity Planning

**Current Cluster Resources (3 nodes):**
- Total CPU: ~30 cores
- Total RAM: ~150GB
- Total GPU: 1x RTX 3070 (4 GPU resources)

**Recommendations:**
- Monitor resource utilization with Prometheus
- Plan for 4th K3s node if workloads expand
- Consider dedicated storage node for monitoring stack

### 4. GitHub Issue Closure

```bash
# Create GitHub issue documenting migration
gh issue create --title "K3s workload migration after still-fawn failure" \
  --body "Completed migration of all GitOps workloads to 3-node cluster. See runbook for details."

# Close issue after validation
gh issue close <issue-number>
```

## Troubleshooting

### Problem: Pods Stuck in Pending

**Diagnosis:**
```bash
kubectl describe pod <pod-name> -n <namespace>
# Look for "Events" section for scheduling failures
```

**Common Causes:**
- Insufficient resources (CPU/RAM/GPU)
- PVC bound to unavailable node
- Node taints preventing scheduling
- Missing node labels

**Resolution:**
- Free up resources by scaling down non-critical pods
- Delete and recreate PVCs
- Remove taints: `kubectl taint node <node-name> <taint-key>-`
- Add labels: `kubectl label node <node-name> <label-key>=<value>`

### Problem: PVC Stuck in Pending

**Diagnosis:**
```bash
kubectl describe pvc <pvc-name> -n <namespace>
# Check "Events" for provisioning errors
```

**Resolution:**
```bash
# Ensure local-path-provisioner is running
kubectl get pods -n kube-system | grep local-path

# Check available disk space on nodes
kubectl get nodes -o wide
ssh ubuntu@<node-ip> "df -h /var/lib/rancher/k3s/storage"

# Delete and recreate PVC if stuck
kubectl delete pvc <pvc-name> -n <namespace>
```

### Problem: GPU Workloads Not Scheduling

**Diagnosis:**
```bash
# Verify GPU resources advertised
kubectl describe node k3s-vm-pumped-piglet-gpu | grep nvidia.com/gpu

# Check NVIDIA GPU Operator pods
kubectl get pods -n gpu-operator
```

**Resolution:**
```bash
# Restart GPU Operator DaemonSets
kubectl rollout restart daemonset -n gpu-operator nvidia-device-plugin-daemonset
kubectl rollout restart daemonset -n gpu-operator nvidia-container-toolkit-daemonset

# Verify CUDA validator completed
kubectl logs -n gpu-operator nvidia-cuda-validator-<hash>
```

## Related Documentation

- [GPU Passthrough Runbook](proxmox-gpu-passthrough-k3s-node.md)
- [K3s etcd Member Management](../reference/etcdctl-k3s-reference.md)
- [Secure Boot NVIDIA Drivers](../troubleshooting/secure-boot-nvidia-drivers.md)
- [K3s etcd Stale Member Removal](../troubleshooting/action-log-k3s-etcd-stale-member-removal.md)
- [Flux GitOps Troubleshooting](https://fluxcd.io/flux/troubleshooting/)
- [MetalLB Configuration](../infrastructure/metallb-configuration.md)

## Tags

k3s, kubernetes, kubernettes, k8s, migration, disaster-recovery, node-failure, workload-migration, gpu, ollama, stable-diffusion, prometheus, promethius, grafana, grafanna, flux, fluxcd, gitops, metallb, pv, pvc, storage-migration, etcd

## Version History

- **v1.0** (Oct 21, 2025): Initial migration plan after still-fawn node loss
- K3s version: v1.32.4+k3s1
- Remaining nodes: pve, chief-horse, pumped-piglet-gpu
