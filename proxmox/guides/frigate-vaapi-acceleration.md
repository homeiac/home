# Frigate + go2rtc VA-API Hardware Acceleration on AMD Radeon R5

Offload JPEG→H.264 decode & encode to your A9-9400’s Radeon R5 GPU via VA-API
and slash CPU load.

---

## Configuration

Add **only** these lines to your Frigate config.yaml using the Configuration
editor:

```yaml
environment_vars:
  LIBVA_DRIVER_NAME: radeonsi

ffmpeg:
  hwaccel_args: preset-vaapi

go2rtc:
  streams:
    # Pull MJPEG HTTP, then hardware-encode to H.264 @ 640×480
    mjpeg_cam: "ffmpeg:http://<username>:<password>@<old ipcam IP address>/videostream.cgi#video=h264#hardware"
```

The complete working config file for ATOPNUC Model MA90 with AMD A9-9400 with
Radeon 5 GPU:

```yaml
mqtt:
  enabled: false
environment_vars:
  LIBVA_DRIVER_NAME: radeonsi
ffmpeg:
  hwaccel_args: preset-vaapi
go2rtc:
  streams:
    # tell go2rtc to pull JPEG HTTP, then re-encode to H264 via our preset
    mjpeg_cam: "ffmpeg:http://<username>:<password>@<old ipcam IP address>/videostream.cgi#video=h264#hardware"
cameras:
  old_ip_camera:
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/mjpeg_cam
          roles:
            - detect
            - record
            - rtmp
    detect:
      width: 640
      height: 480
      fps: 5  # Adjust for lower CPU usage
    objects:
      track:
        - person
        - car
    motion:
      threshold: 10  # Adjust sensitivity
      mask:
        0.001,0.001,1,0.001,0.998,0.306,0.857,0.317,0.813,0.313,0.796,0.286,0.769,0.319,0.755,0.318,0.737,0.268,0.707,0.325,0.693,0.326,0.671,0.263,0.634,0.293,0.467,0.289,0.002,0.254
    zones: {}
    record:
      enabled: true
      retain:
        days: 3      # Number of days to keep recordings
        mode: motion # Options: all, motion, continuous
      events:
        retain:
          default: 10 # Retain event recordings for 10 days
detectors:
  ov:
    type: openvino
    device: CPU
    model:
      path: /openvino-model/FP16/ssdlite_mobilenet_v2.xml
model:
  width: 300
  height: 300
  input_tensor: nhwc
  input_pixel_format: bgr
  labelmap_path: /openvino-model/coco_91cl_bkgr.txt
version: 0.14
```

---

## Caveats

* **Weird aspect ratio**: It turned into 960 x 720 pixels image instead of
  640x480 even if I specify:

```yaml
    mjpeg_cam: "ffmpeg:http://<username>:<password>@<old ipcam IP address>/videostream.cgi#video=h264#hardware#width=640#height=480"
```

as suggested in the following
[link](https://github.com/AlexxIT/go2rtc?tab=readme-ov-file#source-ffmpeg)

> You can use width and/or height params, important with transcoding (ex.
> #video=h264#width=1280)

### Reference Links

See
  [https://github.com/blakeblackshear/frigate/discussions/16782](https://github.com/blakeblackshear/frigate/discussions/16782)

* **go2rtc presets**: For full details on the `#hardware` suffix and built-in
  codecs, see
  [https://github.com/AlexxIT/go2rtc?tab=readme-ov-file#source-ffmpeg](https://github.com/AlexxIT/go2rtc?tab=readme-ov-file#source-ffmpeg)
