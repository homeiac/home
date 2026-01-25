# Runbook: still-fawn Recovery (January 2026)

## Incident Summary

| Field | Value |
|-------|-------|
| Date | 2026-01-23 |
| Host | still-fawn.maas (192.168.4.17) |
| Symptom | "cannot import rpool" at boot, initramfs shell |
| Root Cause | 512GB ZFS root disk failure (UNAVAIL) |
| Impact | K3s control plane down, Frigate down, no monitoring/alerting |

## Why No Alerts Were Sent

**Single point of failure**: All monitoring ran on K3s, which ran on still-fawn.

```
still-fawn disk dies
    → rpool won't import
    → Proxmox won't boot
    → K3s VM 108 down
    → K3s control plane unreachable
    → Prometheus/Alertmanager down
    → No alerts sent
```

**Lesson**: Need out-of-band alerting that doesn't depend on the infrastructure it monitors.

---

## Recovery Steps

### Phase 1: Hardware

- [ ] Power off still-fawn
- [ ] Try reseating 512GB SSD/NVMe
- [ ] Check BIOS if disk is visible
- [ ] If disk dead → replace with spare SSD (256GB+ minimum)

### Phase 2: Proxmox Reinstall

1. Boot Proxmox ISO from USB
2. Install with **ZFS root** (rpool) on new disk
3. Configure network:
   - IP: 192.168.4.17
   - Gateway: 192.168.4.1
   - DNS: 192.168.4.1
4. Set hostname: `still-fawn`

### Phase 3: Rejoin Cluster (AUTOMATED)

**Use the Python automation** - DO NOT do this manually:

```bash
cd ~/code/home/proxmox/homelab
poetry run python src/homelab/cluster_manager.py rejoin still-fawn
```

This single command handles:
- SSH key setup (Mac → still-fawn using password from `.env`)
- Removing stale cluster entry from pumped-piglet
- Cleaning up cluster state on still-fawn
- Setting up inter-node SSH (still-fawn → pumped-piglet)
- Joining the cluster via `pvecm add --use_ssh`
- Configuring GPU passthrough (IOMMU, VFIO, driver blacklist)

**After the script completes, REBOOT still-fawn** for GPU passthrough:
```bash
ssh root@still-fawn.maas reboot
```

**Full documentation**: [Proxmox Node Rejoin Automation](proxmox-node-rejoin-automation.md)

### Phase 4: Configure Storage

PBS storage should sync from cluster automatically. If not:

```bash
ssh root@still-fawn.maas

# Add PBS storage
pvesm add pbs homelab-backup \
  --server 192.168.4.211 \
  --datastore homelab-backup \
  --fingerprint 54:52:3A:D2:43:F0:80:66:E3:D0:BB:D6:0B:28:50:9F:C6:1C:73:BD:45:EA:D0:38:BC:25:54:EE:A4:D5:D1:54 \
  --content backup

# Verify local-zfs exists (created during Proxmox install)
pvesm status
```

### Phase 5: Create Fresh VM 108 via Crossplane

**DO NOT restore from PBS** for these reasons:

1. **Performance**: PBS restore of a 700GB VM causes 100% iowait even on NVMe. PBS uses chunked deduplication - restoring requires reassembling millions of 4MB chunks, creating random write patterns that saturate disk I/O. A restore that should take minutes takes hours. This is a fundamental PBS architecture issue, not a hardware problem.

2. **Stale state**: Cloud-init in the backup contains old K3s tokens that cause TLS failures on cluster rejoin anyway. You'd restore for hours, then have to rebuild K3s state regardless.

**Better approach**: Fresh VM creation (minutes) + GitOps reconciliation (minutes) is faster than waiting for PBS restore (hours).

Create fresh VM:

```bash
# Deploy cloud-init snippet with CURRENT token
./scripts/k3s/deploy-snippets.sh still-fawn.maas

# Crossplane will create the VM - check status
kubectl get environmentvm k3s-vm-still-fawn
```

The Crossplane definition is at `gitops/clusters/homelab/instances/k3s-vm-still-fawn.yaml`.

### Phase 6: Add Passthrough (Crossplane Can't Do This)

Crossplane API token lacks USB/PCI passthrough permissions. Add manually:

```bash
ssh root@still-fawn.maas

# Stop VM for passthrough changes
qm stop 108

# USB passthrough (Coral TPU - two device IDs)
qm set 108 --usb0 host=1a6e:089a,usb3=1
qm set 108 --usb1 host=18d1:9302,usb3=1

# PCI passthrough (AMD GPU at 01:00)
qm set 108 --hostpci0 0000:01:00,pcie=1

# Start VM
qm start 108
```

Or run the passthrough job:
```bash
kubectl apply -f gitops/clusters/homelab/instances/job-vm108-passthrough.yaml
```

### Phase 7: K3s Cluster Join

**CRITICAL**: The joining node must be COMPLETELY CLEAN. Any leftover CA certs from previous attempts cause TLS handshake failures.

#### Step 1: Verify primary node is healthy

```bash
# On pumped-piglet VM 105 - check single-node etcd
ssh root@pumped-piglet.maas 'qm guest exec 105 -- bash -c "
export ETCDCTL_API=3
export ETCDCTL_CACERT=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt
export ETCDCTL_CERT=/var/lib/rancher/k3s/server/tls/etcd/server-client.crt
export ETCDCTL_KEY=/var/lib/rancher/k3s/server/tls/etcd/server-client.key
etcdctl --endpoints=https://127.0.0.1:2379 member list -w table
k3s kubectl get nodes
"'
```

Must show: 1 etcd member, 1 node Ready.

#### Step 2: Get current token

```bash
ssh root@pumped-piglet.maas 'qm guest exec 105 -- cat /var/lib/rancher/k3s/server/node-token'
```

#### Step 3: FULL CLEANUP on joining node (CRITICAL!)

**Use the uninstall script** - manual `rm -rf` leaves CA certs behind!

```bash
ssh root@still-fawn.maas 'qm guest exec 108 -- bash -c "
# MUST use uninstall script - it removes EVERYTHING including systemd units
sudo /usr/local/bin/k3s-uninstall.sh

# Verify nothing remains
ls /var/lib/rancher/k3s 2>&1 || echo CLEAN
ls /etc/rancher/k3s 2>&1 || echo CLEAN
ls /etc/systemd/system/k3s* 2>&1 || echo CLEAN
"'
```

If `k3s-uninstall.sh` doesn't exist (fresh VM), the node is already clean.

#### Step 4: Join cluster

```bash
ssh root@still-fawn.maas 'qm guest exec 108 -- bash -c "
export HOME=/root
curl -sfL https://get.k3s.io | \
  K3S_URL=\"https://192.168.4.210:6443\" \
  K3S_TOKEN=\"<TOKEN_FROM_STEP_2>\" \
  INSTALL_K3S_VERSION=\"v1.33.6+k3s1\" \
  sh -s - server --disable servicelb
"'
```

#### Step 5: Verify join

```bash
# Wait 60-90 seconds for etcd sync, then check
ssh root@pumped-piglet.maas 'qm guest exec 105 -- k3s kubectl get nodes -o wide'
```

Should show both nodes Ready:
```
k3s-vm-pumped-piglet-gpu   Ready    control-plane,etcd,master
k3s-vm-still-fawn          Ready    control-plane,etcd,master
```

### Phase 8: Bootstrap Flux GitOps

After K3s cluster is healthy, Flux needs to be reinstalled with secrets.

#### Step 1: Get fresh kubeconfig

```bash
# Get kubeconfig from pumped-piglet VM
ssh root@pumped-piglet.maas 'qm guest exec 105 -- cat /etc/rancher/k3s/k3s.yaml' 2>&1 | \
  grep -v "^Warning" | jq -r '.["out-data"]' > /tmp/kubeconfig.new

# Replace localhost with actual IP
sed -i '' 's/127.0.0.1/192.168.4.210/g' /tmp/kubeconfig.new
cp /tmp/kubeconfig.new ~/kubeconfig

# Verify access
KUBECONFIG=~/kubeconfig kubectl get nodes
```

#### Step 2: Install Flux components

```bash
KUBECONFIG=~/kubeconfig flux install
```

#### Step 3: Create SOPS age secret (for decrypting secrets)

**CRITICAL**: Without this secret, Flux cannot decrypt SOPS-encrypted secrets in git.

The age private key is stored at `~/.config/sops/age/keys.txt` on Mac.

```bash
KUBECONFIG=~/kubeconfig kubectl create secret generic sops-age \
  --namespace=flux-system \
  --from-file=age.agekey=/Users/10381054/.config/sops/age/keys.txt
```

**What this enables**:
- Flux's kustomize-controller uses this key to decrypt secrets at apply time
- Encrypted secrets in git (e.g., `infrastructure/cert-manager/cloudflare-secret.yaml`) are decrypted on-the-fly
- The age PUBLIC key is in `.sops.yaml` for encrypting; the PRIVATE key here is for decrypting

**If you lose the age key**:
1. Generate new key: `age-keygen -o ~/.config/sops/age/keys.txt`
2. Update `.sops.yaml` with new public key
3. Re-encrypt ALL secrets: `find gitops -name "*.yaml" -exec grep -l "sops:" {} \; | xargs -I {} sops updatekeys {}`
4. Commit and push
5. Recreate the `sops-age` secret

**SOPS-encrypted secrets in this repo**:
- `gitops/clusters/homelab/infrastructure/cert-manager/cloudflare-secret.yaml`
- `gitops/clusters/homelab/infrastructure/external-dns/cloudflare-secret.yaml`
- `gitops/clusters/homelab/infrastructure/crossplane/proxmox-secret.yaml`
- `gitops/clusters/homelab/apps/postgres/secret.yaml`
- `gitops/clusters/homelab/apps/postgres/rclone-secret.yaml`
- `gitops/clusters/homelab/apps/claudecodeui/blue/mqtt-secret.yaml`

#### Step 4: Generate new GitHub deploy key

```bash
# Generate new SSH key for Flux
ssh-keygen -t ed25519 -f ~/.ssh/flux-homeiac-home -N "" -C "flux-homeiac-home"

# Add to GitHub as deploy key
gh repo deploy-key add ~/.ssh/flux-homeiac-home.pub \
  --repo homeiac/home \
  --title "flux-k3s-$(date +%Y-%m)"
```

#### Step 5: Create flux-system secret with deploy key

```bash
# Get GitHub's current SSH host keys
KNOWN_HOSTS=$(ssh-keyscan github.com 2>/dev/null)

# Create the secret
KUBECONFIG=~/kubeconfig kubectl create secret generic flux-system \
  --namespace=flux-system \
  --from-file=identity=/Users/10381054/.ssh/flux-homeiac-home \
  --from-file=identity.pub=/Users/10381054/.ssh/flux-homeiac-home.pub \
  --from-literal=known_hosts="$KNOWN_HOSTS"
```

#### Step 6: Apply GitOps sync configuration

```bash
KUBECONFIG=~/kubeconfig kubectl apply -f ~/code/home/gitops/clusters/homelab/flux-system/gotk-sync.yaml
```

#### Step 7: Trigger reconciliation and verify

```bash
# Force reconcile
KUBECONFIG=~/kubeconfig flux reconcile source git flux-system

# Watch kustomizations
KUBECONFIG=~/kubeconfig flux get kustomizations

# Watch all resources sync
watch 'KUBECONFIG=~/kubeconfig kubectl get pods -A'
```

**Note**: Initial sync may show errors for CRDs that don't exist yet (e.g., MetalLB IPAddressPool). Flux will retry and resolve these as dependencies are installed.

### Phase 9: Verify Workloads

```bash
export KUBECONFIG=~/kubeconfig
kubectl get nodes
kubectl get pods -A
kubectl get pods -n frigate
```

---

## Post-Recovery: Add Out-of-Band Alerting

### Step 1: Add Ping Sensors to Home Assistant

**NOTE**: Ping integration is now UI-only. Add via Home Assistant UI:
1. Settings → Devices & Services → Add Integration
2. Search for "Ping"
3. Add sensors for: 192.168.4.17 (still-fawn), 192.168.4.175 (pumped-piglet), 192.168.4.19 (chief-horse), 192.168.4.172 (fun-bedbug)

### Step 2: Create Infrastructure Alert Automation

The automation YAML files are in the repo:
- `scripts/haos/ping-sensors.yaml` - Reference for ping sensor config
- `scripts/haos/infra-alert-automation.yaml` - Voice PE alert automation

Add input_boolean helper via HA UI:
1. Settings → Devices & Services → Helpers
2. Create Toggle: `infra_alert_active`

Import automations:
1. Settings → Automations → Import
2. Or copy YAML from `scripts/haos/infra-alert-automation.yaml`

### How It Works

**One alert per incident:**
- `input_boolean.infra_alert_active` tracks if we've already alerted
- First host down → alert fires, boolean turns ON
- Second host down → condition fails (boolean already ON), no duplicate alert
- All hosts recover → boolean resets to OFF, ready for next incident

**One announcement per incident:**
- "What's my notification" reads `pending_notification_message`
- LED stays red until all hosts recover

---

## Verification Checklist

After recovery, verify:

- [ ] `ping still-fawn.maas` works
- [ ] `ssh root@still-fawn.maas` works
- [ ] `pvecm status` shows all 5 nodes (pve, still-fawn, chief-horse, fun-bedbug, pumped-piglet)
- [ ] VM 108 exists: `qm status 108`
- [ ] VM 108 running after start
- [ ] K3s healthy: `kubectl get nodes`
- [ ] Frigate running: `kubectl get pods -n frigate`
- [ ] Coral TPU detected: `kubectl logs -n frigate -l app=frigate | grep -i tpu`
- [ ] GPU working: `kubectl logs -n frigate -l app=frigate | grep -i vaapi`
- [ ] Ping sensors in HA: Check `binary_sensor.still_fawn_ping` state
- [ ] Alert automation loaded: Check HA automations list

---

## PBS Backup Status (Verified)

| VMID | Name | Latest Backup | Size |
|------|------|---------------|------|
| 108 | k3s-vm-still-fawn | 2026-01-20 | 700 GB |

---

## Hardware Notes

still-fawn specs:
- CPU: Intel i5-4460 (4 cores)
- RAM: 32GB
- Boot disk: 512GB SSD (FAILED)
- GPU: AMD Radeon RX 570/580 (PCI passthrough to VM 108)
- TPU: Google Coral USB (passed through to VM 108)

Known issues:
- PSU aging (11+ years) - caused previous failures
- Consider PSU replacement if disk failure was power-related

---

## Automation Details

The `cluster_manager.py` script handles the entire rejoin process:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  poetry run python src/homelab/cluster_manager.py rejoin still-fawn        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. SSH Key Setup (Mac → still-fawn)                                        │
│     └── Uses PVE_ROOT_PASSWORD from .env + sshpass                          │
│                                                                             │
│  2. Remove Old Cluster Entry                                                │
│     └── pvecm delnode still-fawn (via pumped-piglet)                        │
│                                                                             │
│  3. Clean Cluster State                                                     │
│     ├── Delete /var/lib/pve-cluster/*                                       │
│     ├── Delete /etc/corosync/*, /var/lib/corosync/*                         │
│     ├── Delete /etc/pve/nodes/*, qemu-server/*, lxc/*                       │
│     └── Wait for pve-cluster ready                                          │
│                                                                             │
│  4. Inter-node SSH Setup                                                    │
│     └── Copy still-fawn's id_rsa.pub to pumped-piglet                       │
│                                                                             │
│  5. Join Cluster                                                            │
│     └── pvecm add pumped-piglet.maas --use_ssh                              │
│                                                                             │
│  6. GPU Passthrough                                                         │
│     ├── GRUB: intel_iommu=on iommu=pt                                       │
│     ├── VFIO modules                                                        │
│     ├── Blacklist radeon/amdgpu                                             │
│     └── Bind GPU to vfio-pci                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**The script is idempotent** - running it again on a healthy node skips cluster rejoin but still checks GPU config.

---

---

## K3s Join - CRITICAL Lessons Learned (January 2026)

### The Problem

When rejoining still-fawn to K3s cluster, repeated TLS handshake failures:
```
"rejected connection on peer endpoint","error":"remote error: tls: bad certificate"
```

Every join attempt would:
1. Add a learner member to pumped-piglet's etcd
2. Fail TLS handshake
3. Leave stale learner in etcd
4. Crash pumped-piglet's etcd (stuck trying to reach unreachable member)

### Root Cause

**Mixed CA certificates**: still-fawn had OLD CA files (`peer-ca.crt`, `server-ca.crt`) from previous cluster attempts mixed with NEW client certs from current attempt.

```
/var/lib/rancher/k3s/server/tls/etcd/peer-ca.crt     06:30 (OLD!)
/var/lib/rancher/k3s/server/tls/etcd/client.crt      06:59 (new)
```

K3s downloads CA from existing cluster during join. But if OLD CA files exist, they're used instead, causing TLS mismatch.

### Why Manual Cleanup Failed

`rm -rf /var/lib/rancher/k3s` doesn't remove everything:
- systemd service files remain (`/etc/systemd/system/k3s.service`)
- Service env file remains (`/etc/systemd/system/k3s.service.env`)
- K3s restarts and recreates state before join completes

### The Fix

**ALWAYS use `/usr/local/bin/k3s-uninstall.sh`** - it removes:
- All `/var/lib/rancher/k3s/*`
- All `/etc/rancher/k3s/*`
- systemd service files
- symlinks (`kubectl`, `crictl`, `ctr`)
- CNI state
- iptables rules

### If Primary etcd Gets Stuck

When pumped-piglet's etcd is stuck with stale member:

```bash
# On pumped-piglet VM
sudo systemctl stop k3s
sudo k3s server --cluster-reset
sudo systemctl start k3s
```

This removes ALL other members and makes pumped-piglet single-node again.

### Correct Sequence

1. **STOP** K3s on joining node
2. **VERIFY** primary etcd is healthy (single member, can run `etcdctl member list`)
3. **UNINSTALL** K3s on joining node with `k3s-uninstall.sh`
4. **VERIFY** cleanup (no `/var/lib/rancher/k3s`, no `/etc/systemd/system/k3s*`)
5. **FRESH INSTALL** K3s with join command
6. **WAIT** 60-90 seconds for etcd sync
7. **VERIFY** both nodes Ready

### References

- [GitHub #3597](https://github.com/k3s-io/k3s/issues/3597) - Unable to add new master to cluster
- [RKE2 Discussion #6180](https://github.com/rancher/rke2/discussions/6180) - Re-add master node
- [K3s HA Embedded Docs](https://docs.k3s.io/datastore/ha-embedded) - Official procedure

---

## Related Documentation

- [Proxmox Node Rejoin Automation](proxmox-node-rejoin-automation.md) - Full script documentation
- [K3s VM still-fawn Setup](k3s-vm-still-fawn-setup.md) - VM 108 configuration
- [Proxmox Cluster Node Addition](proxmox-cluster-node-addition.md) - General cluster procedures
- [K3s etcd Stale Member Removal](../troubleshooting/action-log-k3s-etcd-stale-member-removal.md) - October 2025 incident

---

## Tags

still-fawn, proxmox, zfs, rpool, disk-failure, recovery, alerting, voice-pe, home-assistant, runbook, cluster_manager, automation, python, k3s, etcd, tls-certificate, cluster-join, k3s-uninstall
