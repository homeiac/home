# Runbook: Add K3s Control-Plane Node

**Purpose**: Add a new K3s server (control-plane/etcd) node to the cluster via Crossplane GitOps.

**When to use**:
- Restoring etcd quorum after node failure
- Expanding control-plane for HA
- Migrating control-plane to different hardware

---

## Prerequisites

- [ ] Proxmox host is operational and accessible via SSH
- [ ] `local` datastore has snippets content type enabled
- [ ] Ubuntu cloud image is available (`local:import/noble-server-cloudimg-amd64.qcow2`)
- [ ] kubectl access to the K3s cluster
- [ ] Git access to the home repo

---

## Procedure

### Step 1: Get Cluster Join Information

```bash
# Get K3s version from existing nodes
kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.kubeletVersion}'
# Example: v1.33.6+k3s1

# Get K3s server URL (any existing control-plane node IP)
kubectl get nodes -o wide
# Use the INTERNAL-IP of an existing control-plane node
# Example: https://192.168.4.210:6443

# Get join token from existing control-plane node
ssh root@<proxmox-host>.maas "qm guest exec <VMID> -- cat /var/lib/rancher/k3s/server/node-token"
# Example: K103e5597417ab93ec...::server:4b29815ba0333c8cc...
```

### Step 2: Create Host-Specific Snippet

```bash
# Copy the example template
cp scripts/k3s/snippets/k3s-server-EXAMPLE.yaml scripts/k3s/snippets/k3s-server-<host>.yaml

# Edit and replace placeholders:
#   HOSTNAME        → k3s-vm-<host> (e.g., k3s-vm-fun-bedbug)
#   K3S_SERVER_URL  → https://<existing-node-ip>:6443
#   K3S_TOKEN       → Token from Step 1
#   K3S_VERSION     → Version from Step 1
#   SSH_PUBLIC_KEY  → Your SSH public key

vim scripts/k3s/snippets/k3s-server-<host>.yaml
```

### Step 3: Deploy Snippet to Proxmox Host

```bash
# One-time per host - snippet stays forever
scp scripts/k3s/snippets/k3s-server-<host>.yaml root@<host>.maas:/var/lib/vz/snippets/

# Verify it's there
ssh root@<host>.maas "ls -la /var/lib/vz/snippets/"
```

### Step 4: Create VM Manifest

Create `gitops/clusters/homelab/instances/k3s-vm-<host>.yaml`:

```yaml
apiVersion: virtualenvironmentvm.crossplane.io/v1alpha1
kind: EnvironmentVM
metadata:
  name: k3s-vm-<host>
  labels:
    role: k3s-control-plane
    node: <host>
spec:
  forProvider:
    nodeName: <host>
    name: k3s-vm-<host>
    vmId: <next-available-vmid>
    description: "K3s control-plane node - Crossplane managed"
    started: true
    onBoot: true
    machine: pc-i440fx-8.1
    bios: seabios

    cpu:
      - cores: 2
        type: host
    memory:
      - dedicated: 4096
    scsiHardware: virtio-scsi-pci

    disk:
      - interface: scsi0
        datastoreId: local
        size: 50
        fileFormat: raw
        discard: "on"
        importFrom: local:import/noble-server-cloudimg-amd64.qcow2

    networkDevice:
      - bridge: vmbr0
        model: virtio
        enabled: true

    initialization:
      - datastoreId: local
        userAccount:
          - username: ubuntu
        ipConfig:
          - ipv4:
              - address: dhcp
        userDataFileId: local:snippets/k3s-server-<host>.yaml

    agent:
      - enabled: true
        trim: true
        type: virtio

  providerConfigRef:
    name: default
  deletionPolicy: Orphan
```

### Step 5: Add to Kustomization

Edit `gitops/clusters/homelab/instances/kustomization.yaml`:

```yaml
resources:
  - ubuntu-noble-cloud-image.yaml
  - k3s-vm-<host>.yaml  # Add this line
```

### Step 6: Commit and Push

```bash
git add gitops/clusters/homelab/instances/k3s-vm-<host>.yaml
git add gitops/clusters/homelab/instances/kustomization.yaml
git commit -m "feat(k3s): add control-plane node on <host>"
git push origin master
```

### Step 7: Trigger Reconciliation

```bash
flux reconcile kustomization flux-system --with-source
```

### Step 8: Verify

```bash
# Watch Crossplane create the VM
kubectl get environmentvm k3s-vm-<host> -w

# Check VM is running on Proxmox
ssh root@<host>.maas "qm status <VMID>"

# Wait for cloud-init (2-3 minutes)
ssh root@<host>.maas "qm guest exec <VMID> -- cloud-init status"
# Should show: status: done

# Verify node joined cluster
kubectl get nodes
# Should show new node with Ready status
```

---

## Troubleshooting

### Node Shows Wrong Hostname

**Symptom**: Node appears as `ubuntu` instead of `k3s-vm-<host>`

**Cause**: Cloud-init hostname didn't persist before K3s registered

**Fix**:
```bash
# Set hostname manually
ssh root@<host>.maas "qm guest exec <VMID> -- hostnamectl set-hostname k3s-vm-<host>"

# Restart K3s to re-register
ssh root@<host>.maas "qm guest exec <VMID> -- systemctl restart k3s"

# Delete old node entry
kubectl delete node ubuntu
```

### Cloud-Init Stuck

**Symptom**: `cloud-init status` shows `running` for >5 minutes

**Check logs**:
```bash
ssh root@<host>.maas "qm guest exec <VMID> -- cat /var/log/cloud-init-output.log"
```

### K3s Failed to Join

**Symptom**: Node doesn't appear in `kubectl get nodes`

**Check K3s logs**:
```bash
ssh root@<host>.maas "qm guest exec <VMID> -- journalctl -u k3s -n 50"
```

**Common causes**:
- Wrong K3S_TOKEN (copy error)
- Wrong K3S_URL (firewall, wrong IP)
- Version mismatch

### Crossplane Not Creating VM

**Check EnvironmentVM status**:
```bash
kubectl describe environmentvm k3s-vm-<host>
```

**Common causes**:
- Cloud image not downloaded yet
- Snippet not deployed to Proxmox host
- VMID conflict

---

## Rollback

### Remove Node from Cluster

```bash
# Drain the node first (if it was running workloads)
kubectl drain k3s-vm-<host> --ignore-daemonsets --delete-emptydir-data

# Delete node from cluster
kubectl delete node k3s-vm-<host>
```

### Delete VM

```bash
# Remove from Git (VM stays due to Orphan policy)
git rm gitops/clusters/homelab/instances/k3s-vm-<host>.yaml
# Edit kustomization.yaml to remove reference
git commit -m "rollback: remove k3s-vm-<host>"
git push

# Manually destroy VM on Proxmox
ssh root@<host>.maas "qm stop <VMID> && qm destroy <VMID>"
```

---

## Reference

- **Blog post**: `docs/blog/k3s-iac-crossplane-cloud-init.md`
- **Example snippet**: `scripts/k3s/snippets/k3s-server-EXAMPLE.yaml`
- **Crossplane provider**: provider-proxmox-bpg v0.11.1

**Tags**: k3s, crossplane, proxmox, control-plane, etcd, runbook
