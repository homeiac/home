# Voice Approval Design

**Date**: 2025-12-20
**Status**: Ready for implementation

## Overview

Enable approval of Claude actions via voice ("yes"/"no") without wake word, while keeping dial approval as fallback.

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     APPROVAL REQUEST FLOW                           │
└─────────────────────────────────────────────────────────────────────┘

ClaudeCodeUI needs approval
        │
        ▼
MQTT: claude/approval-request
{"requestId": "abc123", "message": "Restart frigate deployment?"}
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ HA Automation: claude_approval_request                              │
│                                                                     │
│  1. Store requestId → input_text.claude_approval_request_id         │
│  2. Set awaiting flag → input_boolean.claude_awaiting_approval = on │
│  3. LED → orange                                                    │
│  4. Start conversation:                                             │
│     service: assist_satellite.start_conversation                    │
│     target: assist_satellite.home_assistant_voice_09f5a3            │
│     data:                                                           │
│       start_message: "{{ trigger.payload_json.message }}"           │
└─────────────────────────────────────────────────────────────────────┘
        │
        ▼
Voice PE: Speaks question AND starts listening (no wake word needed!)
        │
        │
   ┌────┴────────────────────────────────┐
   │                                     │
   ▼                                     ▼
┌──────────────────────┐    ┌──────────────────────────────┐
│ OPTION A: Voice      │    │ OPTION B: Dial               │
│                      │    │                              │
│ User says "yes"      │    │ User turns dial CW + button  │
│         or "no"      │    │           or CCW + button    │
│                      │    │                              │
│ HA Intent triggers:  │    │ ESPHome event triggers:      │
│ ApproveClaudeAction  │    │ esphome.voice_pe_dial        │
│ RejectClaudeAction   │    │   direction: clockwise/ccw   │
└──────────┬───────────┘    └──────────────┬───────────────┘
           │                               │
           ▼                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ Both paths publish to same topic:                                │
│                                                                  │
│ MQTT: claude/approval-response                                   │
│ {"requestId": "<from input_text>", "approved": true/false,       │
│  "source": "voice" | "dial"}                                     │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ HA Automation: claude_approval_response                             │
│                                                                     │
│  1. LED → green (approved) or red (rejected)                        │
│  2. Clear awaiting flag                                             │
│  3. LED → off (after delay)                                         │
└─────────────────────────────────────────────────────────────────────┘
        │
        ▼
ClaudeCodeUI receives approval, executes action
```

## Key Insight

`assist_satellite.start_conversation` is the magic:
- Plays the approval question via TTS
- Automatically starts listening after TTS completes
- No wake word needed - user just says "yes" or "no"
- No firmware modification required!

## Components

### 1. Custom Sentences (HA)

**File**: `config/custom_sentences/en/voice_approval.yaml`

```yaml
language: en
intents:
  ApproveClaudeAction:
    data:
      - sentences:
          - "yes"
          - "approve"
          - "do it"
          - "go ahead"
          - "yep"
          - "yeah"
  RejectClaudeAction:
    data:
      - sentences:
          - "no"
          - "reject"
          - "cancel"
          - "stop"
          - "nope"
```

### 2. Intent Scripts (HA)

**File**: `config/intent_script.yaml` (merge)

```yaml
ApproveClaudeAction:
  action:
    - condition: state
      entity_id: input_boolean.claude_awaiting_approval
      state: "on"
    - service: mqtt.publish
      data:
        topic: claude/approval-response
        payload: >-
          {{ {"requestId": states("input_text.claude_approval_request_id"),
              "approved": true, "source": "voice"} | to_json }}
    - service: input_boolean.turn_off
      target:
        entity_id: input_boolean.claude_awaiting_approval
  speech:
    text: "Approved"

RejectClaudeAction:
  action:
    - condition: state
      entity_id: input_boolean.claude_awaiting_approval
      state: "on"
    - service: mqtt.publish
      data:
        topic: claude/approval-response
        payload: >-
          {{ {"requestId": states("input_text.claude_approval_request_id"),
              "approved": false, "source": "voice"} | to_json }}
    - service: input_boolean.turn_off
      target:
        entity_id: input_boolean.claude_awaiting_approval
  speech:
    text: "Rejected"
```

### 3. Approval Request Automation (HA)

**Trigger**: MQTT `claude/approval-request`

**Actions**:
1. Store requestId in `input_text.claude_approval_request_id`
2. Set `input_boolean.claude_awaiting_approval` = on
3. LED orange via `light.turn_on`
4. Call `assist_satellite.start_conversation` with the approval message

### 4. Dial Approval (existing)

Already implemented - fires `esphome.voice_pe_dial` event which HA automation handles.

## HA Helpers Required

| Helper | Type | Purpose |
|--------|------|---------|
| `input_text.claude_approval_request_id` | Text | Stores requestId for correlation |
| `input_boolean.claude_awaiting_approval` | Toggle | Guards voice intents |

## Testing

1. Trigger approval request manually:
   ```bash
   mosquitto_pub -h mqtt.host -t claude/approval-request \
     -m '{"requestId":"test123","message":"Should I restart frigate?"}'
   ```

2. Voice PE should:
   - LED → orange
   - Speak: "Should I restart frigate?"
   - Start listening

3. Say "yes" → Should hear "Approved", LED → green → off

4. Or turn dial CW + press button → Same result

## Failed Approach (for RCA)

Attempted to add `voice_assistant.start:` as ESPHome action callable from HA.
Caused boot loop - likely initialization timing issue where voice_assistant
component wasn't ready when action was registered.

Solution: Use `assist_satellite.start_conversation` instead - it's an HA
service that works without firmware modification.
