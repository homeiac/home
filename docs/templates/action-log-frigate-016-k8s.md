# Action Log Template: Frigate 0.16 K8s Deployment with Coral TPU

**Document Type**: Action Log Template
**Last Updated**: December 2025
**Blueprint**: `/Users/10381054/.claude/plans/wiggly-percolating-sunrise.md`
**Reference**: `proxmox/guides/google-coral-tpu-frigate-integration.md`

---

## Document Header

```
# Action Log: Frigate 0.16 K8s on <HOST_NAME>

**Date**: YYYY-MM-DD
**Operator**: [Name/AI Agent]
**GitHub Issue**: #XXX
**Target Host**: <PROXMOX_HOST> (<IP_ADDRESS>)
**K8s VM**: <VM_NAME> (VMID: <VMID>)
**Status**: [Planning | In Progress | Completed | Failed | Rolled Back]
```

---

## Pre-Operation State

### Infrastructure
| Component | Value |
|-----------|-------|
| Proxmox Host | [pumped-piglet.maas] |
| K8s VM Name | [k3s-vm-pumped-piglet-gpu] |
| K8s VM VMID | [105] |
| GPU | [RTX 3070] |
| Coral Location | [still-fawn.maas / to be moved] |

### Current Frigate (to be replaced)
| Component | Value |
|-----------|-------|
| Host | [still-fawn.maas] |
| Type | [LXC] |
| VMID | [110] |
| Version | [0.14.1] |
| Coral Status | [Working / Not Working] |
| Recordings Size | [XXX GB] |

### K8s Cluster Status
```bash
# Output of: kubectl get nodes
```

---

## Restore Points Created

| Point | State | Restore Command |
|-------|-------|-----------------|
| RP0 | Before anything | `pct rollback 110 pre-016-YYYYMMDD` |
| RP1 | After Coral move | Physical move Coral back |
| RP2 | After VM config | `cp 105.conf.bak 105.conf && qm restart 105` |
| RP3 | After K8s deploy | `kubectl delete namespace frigate` |

---

## Phase 0: Documentation Setup

### Step 0.1: Create Action Log Instance
**Timestamp**: [HH:MM]
**File Created**: `docs/troubleshooting/action-log-frigate-016-pumped-piglet.md`
**Status**: [ ] Pending

---

## Phase 1: Pre-Flight (Backup & Stop)

### Step 1.1: Snapshot still-fawn Frigate LXC
**Timestamp**: [HH:MM]
**Command**:
```bash
ssh root@still-fawn.maas "pct snapshot 110 pre-016-migration-$(date +%Y%m%d)"
```
**Output**:
```
[PASTE OUTPUT]
```
**Snapshot Name**: [pre-016-migration-YYYYMMDD]
**Status**: [ ] Pending

---

### Step 1.2: Stop still-fawn Frigate
**Timestamp**: [HH:MM]
**Command**:
```bash
ssh root@still-fawn.maas "pct stop 110"
```
**Status**: [ ] Pending

---

### Step 1.3: Verify Coral Released
**Timestamp**: [HH:MM]
**Command**:
```bash
ssh root@still-fawn.maas "lsusb | grep -E '(Google|Global)'"
```
**Coral Status**: [Still connected / Released]
**Status**: [ ] Pending

---

## Phase 2: Physical Hardware Move

### Step 2.1: Unplug Coral from still-fawn
**Timestamp**: [HH:MM]
**Action**: Physically disconnect Coral USB from still-fawn server
**Status**: [ ] Pending (USER ACTION REQUIRED)

---

### Step 2.2: Plug Coral into pumped-piglet
**Timestamp**: [HH:MM]
**USB Port Used**: [Front USB 3.0 / Rear USB 3.0 / etc.]
**Action**: Physically connect Coral USB to pumped-piglet server
**Status**: [ ] Pending (USER ACTION REQUIRED)

---

### Step 2.3: Verify Coral on pumped-piglet
**Timestamp**: [HH:MM]
**Command**:
```bash
ssh root@pumped-piglet.maas "lsusb | grep -E '(Google|Global)'"
```
**Output**:
```
[PASTE OUTPUT]
```
**Vendor ID**: [1a6e:089a (bootloader) / 18d1:9302 (initialized)]
**Bus**: [XXX]
**Device**: [XXX]
**Status**: [ ] Pending

---

## Phase 3: USB Passthrough to K8s VM

### Step 3.1: Install Prerequisites on Host
**Timestamp**: [HH:MM]
**Commands**:
```bash
ssh root@pumped-piglet.maas "apt update && apt install -y usbutils dfu-util"
```
**Output**:
```
[PASTE OUTPUT]
```
**Status**: [ ] Pending

---

### Step 3.2: Download Coral Firmware
**Timestamp**: [HH:MM]
**Command**:
```bash
ssh root@pumped-piglet.maas "mkdir -p /usr/local/lib/firmware && wget -O /usr/local/lib/firmware/apex_latest_single_ep.bin 'https://raw.githubusercontent.com/google-coral/libedgetpu/master/firmware/apex_latest_single_ep.bin'"
```
**Firmware Path**: `/usr/local/lib/firmware/apex_latest_single_ep.bin`
**Firmware Size**: [BYTES]
**Status**: [ ] Pending

---

### Step 3.3: Create udev Rules with Firmware Loading
**Timestamp**: [HH:MM]
**File**: `/etc/udev/rules.d/95-coral-init.rules`
**Content**:
```bash
# Coral USB Accelerator initialization
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="1a6e", ATTR{idProduct}=="089a", \
  RUN+="/usr/bin/dfu-util -D /usr/local/lib/firmware/apex_latest_single_ep.bin"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="18d1", ATTRS{idProduct}=="9302", \
  OWNER="root", MODE="0666", GROUP="plugdev"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="1a6e", ATTRS{idProduct}=="089a", \
  OWNER="root", MODE="0666", GROUP="plugdev"
```
**Status**: [ ] Pending

---

### Step 3.4: Reload udev and Initialize Coral
**Timestamp**: [HH:MM]
**Commands**:
```bash
ssh root@pumped-piglet.maas "udevadm control --reload-rules && udevadm trigger && sleep 5 && lsusb | grep -E '(1a6e|18d1)'"
```
**Before State**: [1a6e:089a / 18d1:9302]
**After State**: [1a6e:089a / 18d1:9302]
**Output**:
```
[PASTE OUTPUT]
```
**Status**: [ ] Pending

> **EXPECTED**: Coral changes from `1a6e:089a` (bootloader) to `18d1:9302` (Google Inc)
> **IF STILL 1a6e:089a**: Run `dfu-util -D /usr/local/lib/firmware/apex_latest_single_ep.bin` manually

---

### Step 3.5: Backup VM Config
**Timestamp**: [HH:MM]
**Command**:
```bash
ssh root@pumped-piglet.maas "cp /etc/pve/qemu-server/105.conf /etc/pve/qemu-server/105.conf.bak"
```
**Backup Path**: `/etc/pve/qemu-server/105.conf.bak`
**Status**: [ ] Pending

---

### Step 3.6: Add USB Passthrough to VM
**Timestamp**: [HH:MM]
**Command**:
```bash
ssh root@pumped-piglet.maas "qm set 105 -usb0 host=18d1:9302"
```
**Config Line Added**: `usb0: host=18d1:9302`
**Output**:
```
[PASTE OUTPUT]
```
**Status**: [ ] Pending

---

### Step 3.7: Restart K8s VM
**Timestamp**: [HH:MM]
**Commands**:
```bash
ssh root@pumped-piglet.maas "qm stop 105 && qm start 105"
```
**Output**:
```
[PASTE OUTPUT]
```
**Status**: [ ] Pending

---

### Step 3.8: Verify Coral in VM
**Timestamp**: [HH:MM]
**Command**:
```bash
ssh ubuntu@k3s-vm-pumped-piglet-gpu "lsusb | grep -E '(Google|Global)'"
```
**Output**:
```
[PASTE OUTPUT]
```
**Coral Visible in VM**: [Yes/No]
**Status**: [ ] Pending

> **IF NOT VISIBLE**: Check USB passthrough config, try physical replug

---

### Step 3.9: Install libedgetpu in VM
**Timestamp**: [HH:MM]

> **IMPORTANT**: Some VMs don't have SSH access. Use `qm guest exec` via Proxmox host instead:
> ```bash
> ssh root@HOST.maas "qm guest exec VMID -- apt-get install -y libedgetpu1-std"
> ```

**Commands** (if SSH works):
```bash
ssh ubuntu@VM_NAME
echo "deb https://packages.cloud.google.com/apt coral-edgetpu-stable main" | sudo tee /etc/apt/sources.list.d/coral-edgetpu.list
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -
sudo apt update && sudo apt install -y libedgetpu1-std
```

**Commands** (if SSH doesn't work - use qm guest exec):
```bash
ssh root@HOST.maas "qm guest exec VMID -- bash -c 'echo deb https://packages.cloud.google.com/apt coral-edgetpu-stable main | tee /etc/apt/sources.list.d/coral-edgetpu.list'"
ssh root@HOST.maas "qm guest exec VMID -- bash -c 'curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -'"
ssh root@HOST.maas "qm guest exec VMID -- apt-get update"
ssh root@HOST.maas "qm guest exec VMID -- apt-get install -y libedgetpu1-std"
```
**Output**:
```
[PASTE OUTPUT]
```
**Status**: [ ] Pending

---

### Step 3.10: Create udev Rules in VM
**Timestamp**: [HH:MM]
**Command**:
```bash
ssh ubuntu@k3s-vm-pumped-piglet-gpu "sudo tee /etc/udev/rules.d/99-coral.rules <<'EOF'
SUBSYSTEMS==\"usb\", ATTRS{idVendor}==\"18d1\", ATTRS{idProduct}==\"9302\", MODE=\"0666\"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger"
```
**Status**: [ ] Pending

---

### GO/NO-GO Decision Point: Phase 3
| Criterion | Result |
|-----------|--------|
| Coral initialized (18d1:9302) on host | [ ] Yes / [ ] No |
| USB passthrough configured | [ ] Yes / [ ] No |
| Coral visible in VM | [ ] Yes / [ ] No |

**Decision**: [ ] GO to Phase 4 / [ ] NO-GO - Rollback

---

## Phase 4: Manual K8s Deployment

### Step 4.1: Create Manifest Directory
**Timestamp**: [HH:MM]
**Command**:
```bash
mkdir -p ~/frigate-k8s-manifests && cd ~/frigate-k8s-manifests
```
**Status**: [ ] Pending

---

### Step 4.2: Create namespace.yaml
**Timestamp**: [HH:MM]
**File**: `~/frigate-k8s-manifests/namespace.yaml`
**Status**: [ ] Pending

---

### Step 4.3: Create pvc.yaml
**Timestamp**: [HH:MM]
**File**: `~/frigate-k8s-manifests/pvc.yaml`
**Config PVC Size**: [1Gi]
**Media PVC Size**: [100Gi]
**Status**: [ ] Pending

---

### Step 4.4: Create configmap.yaml
**Timestamp**: [HH:MM]
**File**: `~/frigate-k8s-manifests/configmap.yaml`
**Detector**: [edgetpu / usb]
**Face Recognition**: [enabled / disabled]
**Cameras**: [list from still-fawn config]
**Status**: [ ] Pending

---

### Step 4.5: Create deployment.yaml
**Timestamp**: [HH:MM]
**File**: `~/frigate-k8s-manifests/deployment.yaml`
**Image**: `ghcr.io/blakeblackshear/frigate:0.16.0`
**runtimeClassName**: `nvidia`
**nodeSelector**: `nvidia.com/gpu.present: "true"`
**Privileged**: `true`
**Status**: [ ] Pending

---

### Step 4.6: Create service.yaml
**Timestamp**: [HH:MM]
**File**: `~/frigate-k8s-manifests/service.yaml`
**Type**: `LoadBalancer`
**Ports**: `5000, 8554, 8555`
**Status**: [ ] Pending

---

### Step 4.7: Create kustomization.yaml
**Timestamp**: [HH:MM]
**File**: `~/frigate-k8s-manifests/kustomization.yaml`
**Status**: [ ] Pending

---

### Step 4.8: Apply Manifests
**Timestamp**: [HH:MM]
**Commands**:
```bash
cd ~/frigate-k8s-manifests
KUBECONFIG=~/kubeconfig kubectl apply -f namespace.yaml
KUBECONFIG=~/kubeconfig kubectl apply -f pvc.yaml
KUBECONFIG=~/kubeconfig kubectl apply -f configmap.yaml
KUBECONFIG=~/kubeconfig kubectl apply -f deployment.yaml
KUBECONFIG=~/kubeconfig kubectl apply -f service.yaml
```
**Output**:
```
[PASTE OUTPUT]
```
**Status**: [ ] Pending

---

## Phase 5: Manual Validation

### Step 5.1: Monitor Pod Startup
**Timestamp**: [HH:MM]
**Command**:
```bash
KUBECONFIG=~/kubeconfig kubectl get pods -n frigate -w
```
**Pod Name**: [frigate-XXXXXXXX-XXXXX]
**Pod Status**: [Pending / ContainerCreating / Running / CrashLoopBackOff]
**Time to Running**: [X minutes]
**Status**: [ ] Pending

---

### Step 5.2: Check Coral TPU Detection
**Timestamp**: [HH:MM]
**Command**:
```bash
KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate | grep -i "TPU\|coral\|edgetpu"
```
**Output**:
```
[PASTE OUTPUT]
```
**EdgeTPU Found**: [Yes/No]
**Status**: [ ] Pending

---

### Step 5.3: Verify GPU Detection
**Timestamp**: [HH:MM]
**Command**:
```bash
KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate | grep -i "nvidia\|cuda\|gpu"
```
**Output**:
```
[PASTE OUTPUT]
```
**GPU Detected**: [Yes/No]
**Status**: [ ] Pending

---

### Step 5.4: Check Detector Stats
**Timestamp**: [HH:MM]
**Command**:
```bash
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- curl -s http://localhost:5000/api/stats | jq '.detectors'
```
**Output**:
```json
[PASTE OUTPUT]
```
**Inference Speed**: [X.X ms]
**Status**: [ ] Pending

> **EXPECTED**: Coral inference speed ~8-15ms

---

### Step 5.5: Get LoadBalancer IP
**Timestamp**: [HH:MM]
**Command**:
```bash
KUBECONFIG=~/kubeconfig kubectl get svc -n frigate
```
**External IP**: [192.168.4.XX]
**Status**: [ ] Pending

---

### Step 5.6: Access Frigate UI
**Timestamp**: [HH:MM]
**URL**: `http://[EXTERNAL_IP]:5000`
**UI Loads**: [Yes/No]
**Status**: [ ] Pending

---

### GO/NO-GO Decision Point: Phase 5
| Criterion | Result |
|-----------|--------|
| Pod Running | [ ] Yes / [ ] No |
| Coral detected in logs | [ ] Yes / [ ] No |
| Inference speed ~8-15ms | [ ] Yes / [ ] No |
| GPU detected | [ ] Yes / [ ] No |
| UI accessible | [ ] Yes / [ ] No |

**Decision**: [ ] GO to Phase 6 / [ ] NO-GO - Troubleshoot / [ ] ROLLBACK

---

## Phase 6: Import Existing Recordings

### Step 6.1: Check still-fawn Recordings
**Timestamp**: [HH:MM]
**Command**:
```bash
ssh root@still-fawn.maas "du -sh /local-3TB-backup/subvol-113-disk-0/frigate/*"
```
**Output**:
```
[PASTE OUTPUT]
```
**Recordings Size**: [XXX GB]
**Clips Size**: [XXX GB]
**Status**: [ ] Pending

---

### Step 6.2: Import Recordings (NFS or rsync)
**Timestamp**: [HH:MM]
**Method**: [NFS / rsync]
**Commands Used**:
```bash
[PASTE COMMANDS]
```
**Duration**: [X hours X minutes]
**Status**: [ ] Pending

---

### Step 6.3: Verify Recordings in Frigate
**Timestamp**: [HH:MM]
**Command**:
```bash
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- ls -la /media/frigate/recordings/
```
**Recordings Visible**: [Yes/No]
**Status**: [ ] Pending

---

## Phase 7: Migrate Camera Config

### Step 7.1: Export still-fawn Camera Config
**Timestamp**: [HH:MM]
**Command**:
```bash
ssh root@still-fawn.maas "pct exec 110 -- cat /config/config.yml" > ~/frigate-old-config.yml
```
**Status**: [ ] Pending

---

### Step 7.2: Update ConfigMap
**Timestamp**: [HH:MM]
**Changes**:
- Hardware acceleration: `preset-vaapi` -> `preset-nvidia-h264`
- Cameras: [list cameras migrated]
**Status**: [ ] Pending

---

### Step 7.3: Apply Updated ConfigMap
**Timestamp**: [HH:MM]
**Command**:
```bash
KUBECONFIG=~/kubeconfig kubectl apply -f configmap.yaml
KUBECONFIG=~/kubeconfig kubectl rollout restart deployment/frigate -n frigate
```
**Status**: [ ] Pending

---

### Step 7.4: Verify Cameras Streaming
**Timestamp**: [HH:MM]
**Command**:
```bash
KUBECONFIG=~/kubeconfig kubectl exec -n frigate deployment/frigate -- curl -s http://localhost:5000/api/stats | jq '.cameras'
```
**Camera Status**:
| Camera | FPS | Detection | Status |
|--------|-----|-----------|--------|
| [NAME] | [X] | [X fps]   | [ ]    |

**Status**: [ ] Pending

---

## Phase 8: Face Recognition Setup

### Step 8.1: Verify Face Recognition Enabled
**Timestamp**: [HH:MM]
**Command**:
```bash
KUBECONFIG=~/kubeconfig kubectl logs -n frigate deployment/frigate | grep -i "face"
```
**Face Recognition Active**: [Yes/No]
**Status**: [ ] Pending

---

### Step 8.2: Add Face Samples
**Timestamp**: [HH:MM]
**Action**: Via Frigate UI
**Faces Added**: [list names]
**Status**: [ ] Pending

---

## Phase 9: Commit to GitOps

### Step 9.1: Copy Manifests to GitOps
**Timestamp**: [HH:MM]
**Command**:
```bash
mkdir -p ~/code/home/gitops/clusters/homelab/apps/frigate
cp ~/frigate-k8s-manifests/*.yaml ~/code/home/gitops/clusters/homelab/apps/frigate/
```
**Status**: [ ] Pending

---

### Step 9.2: Update Main Kustomization
**Timestamp**: [HH:MM]
**File**: `gitops/clusters/homelab/apps/kustomization.yaml`
**Line Added**: `- frigate`
**Status**: [ ] Pending

---

### Step 9.3: Commit and Push
**Timestamp**: [HH:MM]
**Commands**:
```bash
cd ~/code/home
git add gitops/clusters/homelab/apps/frigate/
git add gitops/clusters/homelab/apps/kustomization.yaml
git commit -m "feat: add Frigate 0.16 with Coral TPU and GPU face recognition"
git push
```
**Status**: [ ] Pending

---

### Step 9.4: Verify Flux Reconciliation
**Timestamp**: [HH:MM]
**Command**:
```bash
KUBECONFIG=~/kubeconfig flux reconcile kustomization apps --with-source
```
**Status**: [ ] Pending

---

## Issues Encountered

### Issue 1: [Description]
**Severity**: [Low/Medium/High/Critical]
**Time Encountered**: [HH:MM]
**Symptoms**:
- [Symptom 1]
- [Symptom 2]

**Root Cause**: [Analysis]

**Resolution**:
```bash
[Commands used]
```

**Prevention**: [How to prevent in future]

---

## Rollback Actions (if applicable)

**Trigger**: [What necessitated rollback]
**Timestamp**: [HH:MM]
**Commands Used**:
```bash
[PASTE ROLLBACK COMMANDS]
```
**Result**: [Success/Partial/Failed]

---

## Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | [Success/Partial/Failed] |
| **Start Time** | [HH:MM] |
| **End Time** | [HH:MM] |
| **Total Duration** | [X hours Y minutes] |
| **Frigate Version** | [0.16.0] |
| **Coral Inference Speed** | [X.X ms] |
| **GPU** | [RTX 3070] |
| **Face Recognition** | [Enabled/Disabled] |
| **Recordings Imported** | [XXX GB] |

### Success Criteria Checklist
- [ ] Coral TPU detected (~8-15ms inference)
- [ ] GPU detected for face recognition
- [ ] All cameras streaming
- [ ] Object detection working
- [ ] Face recognition working
- [ ] Recordings imported from still-fawn
- [ ] Recordings being saved to PVC
- [ ] Frigate UI accessible via MetalLB
- [ ] GitOps managed by Flux

### Performance Comparison

| Metric | still-fawn LXC | K8s GPU |
|--------|----------------|---------|
| Detector | [Coral] | [Coral + GPU] |
| Inference Speed | [X.X ms] | [X.X ms] |
| Face Recognition | [No] | [Yes] |

---

## Follow-Up Actions

- [ ] Monitor Frigate stability for 24 hours
- [ ] Configure recording retention policies
- [ ] Train face recognition with more samples
- [ ] Update Home Assistant Frigate integration URL
- [ ] Close GitHub issue
- [ ] Update blueprint if issues were found
- [ ] Consider: keep still-fawn snapshot or delete?

---

## Tags

frigate, coral, tpu, usb, k8s, kubernetes, gpu, rtx3070, face-recognition, pumped-piglet, action-log
