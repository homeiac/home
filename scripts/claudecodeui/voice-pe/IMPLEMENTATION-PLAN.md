# Voice PE Approval - Implementation Plan

## Capability Tiers

| Tier | Scenarios | What It Enables |
|------|-----------|-----------------|
| **Core** | S1, S2 (dial/button) | Ask Claude, approve with dial |
| **Hands-Free** | + S2 voice yes/no | Approve without touching |
| **Robust** | + S5 errors | Know when things break |
| **Workflow** | + S3 multi-approval | Complex tasks (kubectl apply -R) |
| **Conversational** | + S4 context | Follow-up questions |
| **Power** | + S6 multi-choice | "Which pod? Which service?" |

---

## Core ✅

**Status**: Shipped. Usable.

**What works**:
- Voice command → Claude → TTS response (S1)
- Approval request → LED orange → dial preview → button confirm (S2)
- RequestId correlation
- Server-side 60s timeout

**Known quirks**:
- Edge cases in dial/button handling
- No HA-side timeout feedback (LED stays orange)

**Spikes** (to stabilize before next tier):
- [ ] What dial/button edge cases exist? (document specific failures)
- [ ] Why does clean-trace-test.sh show 2 approval-requests for 1 command?
- [ ] Does HA receive timeout signal from ClaudeCodeUI to clear LED?

---

## Hands-Free

**Gap**: Voice yes/no NOT implemented

**Spikes**:
- [ ] Can HA intent be guarded by input_boolean state?
- [ ] What phrases does Whisper reliably recognize? ("yes" vs "yeah" vs "yep")
- [ ] Does intent fire when Voice PE is in "waiting for command" vs idle?

**Needed**:
- HA intent for "yes" / "approve" / "do it"
- HA intent for "no" / "reject" / "cancel"
- Guard: only active when awaiting approval

**Acceptance**:
- [ ] "Hey Nabu, yes" approves pending request
- [ ] "Hey Nabu, no" rejects pending request
- [ ] Voice ignored when not awaiting approval

---

## Robust

**Gap**: Silent failures

**Spikes**:
- [ ] What error types does ClaudeCodeUI emit? (check MQTT schema)
- [ ] How is error signaled? (type:error in response? separate topic?)
- [ ] Can HA detect MQTT timeout or only ClaudeCodeUI?

**Needed**:
- TTS error messages per APPROVAL-UX-SCENARIOS.md S5
- LED red on error

**Acceptance**:
- [ ] MQTT timeout → spoken error
- [ ] No response → spoken error
- [ ] LED turns red, then off

---

## Workflow

**Gap**: Only handles single approval

**Spikes**:
- [ ] Does ClaudeCodeUI send approval index/total? (approvalIndex, approvalTotal)
- [x] Can Voice PE LED ring address individual LEDs? → **NO** (factory). Possible with custom ESPHome firmware.
- [x] What ESPHome service controls individual LED segments? → **None**. Only full-ring `light.turn_on` with rgb_color/brightness.

**Implication**: Progress LEDs require either:
1. Custom ESPHome firmware exposing `addressable_light`, OR
2. Workaround: full-ring color changes to indicate progress (e.g., green→orange→green)

**Needed**:
- Progress LED (green segments for completed)
- Blinking orange for current approval
- Sequence tracking (N of M)

**Acceptance**:
- [ ] 3-approval task shows progress on LED ring
- [ ] Reject mid-sequence cancels entire task
- [ ] All approved → brief green flash → off

---

## Conversational

**Gap**: No visible context state

**Spikes**:
- [ ] Does ClaudeCodeUI track conversationId/turnNumber?
- [ ] Is context timeout exposed via MQTT or internal only?
- [x] Can LED ring show gradient (brightness per LED)? → **NO**. Full-ring brightness only.

**Implication**: Color aging must use full-ring color changes (white→gray→dim), not per-LED gradients.

**Needed**:
- Context timer (ring drains)
- Color aging per conversation turn

**Acceptance**:
- [ ] After response, ring shows remaining context time
- [ ] Follow-up within timeout uses same conversation
- [ ] After timeout, fresh conversation

---

## Power

**Gap**: Only binary choices

**Spikes**:
- [ ] Does Voice PE firmware support tap count detection? (or HA-side debounce?)
- [ ] Can dial event include rotation amount or just CW/CCW direction?
- [ ] How does ClaudeCodeUI signal multiple choice? (type:choice? options array?)
- [x] LED segments for options? → **NO** (factory). Same limitation as Workflow tier.

**Implication**: Multi-choice options need alternative UX:
1. Voice announces options, user says option name, OR
2. Cycle through options with dial (full-ring color per option)

**Needed**:
- ~~LED segments for options (3-5)~~ → Alternative UX required
- Dial to select, button to confirm
- Voice option names
- Tap patterns (1-5 taps)

**Acceptance**:
- [ ] "Which service?" announces options via TTS
- [ ] Dial rotates selection with voice announcement (full-ring color change per option)
- [ ] Button confirms selection

---

## Scripts to Keep

```
test-mqtt.sh                  # MQTT connectivity test
run-local.sh                  # Local dev container
test-ask-claude-intent.sh     # Voice input test
00-backup-voice-pe-config.sh  # ESPHome backup
98-restore-voice-pe-backup.sh # ESPHome restore
06-check-automation-status.sh # Automation diagnostics
```

## Scripts to Archive

All numbered 01-15 scripts and diagnose-*/check-*/test-piper-* are POC spikes.
Move to `archive/` or delete after confirming Core tier is stable.

---

## V2 (Deferred)

| Scenario | Notes |
|----------|-------|
| S7: Resume conversation | Beyond timeout window |
| S8: Cancel execution | SIGINT to running command |
