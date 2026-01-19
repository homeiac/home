# Frigate Reolink Camera Setup: HTTP-FLV, H.265, and Frigate+

**Date**: 2026-01-19
**Tags**: frigate, reolink, http-flv, h265, coral-tpu, frigate-plus, go2rtc

## TL;DR

Setting up Reolink cameras in Frigate revealed several gotchas:
- HTTP-FLV is recommended but only works with H.264 (FFmpeg 7.x limitation)
- Reolink E1 Zoom defaults to H.265 encoding - use RTSP instead
- Reolink Video Doorbell WiFi uses H.264 - HTTP-FLV works fine
- Frigate+ models run on Coral TPU and include package detection
- Always backup before config changes (learned the hard way)

## The Setup

Four cameras in Frigate running on K3s:
1. **Old IP Camera** (MJPEG) - transcoded to H.264 via go2rtc
2. **TrendNet IP-572W** - direct RTSP
3. **Reolink Video Doorbell WiFi** - HTTP-FLV (recommended)
4. **Reolink E1 Zoom** - RTSP (HTTP-FLV fails with H.265)

## HTTP-FLV vs RTSP for Reolink

Frigate docs recommend HTTP-FLV for Reolink cameras:

```yaml
go2rtc:
  streams:
    reolink_doorbell_main: "ffmpeg:http://camera-ip/flv?port=1935&app=bcs&stream=channel0_main.bcs&user=USER&password=PASS#video=copy#audio=copy#audio=opus"
    reolink_doorbell_sub: "ffmpeg:http://camera-ip/flv?port=1935&app=bcs&stream=channel0_ext.bcs&user=USER&password=PASS#video=copy"
```

This works great for the doorbell. But when I tried the same for the E1 Zoom:

```
ffmpeg.living_room.record ERROR: Invalid data found when processing input
```

## The H.265 Problem

Checking the codec via go2rtc API revealed the issue:

```bash
curl -s "http://localhost:1984/api/streams?src=living_room_main" | jq '.producers[0].medias'
# ["video, recvonly, H265", ...]
```

The E1 Zoom encodes in **H.265 (HEVC)** by default. HTTP-FLV with H.265 requires FFmpeg 8.0+, but Frigate 0.16 ships with FFmpeg 7.1.2.

Reference: [go2rtc issue #1938](https://github.com/AlexxIT/go2rtc/issues/1938)

### The Fix: Use RTSP for H.265 Cameras

```yaml
go2rtc:
  streams:
    # Doorbell (H.264) - HTTP-FLV works
    reolink_doorbell_main: "ffmpeg:http://doorbell-ip/flv?port=1935&app=bcs&stream=channel0_main.bcs&user=USER&password=PASS#video=copy#audio=copy#audio=opus"

    # E1 Zoom (H.265) - use RTSP instead
    living_room_main: "rtsp://USER:PASS@192.168.1.140:554/h264Preview_01_main"
    living_room_sub: "rtsp://USER:PASS@192.168.1.140:554/h264Preview_01_sub"
```

Future Frigate versions with FFmpeg 8.0+ should support HTTP-FLV with H.265.

## Separate Main/Sub Streams

Best practice: use main stream for recording, sub stream for detection:

```yaml
cameras:
  living_room:
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/living_room_main
          input_args: preset-rtsp-restream
          roles:
            - record
        - path: rtsp://127.0.0.1:8554/living_room_sub
          input_args: preset-rtsp-restream
          roles:
            - detect
    detect:
      width: 640
      height: 480
      fps: 5
```

This reduces CPU/TPU load - detection runs on lower resolution while recordings stay high quality.

## Frigate+ for Package Detection

Frigate+ subscription ($50/year) provides improved detection models that run on Coral TPU:

```yaml
model:
  path: plus://c7b38453956cda87076baba4aca213e6

detectors:
  coral:
    type: edgetpu
    device: usb
```

Key points:
- Models are downloaded and cached locally
- They persist even after subscription ends
- Includes package detection (not in base model)
- Still runs on Coral TPU (~13ms inference)

The model isn't "installed" on the Coral - it's loaded into TPU memory at runtime, same as the base model.

## ONVIF for PTZ

E1 Zoom supports PTZ via ONVIF:

```yaml
cameras:
  living_room:
    onvif:
      host: 192.168.1.140
      port: 8000
      user: "{FRIGATE_CAM_LIVINGROOM_USER}"
      password: "{FRIGATE_CAM_LIVINGROOM_PASS}"
```

## OpenVINO Warning (Harmless)

You might see:
```
OpenVINO failed to build model, using CPU instead
[GPU] Can't get OPTIMIZATION_CAPABILITIES property
```

This is the face recognition module trying to use Intel GPU acceleration. On AMD systems (like my A9-9400), it falls back to CPU - totally fine, face recognition isn't latency-sensitive.

## Lessons Learned

### Always Backup Before Changes

I wrote a backup script but didn't use it. Lost the living room camera config and had to restore from a backup file. Now I make multiple backups:

```bash
# Before any config change
kubectl exec -n frigate $POD -- cat /config/config.yml > backup-$(date +%Y%m%d-%H%M%S).yml
cp backup-*.yml /tmp/  # Emergency backup location
```

### Check Camera Codec Before Choosing Stream Type

```bash
# Via go2rtc API
curl -s "http://frigate:1984/api/streams?src=camera_name" | jq '.producers[0].medias'

# H264 = HTTP-FLV works
# H265 = Use RTSP (until FFmpeg 8.0)
```

### GitOps as Source of Truth

Frigate config is managed via K8s ConfigMap with Flux GitOps. The init container always copies from ConfigMap, making git the source of truth:

```yaml
initContainers:
  - name: init-config
    command: ['sh', '-c', 'cp /config-map/config.yml /config/config.yml']
```

## Final Config

Working configuration with all cameras:

```yaml
go2rtc:
  streams:
    mjpeg_cam: "ffmpeg:http://USER:PASS@192.168.1.220/videostream.cgi#video=h264#hardware"
    reolink_doorbell_main: "ffmpeg:http://doorbell/flv?port=1935&app=bcs&stream=channel0_main.bcs&user=USER&password=PASS#video=copy#audio=copy#audio=opus"
    reolink_doorbell_sub: "ffmpeg:http://doorbell/flv?port=1935&app=bcs&stream=channel0_ext.bcs&user=USER&password=PASS#video=copy"
    living_room_main: "rtsp://USER:PASS@192.168.1.140:554/h264Preview_01_main"
    living_room_sub: "rtsp://USER:PASS@192.168.1.140:554/h264Preview_01_sub"

cameras:
  reolink_doorbell:
    objects:
      track: [person, car, package]  # package requires Frigate+ model
  living_room:
    objects:
      track: [person]
    onvif:
      host: 192.168.1.140
      port: 8000

model:
  path: plus://c7b38453956cda87076baba4aca213e6

detectors:
  coral:
    type: edgetpu
    device: usb
```

## References

- [Frigate Camera Specific Configurations](https://docs.frigate.video/configuration/camera_specific/)
- [go2rtc HTTP-FLV H.265 Issue](https://github.com/AlexxIT/go2rtc/issues/1938)
- [Frigate+ Documentation](https://docs.frigate.video/plus/)
