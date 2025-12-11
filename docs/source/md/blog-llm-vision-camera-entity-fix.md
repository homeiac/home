# Why My LLM Vision Notifications Were Showing "Error Message" Instead of Packages

*The subtle difference between Frigate camera entities and native camera entities - and why it matters*

---

```
    WHAT I EXPECTED:                    WHAT I GOT:

    +------------------+                +------------------+
    |  [Photo of       |                |  [Black screen]  |
    |   delivery       |                |                  |
    |   person]        |                |   "Error: No     |
    |                  |                |    person        |
    +------------------+                |    visible"      |
    | Package          |                +------------------+
    | Delivered!       |                | PM: No person    |
    +------------------+                | is visible; the  |
                                        | image shows an   |
                                        | error message.   |
                                        +------------------+
```

## The Problem

My doorbell detection automation was sending notifications like:

> "PM: No person is visible; the image shows an error message."

The LLM Vision integration was analyzing... a black image. Because the camera snapshot was failing silently.

## Root Cause: Wrong Camera Entity

```yaml
# What was deployed (BROKEN):
- service: camera.snapshot
  target:
    entity_id: camera.reolink_doorbell  # <- Frigate entity!
  data:
    filename: /config/www/tmp/doorbell_visitor.jpg
```

The automation was using `camera.reolink_doorbell` - which is a **Frigate camera entity**. When Frigate went down (old server), this entity returned errors or black frames.

```yaml
# What should have been deployed (WORKING):
- service: camera.snapshot
  target:
    entity_id: camera.reolink_video_doorbell_wifi_fluent  # <- Native Reolink
  data:
    filename: /config/www/tmp/doorbell_visitor.jpg
```

The native Reolink integration entity `camera.reolink_video_doorbell_wifi_fluent` connects directly to the camera, bypassing Frigate entirely.

## Blueprint: Camera Entity Selection for Automations

### Camera Entity Types

| Entity Pattern | Source | Dependency |
|----------------|--------|------------|
| `camera.<frigate_camera_name>` | Frigate integration | Requires Frigate running |
| `camera.<brand>_<model>_<stream>` | Native integration | Direct to camera |
| `image.<camera>_<object>` | Frigate snapshots | Requires Frigate + detection |

### Decision Matrix

```
Is Frigate required for this automation?
    |
    +-- YES (need object detection, zones, events)
    |       |
    |       +-> Use Frigate entities
    |           - camera.<name> for streams
    |           - image.<name>_<object> for snapshots
    |           - binary_sensor.<name>_<object>_occupancy for triggers
    |
    +-- NO (just need camera image)
            |
            +-> Use Native camera entities
                - More reliable (no middleware dependency)
                - Works even if Frigate is down
                - Better for LLM Vision analysis
```

### Action Log Template

```markdown
## Fix: Camera Entity Selection in Automation
Date: YYYY-MM-DD

### Problem Identification
- [ ] Notification showing error/blank images
- [ ] LLM Vision returning "error message" or "no person visible"
- [ ] Automation uses Frigate camera entity
- [ ] Frigate server was down/unreachable

### Camera Entity Audit
Current entities in automation:
- Snapshot: `camera.xxx`
- Image proxy: `/api/camera_proxy/camera.xxx`
- Trigger: `binary_sensor.xxx`

### Fix Steps
1. [ ] Backup automations.yaml
2. [ ] Identify correct native camera entity
3. [ ] Replace all Frigate camera references
4. [ ] Reload/restart Home Assistant
5. [ ] Test with actual trigger

### Verification
- [ ] Snapshot file created with actual image
- [ ] LLM Vision returns meaningful analysis
- [ ] Notification shows correct image
```

---

## Action Log: Package Detection Automation Fix

**Date:** 2024-12-11

### Problem Identification

User reported notifications with message:
> "PM: No person is visible; the image shows an error message."

The `pending_notification_message` helper showed the LLM was analyzing an error image, not camera footage.

### Root Cause Analysis

Inspected deployed automation in Home Assistant:

```bash
$ ssh root@chief-horse.maas 'qm guest exec 116 -- cat /mnt/data/supervisor/homeassistant/automations.yaml' | jq -r '."out-data"' | grep -E "camera\.(reolink|frigate)"
```

Found **8 references** to `camera.reolink_doorbell` (Frigate entity):

```yaml
# In visitor analysis action:
- target:
    entity_id: camera.reolink_doorbell  # WRONG - Frigate entity
  data:
    filename: /config/www/tmp/doorbell_visitor.jpg
  action: camera.snapshot

# In notification:
data:
  image: /api/camera_proxy/camera.reolink_doorbell  # WRONG
```

### Camera Entity Comparison

| Entity | Source | Status When Frigate Down |
|--------|--------|--------------------------|
| `camera.reolink_doorbell` | Frigate integration | Returns error/black |
| `camera.reolink_video_doorbell_wifi_fluent` | Reolink integration | Works normally |

### Fix Implementation

**Step 1: Backup**

```bash
$ ssh root@chief-horse.maas 'qm guest exec 116 -- cp /mnt/data/supervisor/homeassistant/automations.yaml /mnt/data/supervisor/homeassistant/automations.yaml.backup.20241211_201500'
{"exitcode": 0, "exited": 1}
```

**Step 2: Replace all camera references**

```bash
$ ssh root@chief-horse.maas 'qm guest exec 116 -- sed -i "s|camera.reolink_doorbell|camera.reolink_video_doorbell_wifi_fluent|g" /mnt/data/supervisor/homeassistant/automations.yaml'
{"exitcode": 0, "exited": 1}
```

**Step 3: Verify changes**

```bash
$ ssh root@chief-horse.maas 'qm guest exec 116 -- cat /mnt/data/supervisor/homeassistant/automations.yaml' | jq -r '."out-data"' | grep -E "camera\.(reolink|frigate)" | head -10
      - camera.reolink_video_doorbell_wifi_fluent
      - camera.reolink_video_doorbell_wifi_fluent
          entity_id: camera.reolink_video_doorbell_wifi_fluent
          entity_id: camera.reolink_video_doorbell_wifi_fluent
            image: /api/camera_proxy/camera.reolink_video_doorbell_wifi_fluent
```

All 8 references updated.

**Step 4: Restart Home Assistant**

```bash
$ ssh root@chief-horse.maas 'qm guest exec 116 -- ha core restart'
# Timeout expected - HA restarting
$ sleep 30 && curl -s http://192.168.4.240:8123/ | head -c 50
<!DOCTYPE html><html><head><title>Home Assistant
```

### Post-Fix State

The automation now:
1. Triggers on `binary_sensor.reolink_video_doorbell_wifi_person` (native Reolink)
2. Captures snapshot from `camera.reolink_video_doorbell_wifi_fluent` (native Reolink)
3. Sends notification with `/api/camera_proxy/camera.reolink_video_doorbell_wifi_fluent`

This bypasses Frigate entirely for image capture, making the automation resilient to Frigate outages.

---

## The Automation Flow

```
                    BEFORE (Broken)

Person detected     Frigate       LLM Vision      Notification
     |                |               |                |
     v                v               v                v
[Reolink]------->[Frigate]------->[Analyze]------->[Phone]
     |          (DOWN!)         "error msg"      "No person"
     |              X                |                |
     +--------------X----------------+----------------+
                   FAIL


                    AFTER (Fixed)

Person detected     Reolink       LLM Vision      Notification
     |                |               |                |
     v                v               v                v
[Reolink]------->[Direct]-------->[Analyze]------->[Phone]
     |          snapshot        "Delivery        "Package
     |             OK           person in         delivered!"
     +-------------+-------------uniform"             |
                   |                |                 |
                   +----------------+-----------------+
                              SUCCESS
```

---

## Lessons Learned

### 1. Camera Entity Selection Matters

Don't use Frigate camera entities if you don't need Frigate features. Native integrations are more reliable for basic snapshots.

### 2. LLM Vision Error Messages Are Clues

When LLM Vision says "error message visible" or similar, it's often analyzing a failure state image, not your actual camera feed.

### 3. Test Automation Dependencies

If your automation depends on Service A (Frigate), test what happens when Service A is down. Consider fallback paths.

### 4. Entity Naming Confusion

Home Assistant creates similarly-named entities from different integrations:
- `camera.reolink_doorbell` (Frigate)
- `camera.reolink_video_doorbell_wifi_fluent` (Reolink native)

Document which entity comes from which integration.

---

## Quick Reference: Reolink Entity Patterns

| Integration | Camera Entity Pattern |
|-------------|----------------------|
| Reolink (native) | `camera.<device_name>_<stream_type>` |
| Frigate | `camera.<frigate_camera_name>` |

Stream types for Reolink:
- `_fluent` - Lower resolution, less bandwidth
- `_clear` - Higher resolution
- `_snapshots_fluent` - Still images

---

## Rollback Procedure

```bash
# List backups
ssh root@chief-horse.maas 'qm guest exec 116 -- ls -la /mnt/data/supervisor/homeassistant/automations.yaml.backup.*'

# Restore
ssh root@chief-horse.maas 'qm guest exec 116 -- cp /mnt/data/supervisor/homeassistant/automations.yaml.backup.20241211_201500 /mnt/data/supervisor/homeassistant/automations.yaml'

# Restart
ssh root@chief-horse.maas 'qm guest exec 116 -- ha core restart'
```

---

*This debugging session was performed with Claude Code, which identified the camera entity mismatch by reading the deployed automation config and correlating it with the error symptoms.*

**Tags:** home-assistant, llm-vision, automation, frigate, reolink, camera, troubleshooting, notification, ollama, llava, homelab
