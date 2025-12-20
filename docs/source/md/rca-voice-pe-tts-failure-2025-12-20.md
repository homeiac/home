# RCA: Voice PE TTS Audio Fetch Failure

**Date**: 2025-12-20
**Duration**: ~2 hours investigation
**Impact**: Voice PE could not play TTS audio, breaking voice approval workflow
**Status**: RESOLVED

## Summary

Voice PE on Google WiFi network (192.168.86.x) could not fetch TTS audio files from Home Assistant via the socat proxy (192.168.1.122). The root cause was stale routing state in the Google WiFi router.

## Timeline

| Time (PST) | Event |
|------------|-------|
| 14:00 | Voice approval testing began, TTS not playing |
| 14:06 | Confirmed `ESP_ERR_HTTP_CONNECT` errors in HA logs |
| 14:15 | Added connectivity check to Voice PE firmware |
| 14:39 | Firmware confirmed: "FAILED to reach http://192.168.1.122:8123/" |
| 14:41 | Observed intermittent success (1 of 10 attempts got 401) |
| 14:50 | User restarted Google WiFi router |
| 14:51 | All connectivity checks now succeeding (401 = connected) |
| 14:56 | TTS working, voice approval flow complete |

## Root Cause

**Google WiFi router had stale routing state** for cross-subnet traffic between:
- Voice PE on Google WiFi (192.168.86.245)
- Socat proxy on ISP network (192.168.1.122)

The routing worked intermittently (1 in 10 attempts) before the router restart, suggesting ARP cache or routing table corruption.

## Key Insight

The ESPHome API connection (HA → Voice PE) worked because HA initiates that connection. TTS failed because Voice PE initiates an outbound HTTP request to fetch audio - a different network direction that was affected by the routing issue.

## Contributing Factors

1. **Complex network topology**: 3 subnets (192.168.86.x, 192.168.1.x, 192.168.4.x) with socat proxy
2. **No monitoring**: No proactive connectivity checks between Voice PE and HA's TTS URL
3. **Misleading symptoms**: LED control worked (different connection direction), masking the network issue

## Resolution

1. Restarted Google WiFi router to clear routing state
2. Verified all connectivity checks passing
3. Tested full voice approval flow successfully

## Prevention

1. **Added to OpenMemory**: "Voice PE TTS not working - restart Google WiFi router"
2. **Firmware diagnostic added then removed**: Added HTTP connectivity check during debugging (caused auth warnings, removed after fix)
3. **Document the network topology**: Voice PE → socat (192.168.1.122) → HA (192.168.4.240)

## Lessons Learned

1. When ESP32 HTTP requests fail but API works, check network direction (push vs pull)
2. Intermittent connectivity (1/10 success) suggests router-level issues, not firewall
3. Google WiFi mesh can develop stale routing - restart as early troubleshooting step

## Related

- Runbook: `docs/source/md/runbook-voice-pe-tts-troubleshooting.md`
- OpenMemory: Search "voice-pe tts networking solved"
