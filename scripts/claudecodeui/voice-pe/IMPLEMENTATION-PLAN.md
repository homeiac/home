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

**Status**: DESIGNED - Ready for implementation

**Key Discovery**: `assist_satellite.start_conversation` enables voice approval WITHOUT wake word!
- Plays TTS message
- Automatically starts listening after TTS
- User just says "yes" or "no"

**Design Doc**: `VOICE-APPROVAL-DESIGN.md`

**Spikes** (answered):
- [x] Can HA intent be guarded by input_boolean state? → YES, use condition in intent script
- [x] What phrases does Whisper reliably recognize? → "yes", "yeah", "yep", "no", "nope", etc.
- [x] Does intent fire when Voice PE is in "waiting for command" vs idle? → YES, after start_conversation

**Failed Approach**: ESPHome `voice_assistant.start:` action caused boot loop. Don't use.

**Needed**:
- [x] HA intent for "yes" / "approve" / "do it" → `ApproveClaudeAction`
- [x] HA intent for "no" / "reject" / "cancel" → `RejectClaudeAction`
- [x] Guard: only active when awaiting approval → `input_boolean.claude_awaiting_approval`
- [ ] Update approval-request automation to use `assist_satellite.start_conversation`
- [ ] Deploy custom_sentences and intent_scripts to HA

**Acceptance**:
- [ ] After approval TTS, user says "yes" (NO wake word) → approves
- [ ] After approval TTS, user says "no" (NO wake word) → rejects
- [ ] Dial still works as fallback
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
- [x] Can Voice PE LED ring address individual LEDs? → **YES** ✅ VERIFIED
- [x] What ESPHome service controls individual LED segments? → **Named effects** ✅ VERIFIED

**Solution** (verified working 2025-12-18):
```yaml
light:
  - id: !extend led_ring
    effects:
      - addressable_lambda:
          name: "Progress 3"
          lambda: |-
            for (int i = 0; i < 3; i++) it[i] = Color(0, 255, 0);
            for (int i = 3; i < 12; i++) it[i] = Color::BLACK;
```

**Demo verified**:
- Progress 1/2/3: ✅ Incremental green LEDs
- Segment Test: ✅ 4 colored segments (R/G/B/W)
- Test script: `scripts/voice-pe/test-per-led.sh "Progress 3"`

**Remaining**: Add Progress 4-12 effects for full multi-approval support.

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
- [x] Can LED ring show gradient (brightness per LED)? → **YES**. Same `set_led` service can set per-LED brightness.

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
- [x] LED segments for options? → **YES**. Same `set_led` service enables colored segments.

**Needed**:
- LED segments for options (3-5)
- Dial to select, button to confirm
- Voice option names
- Tap patterns (1-5 taps)

**Acceptance**:
- [ ] "Which service?" shows 3 colored LED segments
- [ ] Dial rotates selection with voice announcement
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
