# Voice PE Phantom 401 Investigation

**Date**: 2025-12-20
**Symptom**: HA logs showing "Login attempt with invalid authentication from 192.168.4.122"
**Resolution**: Stale compiled firmware had http_request polling without auth token

---

## The Crime Scene

HA logs showed repeated warnings every 30 seconds:

```
WARNING: Login attempt or request with invalid authentication from 192.168.4.122
         Requested URL: '/api/'. (esphome/voice-pe)
```

User reported "something from voice pe or something else via probably the socat proxy is pinging ha proxy without auth"

---

## Step 1: Identify the Suspect IP

**Question**: Who is 192.168.4.122?

**Commands**:
```bash
$ KUBECONFIG=~/kubeconfig kubectl get nodes -o wide
# Result: No K3s node has this IP

$ nslookup 192.168.4.122
# Result: No reverse DNS
```

**Dead end**. Not a K3s node. User said "this is haos" - but 192.168.4.122 isn't HAOS (that's 192.168.4.240).

**Next step**: Query OpenMemory for context about Voice PE and this IP.

---

## Step 2: OpenMemory Query

**Command**:
```bash
$ mcp__openmemory__openmemory_query
    query: "voice PE socat proxy HA authentication 192.168.4.122"
```

**Key result** (score=1.395):
```
[procedural] id=5a80fe94-95ca-4cff-8a96-a4f174118881

"Connect Voice PE to Google WiFi (normal WiFi setup)
 2. When prompted for Home Assistant URL, enter:
    http://192.168.1.122:8123  <-- THIS URL
 3. Verify ISP router is routing between subnets"
```

**Insight**: Voice PE uses `192.168.1.122:8123` - not HA's actual IP. There must be a proxy. The `192.168.4.122` in the error might be related.

---

## Step 3: Find the Proxy

**Command**:
```bash
$ Grep "socat|ha-proxy|192\.168\.4\.122" **/*.{yaml,yml,sh,md}
```

**Files found**:
```
proxmox/systemd/ha-proxy.service
scripts/voice-pe/deploy-ha-proxy.sh
docs/source/md/voice-pe-network-proxy.md
```

**Read**: `docs/source/md/voice-pe-network-proxy.md`

**Discovery** - pve host has multiple interfaces:
```
| Interface | IP             | Network      |
|-----------|----------------|--------------|
| wlan0     | 192.168.86.27  | Google WiFi  |
| vmbr0     | 192.168.1.122  | ISP network  |
| vmbr25gbe | 192.168.4.122  | Homelab      | <-- THE SUSPECT IP!
```

**Read**: `proxmox/systemd/ha-proxy.service`
```ini
ExecStart=/usr/bin/socat \
  TCP-LISTEN:8123,bind=192.168.1.122,reuseaddr,fork \
  TCP:192.168.4.240:8123
```

**The connection**:
```
Voice PE (192.168.86.x)
    │
    ▼
Google WiFi → ISP Router → pve (192.168.1.122:8123)
                                    │
                              socat proxy
                                    │
                                    ▼
                           HA (192.168.4.240:8123)

When socat forwards the request, HA sees the SOURCE as pve's
homelab interface: 192.168.4.122
```

---

## Step 4: Confirm Voice PE is the Culprit

**Command**:
```bash
$ ~/code/home/scripts/haos/get-logs.sh core | grep -iE "esphome.*voice"
```

**Output**:
```
WARNING: invalid authentication from 192.168.4.122
         Requested URL: '/api/'
         (esphome/voice-pe)

ERROR: Home Assistant Voice 09f5a3:
  [http_request.idf:208]: HTTP Request failed;
  URL: http://192.168.1.122:8123/api/  <-- DEVICE IS POLLING THIS!
  Code: 401
```

**Confirmed**: The Voice PE device itself is making HTTP requests to `/api/` every 30 seconds without authentication.

---

## Step 5: Check Our YAML Config

**File**: `scripts/voice-pe/voice-pe-config.yaml`

```yaml
# HTTP connectivity check removed - was causing auth warnings in HA logs
# Network issue was flaky Google WiFi routing - fixed by router restart

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
```

**No http_request in our YAML**. So where is it coming from?

---

## Step 6: Check the Compiled Firmware

**Command**:
```bash
$ grep -n "192.168.1.122" \
    scripts/voice-pe/.esphome/build/home-assistant-voice-09f5a3/src/main.cpp
```

**Output**:
```
4037:  http_request_httprequestsendaction_id->set_url("http://192.168.1.122:8123/api/");
4042:  #line 113 "/config/voice-pe-config.yaml"
4043:  ESP_LOGI("connectivity", "HA reachable at 192.168.1.122:8123 (status %d)", response->status_code);
```

**Root cause found**: The `.esphome/build/` directory had STALE compiled code from an older version of the YAML that included the http_request polling. Even though we removed it from the YAML, the compiled binary was never rebuilt.

---

## Step 7: The Fix

**Commands**:
```bash
# Recompile from current YAML (no http_request)
$ ~/code/home/scripts/voice-pe/docker-compile.sh

# Verify new firmware has no polling URL
$ strings scripts/voice-pe/.esphome/build/.../firmware.factory.bin | grep "192.168.1.122"
# (no output = URL removed)

# Flash via USB
$ ~/code/home/scripts/voice-pe/usb-flash-esptool.sh
```

---

## Step 8: Verification

**Command**:
```bash
$ ~/code/home/scripts/haos/get-logs.sh core | grep "invalid authentication" | tail -5
```

**Before fix**: Errors every 30 seconds
```
18:11:45 WARNING ... invalid authentication from 192.168.4.122
18:12:15 WARNING ... invalid authentication from 192.168.4.122
18:12:45 WARNING ... invalid authentication from 192.168.4.122
18:13:15 WARNING ... invalid authentication from 192.168.4.122
18:13:45 WARNING ... invalid authentication from 192.168.4.122
```

**After fix**: No new errors after 18:13:45 (flash completed ~18:13)

---

## Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   YAML config ──► Compile ──► firmware.bin ──► Flash ──► Device    │
│        │              │            │                                │
│        ▼              ▼            ▼                                │
│   [No http_req]  [STALE!]    [OLD CODE]     [Polls /api/ @ 30s]    │
│                      │                                              │
│                      └── .esphome/build/ had OLD compiled code     │
│                          that was never cleaned                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Files

| Purpose | Path |
|---------|------|
| Socat proxy service | `proxmox/systemd/ha-proxy.service` |
| Network architecture doc | `docs/source/md/voice-pe-network-proxy.md` |
| ESPHome YAML (clean) | `scripts/voice-pe/voice-pe-config.yaml` |
| Compiled code (was stale) | `scripts/voice-pe/.esphome/build/.../src/main.cpp` |
| Compile script | `scripts/voice-pe/docker-compile.sh` |
| Flash script | `scripts/voice-pe/usb-flash-esptool.sh` |
| HA log checker | `scripts/haos/get-logs.sh` |

---

## Lessons Learned

1. **ESPHome build cache can be stale** - removing code from YAML doesn't remove it from the compiled binary until you recompile
2. **OpenMemory pointed to the proxy** - the query result mentioned `http://192.168.1.122:8123` which led to investigating the socat proxy
3. **HA logs show the ESPHome device name** - `(esphome/voice-pe)` in the log identified the source
4. **Check compiled output, not just YAML** - the `main.cpp` showed what was actually running on the device

---

## Tags

voice-pe, esphome, authentication, 401, socat, proxy, troubleshooting, stale-build, http_request, investigation

---

*Document created: 2025-12-20*
