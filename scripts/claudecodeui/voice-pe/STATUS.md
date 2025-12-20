# Voice PE Implementation Status

**Last Updated:** 2025-12-20
**Source:** APPROVAL-UX-SCENARIOS.md

---

## MVP Scenarios

### Scenario 1: Simple Question
**Status:** ❌ NOT STARTED

User asks Claude a question, gets voice response.

| Step | Status | Notes |
|------|--------|-------|
| Voice input triggers "Asking Claude" | ❌ | |
| LED: Blue (thinking) | ❌ | |
| Voice response | ❌ | |
| Long press cancels | ❌ | |

---

### Scenario 2: Binary Approval (Yes/No)
**Status:** 🚧 PARTIAL

| Step | Status | Notes |
|------|--------|-------|
| LED: Orange (waiting) | ✅ | "Waiting" effect |
| PATH A: Dial CW → preview (light green) | ❌ | Currently immediate, no preview |
| PATH A: Button confirms → bright green → blue | ❌ | |
| PATH B: Dial CCW → preview (light red) | ❌ | Currently immediate, no preview |
| PATH B: Button confirms → reject | ❌ | |
| PATH C: Voice "yes"/"no" → immediate | ✅ | Working |
| PATH D: Timeout warning at 10s | ❌ | |
| PATH D: Auto-reject at 15s | ❌ | |
| PATH E: Change mind during preview | ❌ | |

---

### Scenario 3: Multiple Approvals in Sequence
**Status:** ❌ NOT STARTED

Progress LEDs show completed vs pending approvals.

| Step | Status | Notes |
|------|--------|-------|
| Progress LED per approval | ❌ | |
| Current approval blinks orange | ❌ | |
| Done approvals solid green | ❌ | |
| Reject any → cancel entire task | ❌ | |

---

### Scenario 4: Follow-Up Questions
**Status:** ❌ NOT STARTED

Context timer and conversation aging.

| Step | Status | Notes |
|------|--------|-------|
| Context ring drains over 60s | ❌ | |
| Color ages with conversation turns | ❌ | |
| Within timeout: Claude remembers | ❌ | |
| After timeout: fresh conversation | ❌ | |

---

### Scenario 5: System/Automation Failures
**Status:** ❌ NOT STARTED

Technical error messages for debugging.

| Step | Status | Notes |
|------|--------|-------|
| MQTT timeout → voice message | ❌ | |
| No response → voice message | ❌ | |
| MQTT disconnect → voice message | ❌ | |
| Automation error → voice message | ❌ | |
| Parse error → voice message | ❌ | |
| HTTP error → voice message | ❌ | |

---

### Scenario 6: Multiple Choice (up to 5)
**Status:** ❌ NOT STARTED

Dial selects from options, voice announces.

| Step | Status | Notes |
|------|--------|-------|
| LED: colored segments for options | ❌ | |
| Dial CW/CCW navigates + voice announces | ❌ | |
| Button confirms selection | ❌ | |
| Voice selects directly | ❌ | |
| Button tap pattern (1-5) selects | ❌ | |

---

## V2 Scenarios

### Scenario 7: Resume Previous Conversation
**Status:** ❌ V2 - NOT PLANNED

---

### Scenario 8: Cancel During Execution
**Status:** ❌ V2 - NOT PLANNED

---

## Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| Voice PE firmware | ✅ | 25.11.0 with dial events |
| TTS (Piper) | ✅ | Working |
| Network path | ✅ | Via socat 192.168.1.122 |
| MQTT broker | ✅ | On HA |
| LED effects (basic) | ✅ | Waiting/Approved/Rejected |

---

## Summary

| Scenario | Priority | Status |
|----------|----------|--------|
| 1. Simple Question | MVP | ❌ |
| 2. Binary Approval | MVP | 🚧 (voice only) |
| 3. Multiple Approvals | MVP | ❌ |
| 4. Follow-Up Questions | MVP | ❌ |
| 5. System Failures | MVP | ❌ |
| 6. Multiple Choice | MVP | ❌ |
| 7. Resume Conversation | V2 | ❌ |
| 8. Cancel Execution | V2 | ❌ |

---

## Next Priority

1. **Scenario 2 completion** - Add dial preview (light green/red) before confirm
2. **Scenario 1** - Simple question flow
3. **Scenario 5** - Error feedback
