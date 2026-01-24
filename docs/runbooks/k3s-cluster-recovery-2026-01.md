# K3s Cluster Recovery Runbook - January 2026

## Summary

Full cluster recovery after still-fawn disk failure. Documents all steps to restore K3s cluster with GPU passthrough, Frigate, Ollama, and all dependent services.

## Cluster Configuration

### Nodes
| Node | IP | Role | Hardware |
|------|-----|------|----------|
| k3s-vm-pumped-piglet-gpu | 192.168.4.210 | control-plane, primary | RTX 3070 GPU |
| k3s-vm-still-fawn | 192.168.4.212 | control-plane | AMD RX 580 GPU, Coral USB TPU |

### kube-vip VIP
- **VIP**: 192.168.4.79
- **IMPORTANT**: VIP must be in TLS-SAN for kubectl to work via VIP

## Recovery Steps

### 1. TLS-SAN Configuration for VIP Access

The kubeconfig must use the VIP for HA access, but VIP must be in the K3s certificate SANs.

```bash
# Check current TLS-SAN status
cd ~/code/home/proxmox/homelab
poetry run python -m homelab.k3s_manager status

# Add VIP to TLS-SAN and rotate certs
poetry run python -m homelab.k3s_manager prepare-kube-vip --dry-run  # Preview
poetry run python -m homelab.k3s_manager prepare-kube-vip            # Apply

# Update kubeconfig to use VIP
sed -i '' 's/192.168.4.210/192.168.4.79/' ~/kubeconfig
```

Config file: `proxmox/homelab/config/k3s.yaml`

### 2. GPU Passthrough to K3s VMs

#### NVIDIA GPU (pumped-piglet)
Handled by GPU Operator with time-slicing:
- Config: `gitops/clusters/homelab/infrastructure/gpu-operator/time-slicing-config.yaml`
- 4 virtual GPUs from 1 physical RTX 3070

#### AMD GPU + Coral TPU (still-fawn)
Requires manual passthrough job because Crossplane API lacks USB/PCI permissions.

**Prerequisites:**
1. SSH key secret in SOPS: `gitops/clusters/homelab/infrastructure/crossplane/proxmox-ssh-key.sops.yaml`
2. VM must be STOPPED before passthrough changes

**Process:**
```bash
# 1. Drain the node
KUBECONFIG=~/kubeconfig kubectl drain k3s-vm-still-fawn --ignore-daemonsets --delete-emptydir-data --force

# 2. Stop the VM
ssh root@still-fawn.maas "qm stop 108"

# 3. Add passthrough devices
ssh root@still-fawn.maas "
qm set 108 --usb0 host=1a6e:089a,usb3=1   # Coral TPU mode 1
qm set 108 --usb1 host=18d1:9302,usb3=1   # Coral TPU mode 2
qm set 108 --hostpci0 0000:01:00,pcie=1   # AMD GPU
"

# 4. Start VM
ssh root@still-fawn.maas "qm start 108"

# 5. Wait for boot, then load AMD GPU driver
sleep 60
ssh root@still-fawn.maas "qm guest exec 108 -- bash -c 'apt-get update && apt-get install -y linux-modules-extra-\$(uname -r) && modprobe amdgpu'"

# 6. Verify GPU is available
ssh root@still-fawn.maas "qm guest exec 108 -- ls -la /dev/dri/"
# Should show: card0, renderD128

# 7. Uncordon node
KUBECONFIG=~/kubeconfig kubectl uncordon k3s-vm-still-fawn

# 8. Restart Frigate to pick up GPU
KUBECONFIG=~/kubeconfig kubectl rollout restart deployment/frigate -n frigate
```

**USB3 passthrough note**: The `usb3=1` flag is critical - it uses xHCI controller for USB 3.0 speeds, matching LXC performance.

### 3. MetalLB IP Assignments

**CRITICAL**: Always use explicit IP annotations to prevent race conditions.

| IP | Service | Namespace |
|----|---------|-----------|
| 192.168.4.80 | traefik | kube-system |
| 192.168.4.81 | frigate | frigate |
| 192.168.4.82 | stable-diffusion-webui | stable-diffusion |
| 192.168.4.84 | frigate-webrtc-udp | frigate |
| 192.168.4.85 | ollama-lb | ollama |
| 192.168.4.120 | samba-lb | samba |

Documentation: `gitops/clusters/homelab/infrastructure-config/metallb-config/IP-ASSIGNMENTS.md`

### 4. SOPS Secrets

All secrets use age encryption with key: `age1uwvq3llqjt666t4ckls9wv44wcpxxwlu8svqwx5kc7v76hncj94qg3tsna`

Created secrets:
- `gitops/clusters/homelab/apps/claudecodeui/secrets/ghcr-credentials.sops.yaml`
- `gitops/clusters/homelab/apps/frigate/secrets/frigate-credentials.sops.yaml`
- `gitops/clusters/homelab/apps/frigate/secrets/ghcr-creds.sops.yaml`
- `gitops/clusters/homelab/infrastructure/monitoring/secrets/smtp-credentials.sops.yaml`
- `gitops/clusters/homelab/infrastructure/tailscale/secrets/operator-oauth.sops.yaml`
- `gitops/clusters/homelab/apps/samba/secrets/samba-users.sops.yaml`
- `gitops/clusters/homelab/infrastructure/crossplane/proxmox-ssh-key.sops.yaml`

### 5. Ollama Models for Home Assistant

HA uses two Ollama integrations:

1. **ollama** (conversation): `qwen2.5:7b`
2. **llmvision** (image analysis): `gemma3:4b`

```bash
# Pull required models
KUBECONFIG=~/kubeconfig kubectl exec -n ollama deploy/ollama-gpu -- ollama pull qwen2.5:7b
KUBECONFIG=~/kubeconfig kubectl exec -n ollama deploy/ollama-gpu -- ollama pull gemma3:4b

# Verify
KUBECONFIG=~/kubeconfig kubectl exec -n ollama deploy/ollama-gpu -- ollama list

# Reload HA to pick up models
ssh -p 22222 root@192.168.4.240 "ha core restart"
```

**Finding the model HA expects:**
```bash
ssh -p 22222 root@192.168.4.240 "cat /mnt/data/supervisor/homeassistant/.storage/core.config_entries" | jq '.data.entries[] | select(.domain == "ollama") | .subentries[].data.model'
```

### 6. Frigate Camera Network

Cameras are on ISP network (192.168.1.x), not homelab (192.168.4.x).

| Camera | IP | Connection | Status |
|--------|-----|------------|--------|
| TrendNet | 192.168.1.107 | Wired | Works |
| Reolink Doorbell | 192.168.1.10 | 5GHz WiFi | Depends on AT&T router |
| Living Room (E1 Zoom) | 192.168.1.140 | 5GHz WiFi | Depends on AT&T router |

**Routing**: K3s pods reach 192.168.1.x via OPNsense (192.168.4.1) which routes to ISP network.

### Reolink Camera Setup - CRITICAL

When adding a new Reolink camera or after camera reset, you MUST manually enable streaming protocols:

1. Open Reolink App or Web UI
2. Go to **Network → Advanced → Server Settings**
3. Enable:
   - HTTP
   - HTTPS
   - RTMP
   - RTSP (if separate option)

**Without this**: Camera will refuse RTSP connections on port 554 even though it's on the network. Symptom: `connection refused` on port 554.

## SSH Access to HAOS

HAOS VM 116 on chief-horse.maas has SSH via dropbear on port 22222.

```bash
# Direct SSH (if key configured)
ssh -p 22222 root@192.168.4.240 "command"

# Via qm guest exec (always works)
ssh root@chief-horse.maas "qm guest exec 116 -- command"

# Using scripts
/Users/10381054/code/home/scripts/haos/read-from-ha.sh /path/in/haos
/Users/10381054/code/home/scripts/haos/copy-to-ha.sh local_file /path/in/haos
```

Setup guide: `docs/source/md/homeassistant-os-ssh-access-setup.md`

## Verification Commands

```bash
# Cluster health
KUBECONFIG=~/kubeconfig kubectl get nodes
KUBECONFIG=~/kubeconfig kubectl get pods -A --field-selector=status.phase!=Running

# GPU availability
KUBECONFIG=~/kubeconfig kubectl get nodes -o custom-columns="NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu"

# Frigate GPU access
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deploy/frigate -- ls -la /dev/dri/
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deploy/frigate -- vainfo --display drm --device /dev/dri/renderD128

# Coral TPU
KUBECONFIG=~/kubeconfig kubectl logs -n frigate deploy/frigate | grep -i "TPU\|coral"

# Ollama
curl -s http://192.168.4.85/api/tags | jq '.models[].name'

# HA integrations
HA_URL=http://192.168.4.240:8123 /Users/10381054/code/home/scripts/haos/list-integrations.sh | grep -i ollama
```

## Key Files

| Purpose | Path |
|---------|------|
| K3s config | `proxmox/homelab/config/k3s.yaml` |
| K3s manager | `proxmox/homelab/src/homelab/k3s_manager.py` |
| GPU passthrough job | `gitops/clusters/homelab/instances/job-vm108-passthrough.yaml` |
| GPU time-slicing | `gitops/clusters/homelab/infrastructure/gpu-operator/time-slicing-config.yaml` |
| MetalLB IPs | `gitops/clusters/homelab/infrastructure-config/metallb-config/IP-ASSIGNMENTS.md` |
| Frigate config | `gitops/clusters/homelab/apps/frigate/configmap.yaml` |
| HA SSH setup | `docs/source/md/homeassistant-os-ssh-access-setup.md` |

## Lessons Learned

1. **Always verify GPU passthrough** - don't assume "node Ready" means GPU works
2. **USB3 flag matters** - `usb3=1` gives near-native Coral TPU performance in VM
3. **VIP needs TLS-SAN** - kubeconfig pointing to VIP fails without cert update
4. **MetalLB race conditions** - explicit IP annotations prevent IP stealing on cluster rebuild
5. **SOPS for all secrets** - never create secrets manually with kubectl
6. **Check HA config for models** - don't guess Ollama model names, read `.storage/core.config_entries`
7. **Face recognition requires bootstrap** - must upload at least one face image in UI before faces appear in Train tab

## Frigate Face Recognition Setup

Face recognition won't show any faces in the Train tab until you bootstrap it:

1. **Upload at least one face image first** - Go to Frigate UI → Faces → click "+" to add a person
2. **Add a clear headshot** for that person (e.g., "G" for yourself)
3. **After this**, detected faces will start appearing in the Train tab
4. **Resolution matters** - detect stream should be at least 1280x720 for good face detection
5. **Camera angle** - works best on doorbells/eye-level cameras, not ceiling-mounted

Config requirements:
```yaml
face_recognition:
  enabled: true
  model_size: large
  min_area: 500  # Lower if faces are small
```

Reference: [Frigate Face Recognition Docs](https://docs.frigate.video/configuration/face_recognition/)

## Mistakes Made During Recovery (Learn From These)

This section documents errors made during the recovery session to prevent repeating them.

### 1. Claimed GPU Was Working Without Verification
**What happened**: Reported "still-fawn is working" after seeing node Ready status, but never verified GPU passthrough was actually configured.

**Result**: User had to discover Frigate had no GPU access. The passthrough job hadn't run because its SSH key secret was missing.

**Lesson**: "Node Ready" ≠ "Everything Works". Always verify hardware passthrough with actual device checks (`ls /dev/dri/`, `vainfo`, etc.).

### 2. Guessed Ollama Model Names Instead of Checking Config
**What happened**: Assumed HA needed `gemma3:4b` for conversation without checking what model HA actually expected.

**Result**: Pulled wrong model. HA actually needed `qwen2.5:7b` for conversation (gemma3 is for llmvision image analysis).

**Lesson**: Never guess configuration. Always read the actual config:
```bash
ssh -p 22222 root@192.168.4.240 "cat /mnt/data/supervisor/homeassistant/.storage/core.config_entries" | jq '.data.entries[] | select(.domain == "ollama")'
```

### 3. Forgot HAOS SSH Access Exists
**What happened**: Repeatedly used slow `qm guest exec` method to access HAOS instead of direct SSH.

**Result**: Wasted time and frustrated user who had already documented SSH access.

**Lesson**: HAOS has SSH on port 22222:
```bash
ssh -p 22222 root@192.168.4.240 "command"
```
Check existing documentation before reinventing access methods.

### 4. Did Not Check for Missing SOPS Secret Before Claiming Job Would Work
**What happened**: Said the GPU passthrough K8s Job would handle everything, but the job required an SSH key secret that didn't exist.

**Result**: Job couldn't run. Had to manually create the SOPS-encrypted secret and run passthrough commands by hand.

**Lesson**: Before claiming automation will work, verify all dependencies exist:
```bash
kubectl get secret <secret-name> -n <namespace>
```

### 5. Assumed Face Recognition Would Auto-Populate
**What happened**: Configured face_recognition in Frigate config and expected faces to appear in Train tab automatically.

**Result**: Train tab remained empty. Frigate requires at least one face to be manually uploaded before it starts collecting detected faces.

**Lesson**: Read the docs. Face recognition needs bootstrapping - upload one face first, then detections appear.

### 6. Did Not Update Camera IPs in Config After Network Changes
**What happened**: Living room camera IP changed from 192.168.1.140 to 192.168.1.183, but initially kept checking old IP.

**Result**: Camera appeared offline until config was updated with correct IP.

**Lesson**: When cameras stop working, verify current IP first (check router DHCP leases or Reolink app), then update Frigate config.
