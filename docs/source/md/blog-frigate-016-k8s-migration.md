# Migrating Frigate to Kubernetes with GPU Face Recognition

*Lessons learned moving from LXC to K8s, and why your NVR doesn't need GPU encoding*

---

```
    +-------------------+          +------------------------+
    |  still-fawn       |    ->    |  pumped-piglet K8s     |
    |  LXC 110          |          |  RTX 3070 GPU          |
    |  Frigate 0.14     |          |  Frigate 0.16          |
    |  Coral USB TPU    |          |  Face Recognition!     |
    +-------------------+          +------------------------+
```

## The Goal

Upgrade from Frigate 0.14 on an LXC container to Frigate 0.16 on Kubernetes with:
- Face recognition (new in 0.16)
- RTX 3070 GPU for hardware acceleration
- Proper GitOps deployment
- Zero downtime migration with rollback capability

## The Humbling Moment

I confidently added NVENC encoding args to the config:

```yaml
ffmpeg:
  output_args:
    record: -f segment -segment_time 10 -c:v h264_nvenc -preset p2 -c:a aac
```

Then I opened a [GitHub issue](https://github.com/blakeblackshear/frigate/issues/21244) requesting a `preset-record-nvidia-h264` preset. Nicolas Mowen (Frigate maintainer) promptly closed it with:

> "Frigate doesn't do encoding in any case, regardless of what GPU you have. Frigate copies the recordings from the camera."

**Oops.**

## What GPU Actually Does in Frigate

| Function | Hardware | What Happens |
|----------|----------|--------------|
| **Decoding** | NVDEC | Decode camera streams for detector analysis |
| **Face Recognition** | CUDA | ML inference for face detection/recognition |
| **Birdseye View** | NVENC | Encode the combined multi-camera view |
| **go2rtc Transcode** | NVENC | Convert MJPEG cameras to H264 |
| **Recordings** | **Nothing** | Stream copy (`-c copy`) - no encoding! |

The `enc: 3%` I saw in `nvidia-smi` was from **go2rtc** transcoding my old MJPEG camera, not from recording.

### Why No Recording Encoding?

Cameras already send H.264/H.265 streams. Re-encoding would:
- Waste GPU/CPU cycles
- Potentially reduce quality
- Add latency
- Provide zero benefit

Frigate just copies the already-encoded stream directly to disk.

## The Architecture

```
pumped-piglet (Proxmox Host)
├── RTX 3070 GPU (VFIO passthrough)
└── k3s-vm-pumped-piglet-gpu (VMID 105)
    └── Frigate 0.16 Pod
        ├── CPU Detector: ~10ms inference
        ├── NVDEC: Hardware video decoding
        ├── Face Recognition: GPU-accelerated
        └── go2rtc: MJPEG→H264 with #hardware flag
```

## Key Configuration

### CPU Detector (Not GPU)

Frigate 0.16 removed built-in TensorRT. Options are:
1. **CPU detector** - 10ms inference, sufficient for 3 cameras at 5fps
2. **ONNX with CUDA** - Requires building your own YOLOv9 model

I went with CPU - 10ms is fast enough and keeps GPU free for face recognition.

```yaml
detectors:
  cpu:
    type: cpu
    num_threads: 4
```

### MQTT Client ID Matters

Running two Frigate instances? They'll fight over MQTT if using the same client_id:

```yaml
mqtt:
  enabled: true
  host: homeassistant.maas
  client_id: frigate-k8s  # Unique per instance!
```

### go2rtc Hardware Transcoding

For MJPEG cameras, go2rtc handles the transcode with GPU:

```yaml
go2rtc:
  streams:
    mjpeg_cam: "ffmpeg:http://camera/stream#video=h264#hardware"
```

The `#hardware` flag tells go2rtc to use GPU encoding.

## Migration Scripts

Created a full suite of scripts for safe migration:

| Script | Purpose |
|--------|---------|
| `verify-frigate-k8s.sh` | Health checks before migration |
| `update-ha-frigate-url.sh` | Update HA config via QEMU guest agent |
| `shutdown-still-fawn-frigate.sh -y` | Safe LXC shutdown with auto-confirm |
| `rollback-to-still-fawn.sh` | Restore LXC if K8s fails |

### Updating Home Assistant Without UI

The [previous blog post](blog-frigate-server-migration.md) technique still works:

```bash
# Update URL via QEMU guest agent
ssh root@chief-horse.maas 'qm guest exec 116 -- sed -i \
  "s|http://old-url|http://new-url|g" \
  /mnt/data/supervisor/homeassistant/.storage/core.config_entries'

# Restart HA
ssh root@chief-horse.maas 'qm guest exec 116 -- ha core restart'
```

## Lessons Learned

### 1. Read the Architecture First

Before assuming GPU features, understand the data flow:
- Camera → Frigate: Decode for detection (GPU helps)
- Frigate → Disk: Stream copy (GPU not used)
- Frigate → Browser: Re-encode for live view (GPU helps)

### 2. Frigate 0.16 Breaking Changes

- TensorRT detector removed (use ONNX or CPU)
- `record.events.retain.default` deprecated
- `version` must be string: `"0.16"` not `0.16`

### 3. Test Before Committing

The migration script pattern works well:
1. Deploy new instance alongside old
2. Verify with health check scripts
3. Update HA to point to new instance
4. Shutdown old instance (keep for rollback)
5. Only delete old instance after days of stability

### 4. Scripts for Everything

Even one-liners should be scripts:
- Documented and version controlled
- Idempotent (can run multiple times safely)
- Include rollback instructions
- Support `-y` flag for automation

## Current Status

- Frigate 0.16 running on K8s with GPU
- All 3 cameras streaming at 5fps
- Face recognition enabled (large model)
- HA integration working via direct LB IP
- Old LXC stopped but preserved for rollback
- [DNS issue](https://github.com/homeiac/home/issues/169) pending for `frigate.app.homelab`

## Files

All manifests and scripts committed to:
- `k8s/frigate-016/` - Kubernetes manifests
- `scripts/frigate/` - Migration and verification scripts

---

*Sometimes the best way to learn is to confidently make a mistake in public. Thanks to Nicolas Mowen for the quick correction.*

**Tags:** frigate, kubernetes, k8s, gpu, nvidia, nvenc, nvdec, face-recognition, migration, home-assistant, proxmox, homelab
