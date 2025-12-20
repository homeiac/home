# Runbook: Voice PE TTS Troubleshooting

## Symptoms

- Voice PE LED control works (via HA)
- TTS announcements don't play audio
- HA logs show: `ESP_ERR_HTTP_CONNECT` or `Failed to open URL`

## Quick Checks

### 1. Verify Voice PE is connected
```bash
scripts/haos/get-entity-state.sh assist_satellite.home_assistant_voice_09f5a3_assist_satellite | jq -r '.state'
# Expected: "idle" or "responding"
```

### 2. Check HA internal_url
```bash
scripts/haos/get-ha-config.sh | grep internal_url
# Should be: http://192.168.1.122:8123
```

### 3. Test TTS and check logs
```bash
scripts/voice-pe/test-tts-direct.sh "Test message"
sleep 2
scripts/haos/get-logs.sh core | grep -i "ESP_ERR\|Failed to open" | tail -5
```

## Network Topology

```
Voice PE (192.168.86.245)
    ↓ (must reach for TTS audio)
Google WiFi Router
    ↓
ISP Router / socat proxy (192.168.1.122:8123)
    ↓
Home Assistant (192.168.4.240:8123)
```

## Common Fixes

### Fix 1: Restart Google WiFi Router (Most Common)

**When**: Intermittent connectivity, some requests work, most fail

```bash
# Via Google Home app or physical power cycle
# Wait 2-3 minutes for network to stabilize
# Then test:
scripts/voice-pe/test-tts-direct.sh "Router restart test"
```

### Fix 2: Check Piper TTS Addon

**When**: No audio even when connectivity works

```bash
scripts/haos/get-addon-info.sh core_piper
scripts/haos/get-logs.sh core_piper | tail -20
# Look for "ConnectionResetError" or "Ready"

# Restart if needed:
# HA UI → Settings → Add-ons → Piper → Restart
```

### Fix 3: Verify internal_url is reachable

**When**: TTS URL uses wrong IP

```bash
# Check what URL TTS generates:
scripts/voice-pe/test-tts-google.sh "URL check" | grep -o 'http[^"]*tts_proxy[^"]*'

# The URL should use internal_url from HA config
# If Voice PE can't reach that IP, change internal_url in:
# HA UI → Settings → System → Network → Home Assistant URL
```

### Fix 4: Power cycle Voice PE

**When**: Voice PE firmware issue

```bash
# Physical power cycle, or via HA:
# HA UI → Settings → Devices → Voice PE → Restart
# Wait 30 seconds, then test
```

## Diagnostic Commands

### Check connectivity from Voice PE perspective
Add temporary firmware logging (see voice-pe-config.yaml history for example)

### Check all recent Voice PE errors
```bash
scripts/haos/get-logs.sh core | grep -i "voice.*09f5a3" | tail -30
```

### Verify TTS audio URL is accessible
```bash
# Get a TTS URL:
URL=$(scripts/voice-pe/test-tts-google.sh "test" | grep -o 'http[^"]*tts_proxy[^"]*' | head -1)
# Test it:
curl -s -o /dev/null -w "%{http_code}" "$URL"
# Should return 200
```

## Known Quirks

1. **"nothing pending" response**: After voice approval, Voice PE may say "nothing pending" before actual response. Cosmetic issue, approval still works.

2. **Auth warnings in HA logs**: If you see "Login attempt...invalid authentication from 192.168.4.122" - this is the socat proxy IP, not an attack. Usually from firmware connectivity checks.

## Escalation

If none of the above work:
1. Check OpenMemory: `opm query "voice-pe tts"`
2. Review RCA: `docs/source/md/rca-voice-pe-tts-failure-2025-12-20.md`
3. Check ESPHome logs directly: `scripts/voice-pe/check-logs.sh 30`
