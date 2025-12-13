# Coral TPU + AMD GPU on K8s: A Lesson in Reading Documentation

*When AI assistants repeatedly waste your time by not checking the docs first*

---

```
    +-------------------+          +------------------------+
    |  still-fawn       |          |  still-fawn K8s VM     |
    |  Proxmox Host     |    ->    |  Coral USB TPU         |
    |  Coral + AMD GPU  |          |  AMD RX 580 VAAPI      |
    +-------------------+          +------------------------+

    Goal: Coral detection + AMD GPU decode
    Reality: 28ms Coral + working VAAPI + frustration
```

## The Goal

Move Frigate 0.16 to the still-fawn K3s node with:
- Coral USB TPU for efficient object detection (0% CPU overhead)
- AMD RX 580 GPU for VAAPI hardware decode
- Face recognition as a bonus

The pumped-piglet deployment was using ONNX detection at 45% CPU. Coral promised 0% CPU overhead.

## The VT-d Disaster (Read the F***ing Docs)

**Hour 1-3: Kernel command line hell**

I spent hours trying different kernel parameters:
```bash
intel_iommu=on iommu=pt vfio-pci.ids=1002:67df,1002:aaf0
```

Every combination failed with `error -22` on vfio-pci bind. I tried:
- Different IOMMU groups
- ACS override patches
- Kernel module load order
- Various vfio configurations

**The actual problem**: VT-d was disabled in BIOS.

```bash
ls /sys/kernel/iommu_groups/ | wc -l
# 0 ← This should have been my FIRST check
```

**Where to find VT-d on ASUS Intel boards**:
- BIOS → Advanced → **System Agent Configuration** → VT-d → Enabled

Not under CPU settings. Not under Virtualization. Under "System Agent" where nobody looks.

**The documentation I should have read first**: `proxmox/guides/nvidia-RTX-3070-k3s-PCI-passthrough.md` - which already documented this exact BIOS path.

> "You should have told me this upfront... and how many times I told you read the RTX 3070 docs?"

Fair point.

## The detect.enabled Mistake (Fool Me Twice)

After getting GPU passthrough working, cameras showed no detection. The config:

```yaml
cameras:
  trendnet_ip_572w:
    detect:
      width: 1280
      height: 800
      fps: 5
```

Missing: `enabled: true`

**This was the SAME mistake from the pumped-piglet migration.** I had already made this error once and somehow made it again.

> "Why the f*** you do this? This happened on the piglet too. Fool me once..."

The user had to explicitly demand I search all YAML files and fix every instance. Both `configmap.yaml` and `configmap-coral.yaml` needed fixing.

**Lesson**: Create a pre-deployment checklist. Every camera config MUST have:
```yaml
detect:
  enabled: true  # REQUIRED - detection won't work without this
```

## USB 3.0 Passthrough Matters

Coral TPU was showing 87ms inference instead of expected 10ms. Logs showed:
```
TPU found
Created TensorFlow Lite XNNPACK delegate for CPU
```

The problem: USB passthrough was using EHCI (USB 2.0) instead of XHCI (USB 3.0).

dmesg showed: `invalid maxpacket 1024` errors

**Fix**:
```bash
qm set 108 --usb0 host=18d1:9302,usb3=1
```

After USB3 fix: 28ms inference (still not 10ms due to VM passthrough overhead vs LXC direct access).

## AMD GPU Stats: The LIBVA_DRIVER_NAME Discovery

Frigate showed `intel-vaapi` with empty GPU stats even though AMD VAAPI was working. The issue: Frigate's `is_vaapi_amd_driver()` function checks for "AMD Radeon Graphics" but vainfo returns "AMD Radeon RX 580 Series".

**Fix**: Set environment variable in deployment:
```yaml
env:
  - name: LIBVA_DRIVER_NAME
    value: "radeonsi"
```

After this, Frigate correctly showed `amd-vaapi` with GPU utilization stats via `radeontop`.

## The Gamma Filter Bug (Frigate 0.16)

CPU was at 26% even with Coral handling detection. Investigation showed ffmpeg using a CPU gamma filter:

```
-vf fps=5,scale_vaapi=w=1920:h=1080,hwdownload,format=nv12,eq=gamma=1.4:gamma_weight=0.5
```

The `eq=gamma` filter runs on CPU after `hwdownload` from GPU memory.

Frigate 0.16 has an env var to disable this: `FFMPEG_DISABLE_GAMMA_EQUALIZER=1`

**But it doesn't work.** The code has a bug:

```python
# In ffmpeg_presets.py
scale.replace(...)  # Returns new string but doesn't assign!
# Should be: scale = scale.replace(...)
```

The env var is checked, but the replacement result is discarded. Classic Python string immutability mistake.

## Face Recognition CPU Cost

With face recognition enabled and no GPU acceleration (AMD RX 580 doesn't support OpenVINO/ROCm 6.x):

| State | CPU |
|-------|-----|
| Baseline (no person) | 27% |
| Face recognition active | **62%** |
| **Delta** | **+35%** |

The RX 580 (Polaris/gfx803) was dropped from ROCm 6.x. ROCm 5.7.1 was the last version with support, and even that requires custom compilation with `HSA_OVERRIDE_GFX_VERSION=8.0.3`.

## Final Results

| Metric | Value |
|--------|-------|
| Coral TPU inference | 28ms |
| AMD VAAPI decode | Working (3% GPU) |
| Baseline CPU | 27% |
| Face recognition CPU | 62% (CPU fallback) |
| Face recognition | Works but expensive |

## Lessons Learned

### 1. Always Check BIOS First for Passthrough Issues
```bash
# FIRST command when PCI passthrough fails
ls /sys/kernel/iommu_groups/ | wc -l
# If 0 → BIOS, not kernel
```

### 2. Read Your Own Documentation
The VT-d BIOS path was already documented. The detect.enabled requirement was a known issue. Reading existing docs before debugging saves hours.

### 3. Pre-deployment Checklist
Every Frigate camera config must have:
- [ ] `detect: enabled: true`
- [ ] Correct resolution matching camera capability
- [ ] FPS appropriate for the camera

### 4. USB 3.0 for Coral TPU
Always use `usb3=1` flag when passing Coral USB to VMs:
```bash
qm set VMID --usb0 host=18d1:9302,usb3=1
```

### 5. AMD Consumer GPUs Have Limited Compute Support
- ROCm dropped Polaris (RX 400/500 series) in version 6.x
- VAAPI for video decode works fine
- ML inference (face recognition) falls back to CPU
- For GPU-accelerated ML, stick with NVIDIA

## Next Steps

Move Coral USB to pumped-piglet where the RTX 3070 can handle:
- Coral: Object detection (~10ms)
- NVIDIA: Face recognition (GPU accelerated)
- NVIDIA: Video decode (NVDEC)

Best of both worlds instead of Coral + CPU face recognition.

---

*Tags: frigate, coral, coral-tpu, amd, radeon, vaapi, vt-d, iommu, gpu-passthrough, proxmox, k8s, kubernetes, face-recognition, troubleshooting, documentation*
