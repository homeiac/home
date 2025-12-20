# Voice PE Approval UX Scenarios

*Updated: 2025-12-17*
*Status: Requirements finalized, ready for implementation*

---

## Design Principles

1. **Every word costs attention** - Speak less, convey more
2. **Learn once, use forever** - Don't repeat instructions at runtime
3. **Preview before commit** - Dial rotation shows intent, confirmation executes
4. **Voice AND touch** - Dial, button, or voice for all interactions
5. **Fail with details** - Technical error messages for debugging
6. **Long press = cancel** - Universal abort gesture

---

## Hardware Controls

| Control | Actions |
|---------|---------|
| **Rotary Dial** | Rotate CW (right), Rotate CCW (left) |
| **Center Button** | Short press, Long press (1s), Tap patterns (1-5) |
| **LED Ring** | 12 RGB LEDs, full ring or segments |
| **Voice** | Wake word + natural language |

---

## LED Color Reference

| Color | Meaning |
|-------|---------|
| **Blue** | Processing / Thinking / Executing |
| **Orange (full ring)** | Waiting for input |
| **Light green (full ring)** | Preview: approve selected |
| **Light red (full ring)** | Preview: reject selected |
| **Bright green (full ring)** | Confirmed: approved |
| **Bright red (full ring)** | Confirmed: rejected / Error |
| **White → Gray gradient** | Context age (conversation turns) |
| **Colored segments** | Multiple choice options |
| **Off** | Idle |

---

## Scenarios

### Scenario 1: Simple Question

```
VOICE INPUT ──► VOICE: "Asking Claude"
               LED: Blue (thinking)

Response    ──► VOICE: "Four"
               LED: Off

Hardware during blue:
• Short press  → Beep
• Dial         → Beep
• Long press   → VOICE: "Cancelled", LED: Red → Off
```

---

### Scenario 2: Binary Approval (Yes/No)

```
Claude needs  ──► VOICE: "Run kubectl get nodes?"
approval          LED: Orange (full ring)

PATH A: APPROVE VIA DIAL (two-step)
[Rotate CW]    ──► LED: Light green (full ring) ← preview
[Button OR     ──► LED: Bright green → Blue (executing)
 Rotate CW]

PATH B: REJECT VIA DIAL (two-step)
[Rotate CCW]   ──► LED: Light red (full ring) ← preview
[Button OR     ──► LED: Bright red
 Rotate CCW]       VOICE: "Cancelled", LED: Off

PATH C: VOICE (immediate, no preview)
"yes"          ──► LED: Bright green → Blue
"no"           ──► LED: Bright red, VOICE: "Cancelled", LED: Off

PATH D: TIMEOUT
(10 sec)       ──► VOICE: "Still there?"
(5 more sec)   ──► VOICE: "Never mind", LED: Off

PATH E: CHANGE MIND (during preview)
[Opposite dial]──► Back to orange
[10s no action]──► Back to orange

ERROR FEEDBACK
Orange: Short press → Beep (choose first)
Orange: Long press  → Reject
Preview: Long press → Reject
```

---

### Scenario 3: Multiple Approvals in Sequence

```
WAITING STATE: Progress LEDs
• Done approvals = solid green LED (clockwise from 12 o'clock)
• Current approval = blinking orange LED

Example (3 approvals):
  Approval 1: LED at 12 o'clock blinks orange
  [Approve]   LED at 12 goes solid green

  Approval 2: LEDs 12 green, 1 o'clock blinks orange
  [Approve]   LEDs 12 + 1 solid green

  Approval 3: LEDs 12 + 1 green, 2 o'clock blinks orange
  [Approve]   3 green LEDs briefly → Off

PREVIEW/CONFIRM: Full ring (same as binary)
• Rotate → full ring light green/red
• Button → full ring bright green/red → Blue

REJECT MID-SEQUENCE
• Reject any approval → VOICE: "Cancelled", entire task stops
```

---

### Scenario 4: Follow-Up Questions (Conversation Continuity)

```
CONTEXT TIMER (ring counts down)
• Full ring after response, drains clockwise
• 60 seconds default (configurable)
• Timer resets on each interaction

CONVERSATION TURNS (color ages slowly)
Turn 1-2   ──► Context ring: Bright white
Turn 3-4   ──► Context ring: Light gray
Turn 5-6   ──► Context ring: Medium gray
Turn 7-8   ──► Context ring: Dark gray
Turn 9-10  ──► Context ring: Dim gray
Turn 11+   ──► Context ring: Nearly off

BEHAVIOR
• Within timeout: Claude remembers context
• After timeout: Fresh conversation (ring empty)
```

---

### Scenario 5: System/Automation Failures

```
All failures: Red LED + technical voice message

MQTT timeout    ──► "MQTT publish to claude/request timed out
                    after 10 seconds."

No response     ──► "No response on claude/response after
                    30 seconds."

MQTT disconnect ──► "MQTT broker disconnected. Check
                    homeassistant.maas 1883."

Automation error──► "Automation claude_approval_dial_cw threw
                    error. Check HA logs."

Parse error     ──► "JSON parse error on claude/response.
                    Missing field: requestId."

HTTP error      ──► "ClaudeCodeUI returned 503 service
                    unavailable."
```

---

### Scenario 6: Multiple Choice (up to 5 options)

```
Claude asks   ──► VOICE: "Which service? 1. nginx,
                        2. postgres, 3. redis"
                  LED: 3 colored segments (options)
                       Option 1 highlighted (bright)

SELECT VIA DIAL (with voice feedback)
[Rotate CW]   ──► LED: Option 2 highlighted
                  VOICE: "postgres" (announces option)
[Rotate CW]   ──► LED: Option 3 highlighted
                  VOICE: "redis"
[Button]      ──► Selected option pulses → Blue

SELECT VIA VOICE
"postgres"    ──► Option 2 pulses → Blue
              (no repeat needed - user said it)

SELECT VIA BUTTON TAPS
[Single tap]  ──► Option 1 flashes, VOICE: "nginx"
[Double tap]  ──► Option 2 flashes, VOICE: "postgres"
[Triple tap]  ──► Option 3 flashes, VOICE: "redis"
              (confirms after 400ms timeout)

ABORT
[Long press]  ──► VOICE: "Cancelled", LED: Red → Off
"cancel"      ──► Same

AFTER SELECTION
──► VOICE: "Run systemctl restart postgres?"
    LED: Orange (binary approval flow)

NOTES
• Up to 5 options supported
• Options wrap around (5 → 1 → 2...)
• System prompt blocks multi-tab questions for MVP

LED LAYOUT (by option count):
3 options = 4 LEDs each segment
4 options = 3 LEDs each segment
5 options = 2-3 LEDs each segment
```

---

### Scenario 7: Resume Previous Conversation (V2)

```
User          ──► "Hey Nabu, ask Claude to resume"

              ──► VOICE: "Resuming. We were discussing
                         server status."
                  LED: Context color restored

User          ──► "which has the most pods?"
              (Context restored beyond 60s window)
```

---

### Scenario 8: Cancel During Execution (V2)

```
LED: Blue (executing)

"stop" or     ──► VOICE: "Stopping."
[Long press]      LED: Red → Off
                  (Sends SIGINT to running command)
```

---

## Universal Behaviors

| Input | Idle | Blue (thinking) | Orange (waiting) | Preview | Executing |
|-------|------|-----------------|------------------|---------|-----------|
| **Short press** | Red flash | Beep | Beep | Confirm | Beep (V1) |
| **Dial** | Red flash | Beep | Preview | Change/Confirm | Beep (V1) |
| **Long press** | Red flash | Cancel | Reject | Reject | Stop (V2) |
| **Voice** | Ignored | - | Immediate yes/no | Override | Stop (V2) |

---

## First-Time Onboarding

**Spoken once per device, on first approval request:**

> "Rotate right to preview approve, left to preview reject. Press the button to confirm. Or just say yes or no."

After onboarding, prompts are just: "Run X?"

---

## Timing Summary

| Event | Duration |
|-------|----------|
| Preview timeout | 10 seconds → back to orange |
| Approval timeout | 15 seconds total |
| Timeout warning | At 10 seconds |
| Context window | 60 seconds (configurable) |
| Long press | 1 second |
| Button tap pattern timeout | 400ms |

---

## Scenario Priority

| # | Scenario | Priority |
|---|----------|----------|
| 1 | Simple Question | MVP |
| 2 | Binary Approval | MVP |
| 3 | Multiple Approvals | MVP |
| 4 | Follow-Up | MVP |
| 5 | System Failures | MVP |
| 6 | Multiple Choice | MVP |
| 7 | Resume | V2 |
| 8 | Cancel Execution | V2 |

---

## System Prompt Requirements

For MVP, Claude Code system prompt must include:

```
When request comes from Voice PE client:
- Ask one question at a time
- Max 5 options per question
- No multi-part/tabbed questions
```
