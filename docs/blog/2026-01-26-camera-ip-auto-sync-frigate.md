# Auto-Syncing Camera IPs to Frigate: A GitOps Approach

**Date**: January 26, 2026
**Author**: Claude + Human collaboration
**Tags**: frigate, home-assistant, gitops, kubernetes, automation, reolink, dhcp, camera

---

## The Problem: Sunday Morning Feed Outages

Every Sunday morning, my Reolink cameras reboot for scheduled maintenance. When they come back up, DHCP sometimes assigns them new IPs. Frigate keeps trying to connect to the old IPs, and I wake up to dead camera feeds.

The "fix" was always the same:
1. Open the Reolink app to find the new IPs
2. SSH into the cluster
3. Edit the Frigate ConfigMap
4. Restart Frigate
5. Wait for streams to reconnect

Manual, annoying, and exactly the kind of thing that should be automated.

## Why Not Just Use DHCP Reservations?

Great question. My AT&T router has DHCP reservations, but they don't persist across router reboots. Every firmware update wipes them. I've re-added them at least 5 times.

The cameras do support static IPs, but that creates a different problem: if I ever change my network configuration, I have to physically access each camera to reconfigure it.

Dynamic IPs with automatic discovery is actually more resilient.

## The Solution: Event-Driven IP Sync

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Camera IP Auto-Sync Flow                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌───────────────┐    ┌──────────────────────┐  │
│  │   Reolink    │    │  Home         │    │  K8s Cluster         │  │
│  │   Cameras    │    │  Assistant    │    │                      │  │
│  └──────┬───────┘    └───────┬───────┘    │  ┌────────────────┐  │  │
│         │                    │            │  │ frigate-webhook│  │  │
│         │  DHCP assigns      │            │  └────────┬───────┘  │  │
│         │  new IP            │            │           │          │  │
│         ▼                    │            │           ▼          │  │
│  ┌──────────────┐           │            │  ┌────────────────┐  │  │
│  │ 192.168.1.x  │◄──nmap────┤            │  │ ConfigMap      │  │  │
│  │ (by MAC)     │   scan    │            │  │ frigate-config │  │  │
│  └──────────────┘           │            │  └────────┬───────┘  │  │
│                              │            │           │          │  │
│                              ▼            │           ▼          │  │
│                   ┌───────────────┐       │  ┌────────────────┐  │  │
│                   │sensor.camera_ │       │  │ Reloader       │  │  │
│                   │ips (state     │       │  │ (watches CM)   │  │  │
│                   │ change)       │       │  └────────┬───────┘  │  │
│                   └───────┬───────┘       │           │          │  │
│                           │               │           ▼          │  │
│                           │               │  ┌────────────────┐  │  │
│                   ┌───────▼───────┐       │  │ Frigate        │  │  │
│                   │ Automation    │──POST─┼─►│ (restarted)    │  │  │
│                   │ (REST cmd)    │       │  └────────────────┘  │  │
│                   └───────────────┘       │                      │  │
│                                           └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Component 1: Camera Discovery via MAC Address

Reolink cameras don't support mDNS/Bonjour. They use a proprietary UDP discovery protocol and ONVIF WS-Discovery. Both are flaky for automated discovery.

What does work reliably? Good old nmap. The cameras have fixed MAC addresses, and nmap can find them:

```python
# camera-ip-sync.py (runs in HA container)
CAMERAS = {
    "hall": "0C:79:55:4B:D4:2A",
    "living_room": "14:EA:63:A9:04:08",
}

def scan_network(scan_range):
    result = subprocess.run(
        ["nmap", "-sn", scan_range],
        capture_output=True, text=True, timeout=120
    )
    # Parse MAC -> IP mapping from output
    ...
```

This runs every 5 minutes via HA's `command_line` sensor. The output includes an `ip_state` string that changes when IPs change:

```json
{
  "cameras": {"hall": "192.168.1.137", "living_room": "192.168.1.138"},
  "ip_state": "hall:192.168.1.137,living_room:192.168.1.138",
  "all_found": true
}
```

### Component 2: State-Based Automation Trigger

The key insight: use `ip_state` as the sensor's state value, not just an attribute. This means HA's state change trigger fires exactly when IPs change:

```yaml
# configuration.yaml
command_line:
  - sensor:
      name: Camera IPs
      unique_id: camera_ips_sensor
      command: "cat /config/camera_ips.json"
      value_template: "{{ value_json.ip_state }}"  # State = IP string
      json_attributes:
        - cameras
        - all_found
      scan_interval: 300
```

The automation only fires on actual IP changes, not every scan:

```yaml
# automations.yaml
- id: camera_ip_sync_to_frigate
  alias: Camera IP Sync to Frigate
  trigger:
    - platform: state
      entity_id: sensor.camera_ips
  condition:
    # Ignore startup/unavailable states
    - condition: template
      value_template: "{{ trigger.from_state.state not in ['unavailable', 'unknown', ''] }}"
    - condition: template
      value_template: "{{ trigger.to_state.state not in ['unavailable', 'unknown', ''] }}"
    # Only if state actually changed
    - condition: template
      value_template: "{{ trigger.from_state.state != trigger.to_state.state }}"
    # Only if all cameras found
    - condition: template
      value_template: "{{ state_attr('sensor.camera_ips', 'all_found') == true }}"
  action:
    - service: rest_command.update_frigate_camera_ips
```

### Component 3: K8s Webhook for ConfigMap Updates

HA calls a webhook running in the K8s cluster. The webhook patches the Frigate ConfigMap:

```python
# webhook.py (Flask app in K8s)
@app.route("/update", methods=["POST"])
def update_ips():
    camera_ips = request.get_json()
    # {"living_room": "192.168.1.138", "hall": "192.168.1.137"}

    # Patch ConfigMap with regex replacements
    # - go2rtc stream URLs: @OLD_IP:554 -> @NEW_IP:554
    # - ONVIF hosts: host: OLD_IP -> host: NEW_IP

    # Trigger restart via deployment annotation
    patch = {"spec": {"template": {"metadata": {"annotations": {
        "camera-ips-updated": datetime.utcnow().isoformat()
    }}}}}
    apps_v1.patch_namespaced_deployment("frigate", "frigate", patch)
```

The webhook has proper RBAC to patch ConfigMaps and Deployments in the frigate namespace.

### Component 4: Reloader for Automatic Restarts

Instead of the webhook triggering restarts, I use [Stakater Reloader](https://github.com/stakater/Reloader). It watches ConfigMaps and automatically restarts pods when they change:

```yaml
# deployment.yaml
metadata:
  annotations:
    reloader.stakater.com/auto: "true"
```

This is cleaner than manual restart logic and works for any ConfigMap change, not just IP updates.

## The GitOps Angle

Everything is managed through GitOps:

1. **Webhook container** - Built via GitHub Actions, pushed to ghcr.io
2. **K8s manifests** - Deployment, Service, IngressRoute in git
3. **Flux reconciliation** - Changes auto-deploy on push

```yaml
# .github/workflows/build-frigate-webhook.yaml
on:
  push:
    paths:
      - 'gitops/clusters/homelab/apps/frigate-ip-webhook/**'
```

## What I Learned

### 1. State vs Attributes Matter

Initially I had `all_found` as the sensor state. This only triggered when cameras appeared/disappeared, not when IPs changed. Moving the IP string to state fixed it.

### 2. nmap > Proprietary Discovery

I spent hours trying to get Reolink's UDP discovery working from K8s. Broadcast packets don't cross subnets. nmap from the HA container (same L2 as cameras) just works.

### 3. ConfigMap Changes Don't Restart Pods

This surprised me. Kubernetes applies ConfigMap updates, but pods keep running with old values. You need either:
- Reloader (recommended)
- Checksum annotation in pod template
- Manual restart logic

### 4. Webhook > Direct K8s from HA

I considered giving HA direct K8s access via a ServiceAccount token. But:
- More attack surface
- HA doesn't need K8s knowledge
- Webhook is simpler to test and debug

## Future Improvements

1. **Notification on IP change** - Add a mobile push when automation fires
2. **Frigate API validation** - Check streams are actually working after restart
3. **Retry logic** - If webhook fails, retry with backoff

## Files Reference

| File | Purpose |
|------|---------|
| `scripts/haos/camera-ip-sync.py` | nmap scanner, writes JSON |
| `scripts/haos/ha-config-camera-ip-sync.yaml` | HA config template |
| `scripts/haos/automations/camera-ip-sync-to-frigate.yaml` | Automation |
| `gitops/.../frigate-ip-webhook/webhook.py` | K8s webhook |
| `gitops/.../frigate-ip-webhook/deployment.yaml` | RBAC + Deployment |
| `.github/workflows/build-frigate-webhook.yaml` | Container build |

---

*The real test comes next Sunday. I'll update this post with results.*
