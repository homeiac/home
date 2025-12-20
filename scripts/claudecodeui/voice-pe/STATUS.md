# Voice PE Implementation Status

**Last Updated:** 2025-12-20
**Device:** Home Assistant Voice PE (home-assistant-voice-09f5a3)

---

## Scenarios

### 1. Claude Approval via Dial
**Status:** ✅ COMPLETE

User rotates dial to approve/reject Claude Code tool requests.

| Step | Status | Notes |
|------|--------|-------|
| Firmware fires `esphome.voice_pe_dial` event | ✅ | CW/CCW with device_id |
| HA automation listens to event | ✅ | Via HA UI |
| LED shows amber while waiting | ✅ | "Waiting" effect |
| LED shows green on approve | ✅ | "Approved" effect |
| LED shows red on reject | ✅ | "Rejected" effect |
| MQTT response to `claude/approval-response` | ✅ | `{"approved": true/false, "source": "dial"}` |

---

### 2. Claude Approval via Voice
**Status:** ✅ COMPLETE (with quirk)

User says "yes"/"no" after TTS prompt - no wake word needed.

| Step | Status | Notes |
|------|--------|-------|
| TTS asks "Do X? Say yes or no" | ✅ | Uses `assist_satellite.start_conversation` |
| Voice PE listens after TTS | ✅ | No wake word required |
| "yes"/"approve" triggers approval | ✅ | Custom sentence in HA |
| "no"/"reject" triggers rejection | ✅ | Custom sentence in HA |
| MQTT response to `claude/approval-response` | ✅ | `{"approved": true/false, "source": "voice"}` |

**Known Quirk:** Voice PE says "nothing pending" before actual response comes through. Cosmetic issue.

---

### 3. Ask Claude via Voice
**Status:** ❌ NOT STARTED

User says "Hey Jarvis, ask Claude [question]" to send query to Claude Code.

| Step | Status | Notes |
|------|--------|-------|
| Custom sentence for "ask Claude..." | ❌ | File exists: `custom_sentences/en/ask_claude.yaml` |
| Intent script to publish to MQTT | ❌ | File exists: `intent_scripts/ask_claude.yaml` |
| Deploy to HA | ❌ | Script: `deploy-ask-claude-intent.sh` |
| ClaudeCodeUI subscribes to query topic | ❌ | Needs ClaudeCodeUI changes |
| Response spoken via TTS | ❌ | |

---

### 4. Package Detection Notification
**Status:** 🚧 PARTIAL

Frigate detects package at door, Voice PE announces and shows LED.

| Step | Status | Notes |
|------|--------|-------|
| Frigate detects person at door | ✅ | Working in K8s |
| HA automation triggers on detection | 🚧 | Automation exists, needs testing |
| LLM Vision analyzes snapshot | ❌ | Ollama integration issues |
| Voice PE LED pulses | ❌ | |
| User asks "What's my notification?" | ❌ | Custom sentence needed |
| TTS describes who's at door | ❌ | |

---

### 5. Basic Voice Control
**Status:** ✅ COMPLETE

Standard Home Assistant voice commands via Voice PE.

| Step | Status | Notes |
|------|--------|-------|
| Wake word detection ("Hey Jarvis") | ✅ | Using 25.11.0 firmware |
| Voice commands to HA | ✅ | Lights, etc. |
| TTS responses | ✅ | Via Piper |

---

## Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| Voice PE firmware | ✅ | 25.11.0 with dial events |
| TTS (Piper) | ✅ | Working after router restart |
| Network path (Voice PE → HA) | ✅ | Via socat proxy 192.168.1.122 |
| MQTT broker | ✅ | On HA |
| Custom LED effects | ✅ | Waiting/Approved/Rejected/Progress |

---

## Files Reference

| Purpose | Location |
|---------|----------|
| Firmware config | `scripts/voice-pe/voice-pe-config.yaml` |
| Approval automation | HA UI (not file-managed) |
| Custom sentences | `scripts/claudecodeui/voice-pe/custom_sentences/` |
| Intent scripts | `scripts/claudecodeui/voice-pe/intent_scripts/` |
| Test scripts | `scripts/claudecodeui/voice-pe/*.sh` |
| TTS troubleshooting | `docs/source/md/runbook-voice-pe-tts-troubleshooting.md` |

---

## Next Priority

1. **Ask Claude via Voice** - Deploy intent, test E2E
2. **Package Detection** - Fix LLM Vision integration
3. **"Nothing pending" quirk** - Investigate timing issue
