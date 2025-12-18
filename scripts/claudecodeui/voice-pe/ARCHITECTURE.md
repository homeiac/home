# Voice PE Claude Approval - Architecture

*Updated: 2025-12-17 - Post-Feasibility Testing*

---

## Feasibility Testing Results (2025-12-17)

### ✅ VERIFIED WORKING

| Component | Status | Notes |
|-----------|--------|-------|
| **MQTT Pub/Sub** | ✅ | HA ↔ ClaudeCodeUI via `homeassistant.maas:1883` |
| **Approval Request** | ✅ | ClaudeCodeUI publishes `claude/approval-request` |
| **RequestId Storage** | ✅ | HA stores in `input_text.claude_approval_request_id` |
| **Dial CW/CCW** | ✅ | Triggers approve/reject automation via events |
| **MQTT Response** | ✅ | HA publishes `claude/approval-response` with matching requestId |
| **LED Control** | ✅ | Orange (waiting), Green (approved), Red (rejected) |
| **Voice TTS** | ✅ | Piper → Voice PE media player |
| **Response Speak** | ✅ | Claude response → Voice PE (not Google) |

### 🔧 ISSUES DISCOVERED & FIXED

| Issue | Root Cause | Fix |
|-------|------------|-----|
| **Duplicate approval requests** | Local Docker + K8s pod both subscribed | Message deduplication in `mqtt-bridge.js` |
| **Missing voice prompt** | Disabled automation had TTS | Merged TTS into v2 automation |
| **Google speaking responses** | `claude_speak_response` targeted both speakers | Removed Google target |
| **RequestId mismatch** | Test script bug (missing `tail -1`) | Fixed test script |

### 🏗️ ARCHITECTURAL LEARNINGS

#### 1. Topic Isolation is Essential

**Problem**: Local development container and K8s pod both subscribe to same MQTT topics → duplicate processing.

**Solution**: Topic prefix isolation for non-prod environments.

```
Production:  claude/command, claude/home/response, claude/approval-*
Test mode:   test/claude/command, test/claude/home/response, test/claude/approval-*
```

**Implementation**:
```bash
# ClaudeCodeUI run-local.sh
docker run ... \
  -e MQTT_COMMAND_TOPIC="${TOPIC_PREFIX}claude/command" \
  -e MQTT_RESPONSE_TOPIC="${TOPIC_PREFIX}claude/home/response" \
  ...

# Test scripts
./test-mqtt.sh --test  # Uses test/ prefix
```

#### 2. Message Deduplication Required

MQTT can deliver duplicate messages. ClaudeCodeUI must deduplicate.

```javascript
// mqtt-bridge.js
const recentMessages = new Map();
const DEDUPE_WINDOW_MS = 5000;

function isDuplicateMessage(payload) {
  const key = `${payload.source || ''}-${payload.message || ''}`;
  // Check and update map with 5s TTL
}
```

#### 3. Single Instance or Topic Isolation

**Constraint**: Only ONE instance of ClaudeCodeUI should subscribe to production topics at a time.

**Enforcement Options**:
- Stop local container before testing prod K8s
- Use `--test` flag for local development
- Future: MQTT shared subscriptions (not supported by HA broker)

#### 4. RequestId Flow Verified

```
┌─────────────┐     claude/approval-request     ┌─────────────┐
│ ClaudeCodeUI│────────────────────────────────►│     HA      │
│             │     {requestId: "abc123",       │             │
│             │      command: "kubectl..."}     │             │
└─────────────┘                                 └──────┬──────┘
                                                       │
                                               Store requestId in
                                               input_text entity
                                                       │
                                                       ▼
┌─────────────┐     claude/approval-response    ┌─────────────┐
│ ClaudeCodeUI│◄────────────────────────────────│     HA      │
│             │     {requestId: "abc123",       │  (dial/btn) │
│             │      approved: true}            │             │
└─────────────┘                                 └─────────────┘
```

**Critical**: HA automation must extract `requestId` from the stored input_text entity, NOT from the trigger payload (which may be stale).

---

## Design Principles

1. **Voice PE = I/O only** - Events in, LED/TTS out
2. **HA = Stateless I/O handler** - Dial/button → MQTT, LED, TTS (no state machine)
3. **ClaudeCodeUI = State owner** - Claude API, conversation context, ALL state logic
4. **No firmware mods** - Use Voice PE as-is
5. **DRY** - Define patterns/templates once, reuse everywhere

---

## Verified MVP Architecture

**Based on tested scripts: `test-ha-approval.sh`, `test-mqtt.sh`, `automation-claude-led-v2.yaml`**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MVP ARCHITECTURE (VERIFIED)                               │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         ClaudeCodeUI                                 │   │
│  │                                                                       │   │
│  │  Owns:                                                                │   │
│  │  • Conversation with Claude API                                      │   │
│  │  • Knows when approval is needed (tool_use requiring approval)       │   │
│  │  • Publishes: claude/approval-request {requestId, command}          │   │
│  │  • Receives: claude/approval-response {requestId, approved}         │   │
│  │  • Executes command after approval                                   │   │
│  │  • Publishes: claude/home/response {type, text}                     │   │
│  │                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│                              │ MQTT                                          │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         HOME ASSISTANT                               │   │
│  │                                                                       │   │
│  │  Handles:                                                             │   │
│  │  • Receives claude/approval-request → LED orange, TTS prompt         │   │
│  │  • Stores requestId in input_text.claude_approval_request_id        │   │
│  │  • Dial CW → publishes claude/approval-response {approved: true}    │   │
│  │  • Dial CCW → publishes claude/approval-response {approved: false}  │   │
│  │  • Button → publishes claude/approval-response {approved: true}     │   │
│  │  • Receives approval-response → LED green/red flash                 │   │
│  │  • Receives claude/command → LED blue (thinking)                    │   │
│  │  • Receives response complete → LED off                             │   │
│  │                                                                       │   │
│  │  HA is stateless (no state machine). Just:                           │   │
│  │  • input_text.claude_approval_request_id (correlation ID pass-thru) │   │
│  │  • input_boolean.claude_awaiting_approval (guard/lock)              │   │
│  │                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│                              │ ESPHome API                                   │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         VOICE PE                                     │   │
│  │                                                                       │   │
│  │  • Sends dial/button events to HA                                    │   │
│  │  • Receives LED commands from HA                                     │   │
│  │  • Receives TTS from HA (via Piper)                                  │   │
│  │                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### MVP MQTT Flow (Verified)

```
1. User sends command via MQTT or voice
   → claude/command {message: "delete /tmp/test.txt"}

2. ClaudeCodeUI receives, calls Claude API
   → Claude returns tool_use requiring approval

3. ClaudeCodeUI publishes approval request
   → claude/approval-request {requestId: "abc", command: "rm /tmp/test.txt"}

4. HA automation triggers:
   → LED: orange
   → TTS: "Run rm /tmp/test.txt?"
   → Store: input_text.claude_approval_request_id = "abc"
   → Set: input_boolean.claude_awaiting_approval = true

5. User rotates dial CW (approve)
   → HA automation publishes:
   → claude/approval-response {requestId: "abc", approved: true}

6. ClaudeCodeUI receives approval, executes command
   → Calls Claude to continue
   → Publishes result to claude/home/response

7. HA automation receives response
   → LED: green flash → off
   → TTS: speaks response
```

### HA Entities (MVP) - Not State, Just Plumbing

```yaml
# Correlation ID pass-through (like HTTP session param)
input_text:
  claude_approval_request_id:
    name: Claude Approval Request ID
    max: 255

# Guard/lock to prevent spurious dial events
input_boolean:
  claude_awaiting_approval:
    name: Claude Awaiting Approval
```

**Note:** These are NOT state machine state. HA doesn't know THINKING vs WAITING.
ClaudeCodeUI owns all state logic. HA just stores correlation ID and has a lock.

### Key Files (MVP)

| File | Purpose |
|------|---------|
| `automation-claude-led-v2.yaml` | HA automation handling all MQTT/events |
| `test-mqtt.sh` | E2E test script |
| `test-ha-approval.sh` | Approval flow test (requires physical dial) |
| `run-local.sh` | Local Docker dev environment |

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         VOICE PE (ESPHome)                               │
│                              I/O ONLY                                    │
│                                                                          │
│  INPUTS:                              OUTPUTS:                           │
│  • esphome.voice_pe_dial         →   • light.voice_pe_led               │
│  • esphome.voice_pe_button       →   • media_player.voice_pe (TTS)      │
│  • Wake word / STT               →                                       │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                    Events ↓         │         ↑ Service calls
                                     │
┌────────────────────────────────────┴────────────────────────────────────┐
│                         HOME ASSISTANT                                   │
│                    LOCAL I/O HANDLER (minimal state)                     │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     MQTT ↔ EVENT HANDLER                         │   │
│  │                     (automation-claude-led-v2.yaml)              │   │
│  │                                                                   │   │
│  │  MQTT Triggers → Actions:                                        │   │
│  │    claude/command         → LED blue                             │   │
│  │    claude/approval-request→ LED orange, TTS, store requestId    │   │
│  │    claude/home/response   → LED off, TTS response               │   │
│  │    claude/approval-response→ LED green/red flash                │   │
│  │                                                                   │   │
│  │  ESPHome Events → Actions:                                       │   │
│  │    dial CW  + awaiting → publish approval-response: true        │   │
│  │    dial CCW + awaiting → publish approval-response: false       │   │
│  │    button   + awaiting → publish approval-response: true        │   │
│  │                                                                   │   │
│  │  Correlation: input_text.claude_approval_request_id (pass-thru) │   │
│  │  Guard:       input_boolean.claude_awaiting_approval (lock)     │   │
│  │                                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │ script.led   │  │ script.voice │  │ script.mqtt  │                  │
│  │ (controller) │  │ (controller) │  │ (publish)    │                  │
│  └──────────────┘  └──────────────┘  └──────────────┘                  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  TIMERS: preview(10s), approval(15s), context(60s)               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                              MQTT ↕ │
                                     │
┌────────────────────────────────────┴────────────────────────────────────┐
│                          CLAUDECODEUI                                    │
│                           MQTT BRIDGE                                    │
│                                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐            │
│  │  MQTT Handler  │──│  Conversation  │──│  Claude Code   │            │
│  │                │  │  Manager       │  │  Client        │            │
│  │ claude/request │  │ (context,turn) │  │                │            │
│  │ claude/response│  │                │  │                │            │
│  └────────────────┘  └────────────────┘  └────────────────┘            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## States

| State | LED | Entry Actions |
|-------|-----|---------------|
| `IDLE` | Off | Cancel timers |
| `THINKING` | Blue solid | - |
| `WAITING` | Orange solid | Start 15s timer, voice prompt |
| `PREVIEW_APPROVE` | Light green | Start 10s preview timer |
| `PREVIEW_REJECT` | Light red | Start 10s preview timer |
| `EXECUTING` | Blue solid | Send MQTT approve, cancel timers |
| `MULTIPLE_CHOICE` | Colored segments | Voice options |
| `ERROR` | Red flash | Voice error message |

---

## Transitions

```
┌─────────────────────┬─────────────────┬─────────────────────────────────┐
│ From                │ Event           │ To + Side Effects               │
├─────────────────────┼─────────────────┼─────────────────────────────────┤
│ IDLE                │ request_sent    │ THINKING                        │
│ THINKING            │ response        │ IDLE + voice(answer)            │
│ THINKING            │ approval_needed │ WAITING + voice(prompt)         │
│ THINKING            │ choice_needed   │ MULTIPLE_CHOICE + voice(opts)   │
│ THINKING            │ long_press      │ IDLE + voice(cancel)            │
│ WAITING             │ dial_cw         │ PREVIEW_APPROVE                 │
│ WAITING             │ dial_ccw        │ PREVIEW_REJECT                  │
│ WAITING             │ voice_yes       │ EXECUTING                       │
│ WAITING             │ voice_no        │ IDLE + voice(cancel)            │
│ WAITING             │ long_press      │ IDLE + voice(cancel)            │
│ WAITING             │ short_press     │ (same) + beep                   │
│ WAITING             │ timeout         │ IDLE + voice(nevermind)         │
│ PREVIEW_APPROVE     │ button          │ EXECUTING                       │
│ PREVIEW_APPROVE     │ dial_cw         │ EXECUTING                       │
│ PREVIEW_APPROVE     │ dial_ccw        │ WAITING                         │
│ PREVIEW_APPROVE     │ long_press      │ IDLE + voice(cancel)            │
│ PREVIEW_APPROVE     │ preview_timeout │ WAITING                         │
│ PREVIEW_REJECT      │ button          │ IDLE + voice(cancel) + mqtt     │
│ PREVIEW_REJECT      │ dial_ccw        │ IDLE + voice(cancel) + mqtt     │
│ PREVIEW_REJECT      │ dial_cw         │ WAITING                         │
│ PREVIEW_REJECT      │ long_press      │ IDLE + voice(cancel) + mqtt     │
│ PREVIEW_REJECT      │ preview_timeout │ WAITING                         │
│ EXECUTING           │ response        │ IDLE or next WAITING            │
│ EXECUTING           │ error           │ ERROR + voice(error_msg)        │
│ MULTIPLE_CHOICE     │ dial_cw         │ (same) + highlight + voice(opt) │
│ MULTIPLE_CHOICE     │ dial_ccw        │ (same) + highlight + voice(opt) │
│ MULTIPLE_CHOICE     │ button          │ WAITING + voice(confirm_prompt) │
│ MULTIPLE_CHOICE     │ tap_N           │ WAITING + voice(confirm_prompt) │
│ MULTIPLE_CHOICE     │ long_press      │ IDLE + voice(cancel) + mqtt     │
└─────────────────────┴─────────────────┴─────────────────────────────────┘
```

---

## HA Event Handling (MVP)

**HA handles dial/button events locally.** It doesn't forward to ClaudeCodeUI - it acts on them directly.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HA EVENT HANDLING (MVP)                              │
│                                                                              │
│  ┌───────────────────────────────┬──────────────────────────────────────┐   │
│  │ Event                         │ HA Action                            │   │
│  ├───────────────────────────────┼──────────────────────────────────────┤   │
│  │ MQTT: claude/command          │ LED blue (thinking effect)          │   │
│  │ MQTT: claude/approval-request │ LED orange, TTS prompt, store ID    │   │
│  │ MQTT: claude/home/response    │ LED off (if complete), TTS response │   │
│  │ MQTT: claude/approval-response│ LED green/red flash                 │   │
│  │ ESPHome: dial CW              │ Publish approval-response: approved │   │
│  │ ESPHome: dial CCW             │ Publish approval-response: rejected │   │
│  │ ESPHome: button press         │ Publish approval-response: approved │   │
│  └───────────────────────────────┴──────────────────────────────────────┘   │
│                                                                              │
│  Guard: Dial/button events only act if awaiting_approval = true             │
│                                                                              │
│  HA owns: LED control, TTS, dial/button → approval-response                │
│  ClaudeCodeUI owns: conversation, when to request approval                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Helper Entities

```yaml
# State
input_select:
  claude_state:
    options:
      - IDLE
      - THINKING
      - WAITING
      - PREVIEW_APPROVE
      - PREVIEW_REJECT
      - EXECUTING
      - MULTIPLE_CHOICE
      - ERROR

# Request tracking
input_text:
  claude_request_id:
    max: 64
  claude_pending_command:
    max: 256
  claude_choice_options:        # JSON array
    max: 1024

# Multi-approval tracking
input_number:
  claude_approval_count:
    min: 0
    max: 12
  claude_current_approval:
    min: 0
    max: 12

# Multiple choice
input_number:
  claude_choice_selected:
    min: 1
    max: 5
  claude_choice_count:
    min: 2
    max: 5

# Conversation context
input_number:
  claude_conversation_turn:
    min: 0
    max: 20

# Timers
timer:
  claude_preview:
    duration: "00:00:10"
  claude_approval:
    duration: "00:00:15"
  claude_context:
    duration: "00:01:00"
    restore: true
```

---

## LED Controller

```yaml
script:
  claude_led:
    alias: "Claude LED Controller"
    mode: restart
    fields:
      mode:
        description: "LED mode"
        selector:
          select:
            options: [off, solid, blink, progress, choice, timer]
      color:
        description: "Color name"
        selector:
          select:
            options: [orange, green, red, blue, white, lt_green, lt_red]
      # For progress mode
      completed:
        description: "Completed approvals (green LEDs)"
      current:
        description: "Current approval index (blink orange)"
      # For choice mode
      option_count:
        description: "Number of options (2-5)"
      selected:
        description: "Currently selected option"
      # For timer mode
      percent:
        description: "Ring fill percentage (0-100)"

    variables:
      colors:
        orange:    [255, 165, 0]
        green:     [0, 255, 0]
        red:       [255, 0, 0]
        blue:      [0, 0, 255]
        white:     [255, 255, 255]
        lt_green:  [0, 255, 0]    # brightness 128
        lt_red:    [255, 0, 0]    # brightness 128
      brightness:
        lt_green: 128
        lt_red: 128
        default: 255

    sequence:
      - choose:
          - conditions: "{{ mode == 'off' }}"
            sequence:
              - service: light.turn_off
                target:
                  entity_id: light.home_assistant_voice_09f5a3_led_ring

          - conditions: "{{ mode == 'solid' }}"
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.home_assistant_voice_09f5a3_led_ring
                data:
                  rgb_color: "{{ colors[color] }}"
                  brightness: "{{ brightness.get(color, brightness.default) }}"

          # Additional modes: blink, progress, choice, timer
          # Implementation depends on Voice PE LED capabilities
```

---

## Voice Controller

```yaml
script:
  claude_voice:
    alias: "Claude Voice Controller"
    mode: queued
    fields:
      message:
        description: "Message template key"
      command:
        description: "Command for approval_prompt"
      option_name:
        description: "Option name for choice"
      error_code:
        description: "Error code"
      error_details:
        description: "Error details"

    variables:
      templates:
        asking_claude: "Asking Claude"
        approval_prompt: "Run {{ command }}?"
        cancelled: "Cancelled."
        timeout_warning: "Still there?"
        timeout: "Never mind."
        option: "{{ option_name }}"
        error:
          MQTT_TIMEOUT: "MQTT publish to claude request timed out after {{ error_details }}."
          NO_RESPONSE: "No response on claude response after {{ error_details }}."
          MQTT_DISCONNECT: "MQTT broker disconnected. Check homeassistant.maas 1883."
          AUTOMATION_ERROR: "Automation {{ error_details }} threw error. Check HA logs."
          PARSE_ERROR: "JSON parse error on claude response. {{ error_details }}."
          HTTP_ERROR: "ClaudeCodeUI returned {{ error_details }}."

    sequence:
      - service: tts.speak
        target:
          entity_id: tts.piper
        data:
          media_player_entity_id: media_player.home_assistant_voice_09f5a3_media_player
          message: >
            {% if message == 'error' %}
              {{ templates.error[error_code] }}
            {% else %}
              {{ templates[message] }}
            {% endif %}
```

---

## MQTT Protocol

### Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `claude/request` | HA → ClaudeCodeUI | User voice request |
| `claude/response` | ClaudeCodeUI → HA | Claude response/approval request |
| `claude/approval-response` | HA → ClaudeCodeUI | User approval decision |

### Message: claude/request

```json
{
  "text": "what's my server status",
  "conversationId": "uuid-optional",
  "source": "voice_pe"
}
```

### Message: claude/response

```json
{
  "type": "question | approval | choice | response | error | multi_approval",
  "requestId": "uuid",
  "conversationId": "uuid",
  "turnNumber": 3,

  // type=question (no approval needed)
  "text": "Two plus two equals four.",

  // type=approval
  "command": "kubectl get nodes",

  // type=choice
  "question": "Which service?",
  "options": ["nginx", "postgres", "redis"],

  // type=multi_approval
  "command": "kubectl apply -f manifest.yaml",
  "approvalIndex": 2,
  "approvalTotal": 5,

  // type=response (after execution)
  "text": "All three nodes are ready.",

  // type=error
  "code": "MQTT_TIMEOUT",
  "message": "Technical error details here"
}
```

### Message: claude/approval-response

```json
{
  "requestId": "uuid",
  "type": "approved | rejected | choice | cancelled",
  "selectedOption": 2,     // for choice
  "reason": "timeout"      // optional: timeout, user_reject, user_cancel
}
```

---

## Event Router

Single automation that captures all Voice PE events and routes to transition handler.

```yaml
automation:
  - alias: "Claude Event Router"
    id: claude_event_router
    mode: queued
    trigger:
      # Dial events
      - platform: event
        event_type: esphome.voice_pe_dial
        id: dial
      # Button events
      - platform: event
        event_type: esphome.voice_pe_button
        id: button
      # Voice intent (yes/no)
      - platform: event
        event_type: intent_handled
        event_data:
          intent_type: claude_approval
        id: voice_intent
      # MQTT response from ClaudeCodeUI
      - platform: mqtt
        topic: claude/response
        id: mqtt_response

    action:
      - choose:
          # Dial CW
          - conditions: >
              {{ trigger.id == 'dial' and
                 trigger.event.data.direction == 'clockwise' }}
            sequence:
              - service: script.claude_transition
                data:
                  event: dial_cw

          # Dial CCW
          - conditions: >
              {{ trigger.id == 'dial' and
                 trigger.event.data.direction == 'anticlockwise' }}
            sequence:
              - service: script.claude_transition
                data:
                  event: dial_ccw

          # Button short press
          - conditions: >
              {{ trigger.id == 'button' and
                 trigger.event.data.type == 'single' }}
            sequence:
              - service: script.claude_transition
                data:
                  event: button

          # Button long press
          - conditions: >
              {{ trigger.id == 'button' and
                 trigger.event.data.type == 'long' }}
            sequence:
              - service: script.claude_transition
                data:
                  event: long_press

          # Button taps (2-5)
          - conditions: >
              {{ trigger.id == 'button' and
                 trigger.event.data.type in ['double', 'triple', 'quadruple', 'quintuple'] }}
            sequence:
              - service: script.claude_transition
                data:
                  event: "tap_{{ {'double':2, 'triple':3, 'quadruple':4, 'quintuple':5}[trigger.event.data.type] }}"

          # Voice yes/no
          - conditions: "{{ trigger.id == 'voice_intent' }}"
            sequence:
              - service: script.claude_transition
                data:
                  event: "voice_{{ trigger.event.data.response }}"

          # MQTT response
          - conditions: "{{ trigger.id == 'mqtt_response' }}"
            sequence:
              - service: script.claude_transition
                data:
                  event: "{{ (trigger.payload | from_json).type }}"
                  payload: "{{ trigger.payload }}"
```

---

## Transition Handler

Central script that implements the state machine logic.

```yaml
script:
  claude_transition:
    alias: "Claude State Transition"
    mode: queued
    fields:
      event:
        description: "Event name (dial_cw, button, timeout, etc.)"
      payload:
        description: "Optional JSON payload for MQTT events"

    variables:
      current_state: "{{ states('input_select.claude_state') }}"
      payload_json: "{{ payload | from_json if payload else {} }}"

    sequence:
      - choose:
          #================================================
          # FROM: IDLE
          #================================================
          - conditions: "{{ current_state == 'IDLE' and event == 'request_sent' }}"
            sequence:
              - service: input_select.select_option
                target: { entity_id: input_select.claude_state }
                data: { option: THINKING }
              - service: script.claude_led
                data: { mode: solid, color: blue }
              - service: script.claude_voice
                data: { message: asking_claude }

          #================================================
          # FROM: THINKING
          #================================================
          - conditions: "{{ current_state == 'THINKING' and event == 'response' }}"
            sequence:
              - service: input_select.select_option
                target: { entity_id: input_select.claude_state }
                data: { option: IDLE }
              - service: script.claude_led
                data: { mode: off }
              - service: script.claude_voice
                data:
                  message: answer
                  text: "{{ payload_json.text }}"

          - conditions: "{{ current_state == 'THINKING' and event == 'approval' }}"
            sequence:
              - service: input_text.set_value
                target: { entity_id: input_text.claude_request_id }
                data: { value: "{{ payload_json.requestId }}" }
              - service: input_text.set_value
                target: { entity_id: input_text.claude_pending_command }
                data: { value: "{{ payload_json.command }}" }
              - service: input_select.select_option
                target: { entity_id: input_select.claude_state }
                data: { option: WAITING }
              - service: timer.start
                target: { entity_id: timer.claude_approval }
              - service: script.claude_led
                data: { mode: solid, color: orange }
              - service: script.claude_voice
                data:
                  message: approval_prompt
                  command: "{{ payload_json.command }}"

          - conditions: "{{ current_state == 'THINKING' and event == 'choice' }}"
            sequence:
              - service: input_text.set_value
                target: { entity_id: input_text.claude_choice_options }
                data: { value: "{{ payload_json.options | to_json }}" }
              - service: input_number.set_value
                target: { entity_id: input_number.claude_choice_count }
                data: { value: "{{ payload_json.options | length }}" }
              - service: input_number.set_value
                target: { entity_id: input_number.claude_choice_selected }
                data: { value: 1 }
              - service: input_select.select_option
                target: { entity_id: input_select.claude_state }
                data: { option: MULTIPLE_CHOICE }
              - service: script.claude_led
                data:
                  mode: choice
                  option_count: "{{ payload_json.options | length }}"
                  selected: 1
              - service: script.claude_voice
                data:
                  message: choice_prompt
                  options: "{{ payload_json.options }}"

          - conditions: "{{ current_state == 'THINKING' and event == 'long_press' }}"
            sequence:
              - service: input_select.select_option
                target: { entity_id: input_select.claude_state }
                data: { option: IDLE }
              - service: script.claude_led
                data: { mode: solid, color: red }
              - delay: { seconds: 1 }
              - service: script.claude_led
                data: { mode: off }
              - service: script.claude_voice
                data: { message: cancelled }

          #================================================
          # FROM: WAITING
          #================================================
          - conditions: "{{ current_state == 'WAITING' and event == 'dial_cw' }}"
            sequence:
              - service: input_select.select_option
                target: { entity_id: input_select.claude_state }
                data: { option: PREVIEW_APPROVE }
              - service: timer.start
                target: { entity_id: timer.claude_preview }
              - service: script.claude_led
                data: { mode: solid, color: lt_green }

          - conditions: "{{ current_state == 'WAITING' and event == 'dial_ccw' }}"
            sequence:
              - service: input_select.select_option
                target: { entity_id: input_select.claude_state }
                data: { option: PREVIEW_REJECT }
              - service: timer.start
                target: { entity_id: timer.claude_preview }
              - service: script.claude_led
                data: { mode: solid, color: lt_red }

          - conditions: "{{ current_state == 'WAITING' and event == 'voice_yes' }}"
            sequence:
              - service: script.claude_execute_approval
                data: { approved: true }

          - conditions: "{{ current_state == 'WAITING' and event == 'voice_no' }}"
            sequence:
              - service: script.claude_execute_approval
                data: { approved: false }

          - conditions: "{{ current_state == 'WAITING' and event == 'long_press' }}"
            sequence:
              - service: script.claude_execute_approval
                data: { approved: false, reason: user_cancel }

          - conditions: "{{ current_state == 'WAITING' and event == 'button' }}"
            sequence:
              # Beep - invalid action (rotate first)
              - service: script.claude_beep

          - conditions: "{{ current_state == 'WAITING' and event == 'timeout' }}"
            sequence:
              - service: script.claude_execute_approval
                data: { approved: false, reason: timeout }
              - service: script.claude_voice
                data: { message: timeout }

          #================================================
          # FROM: PREVIEW_APPROVE
          #================================================
          - conditions: "{{ current_state == 'PREVIEW_APPROVE' and event in ['button', 'dial_cw'] }}"
            sequence:
              - service: script.claude_execute_approval
                data: { approved: true }

          - conditions: "{{ current_state == 'PREVIEW_APPROVE' and event == 'dial_ccw' }}"
            sequence:
              - service: input_select.select_option
                target: { entity_id: input_select.claude_state }
                data: { option: WAITING }
              - service: timer.cancel
                target: { entity_id: timer.claude_preview }
              - service: script.claude_led
                data: { mode: solid, color: orange }

          - conditions: "{{ current_state == 'PREVIEW_APPROVE' and event == 'preview_timeout' }}"
            sequence:
              - service: input_select.select_option
                target: { entity_id: input_select.claude_state }
                data: { option: WAITING }
              - service: script.claude_led
                data: { mode: solid, color: orange }

          - conditions: "{{ current_state == 'PREVIEW_APPROVE' and event == 'long_press' }}"
            sequence:
              - service: script.claude_execute_approval
                data: { approved: false, reason: user_cancel }

          #================================================
          # FROM: PREVIEW_REJECT
          #================================================
          - conditions: "{{ current_state == 'PREVIEW_REJECT' and event in ['button', 'dial_ccw'] }}"
            sequence:
              - service: script.claude_execute_approval
                data: { approved: false }

          - conditions: "{{ current_state == 'PREVIEW_REJECT' and event == 'dial_cw' }}"
            sequence:
              - service: input_select.select_option
                target: { entity_id: input_select.claude_state }
                data: { option: WAITING }
              - service: timer.cancel
                target: { entity_id: timer.claude_preview }
              - service: script.claude_led
                data: { mode: solid, color: orange }

          - conditions: "{{ current_state == 'PREVIEW_REJECT' and event == 'preview_timeout' }}"
            sequence:
              - service: input_select.select_option
                target: { entity_id: input_select.claude_state }
                data: { option: WAITING }
              - service: script.claude_led
                data: { mode: solid, color: orange }

          - conditions: "{{ current_state == 'PREVIEW_REJECT' and event == 'long_press' }}"
            sequence:
              - service: script.claude_execute_approval
                data: { approved: false, reason: user_cancel }

          #================================================
          # FROM: MULTIPLE_CHOICE
          #================================================
          - conditions: "{{ current_state == 'MULTIPLE_CHOICE' and event == 'dial_cw' }}"
            sequence:
              - variables:
                  next: >
                    {% set current = states('input_number.claude_choice_selected') | int %}
                    {% set count = states('input_number.claude_choice_count') | int %}
                    {{ (current % count) + 1 }}
              - service: input_number.set_value
                target: { entity_id: input_number.claude_choice_selected }
                data: { value: "{{ next }}" }
              - service: script.claude_led
                data:
                  mode: choice
                  option_count: "{{ states('input_number.claude_choice_count') }}"
                  selected: "{{ next }}"
              - service: script.claude_voice
                data:
                  message: option
                  option_name: "{{ (states('input_text.claude_choice_options') | from_json)[next - 1] }}"

          - conditions: "{{ current_state == 'MULTIPLE_CHOICE' and event == 'dial_ccw' }}"
            sequence:
              - variables:
                  prev: >
                    {% set current = states('input_number.claude_choice_selected') | int %}
                    {% set count = states('input_number.claude_choice_count') | int %}
                    {{ ((current - 2) % count) + 1 }}
              - service: input_number.set_value
                target: { entity_id: input_number.claude_choice_selected }
                data: { value: "{{ prev }}" }
              - service: script.claude_led
                data:
                  mode: choice
                  option_count: "{{ states('input_number.claude_choice_count') }}"
                  selected: "{{ prev }}"
              - service: script.claude_voice
                data:
                  message: option
                  option_name: "{{ (states('input_text.claude_choice_options') | from_json)[prev - 1] }}"

          - conditions: "{{ current_state == 'MULTIPLE_CHOICE' and event == 'button' }}"
            sequence:
              - service: script.claude_execute_choice

          - conditions: "{{ current_state == 'MULTIPLE_CHOICE' and event.startswith('tap_') }}"
            sequence:
              - variables:
                  tap_num: "{{ event.split('_')[1] | int }}"
              - service: input_number.set_value
                target: { entity_id: input_number.claude_choice_selected }
                data: { value: "{{ tap_num }}" }
              - service: script.claude_execute_choice

          - conditions: "{{ current_state == 'MULTIPLE_CHOICE' and event == 'long_press' }}"
            sequence:
              - service: script.claude_execute_choice
                data: { cancelled: true }
```

---

## Approval Executor

Shared script for sending approval/rejection via MQTT.

```yaml
script:
  claude_execute_approval:
    alias: "Execute Approval Decision"
    mode: single
    fields:
      approved:
        description: "true/false"
      reason:
        description: "Optional: timeout, user_reject, user_cancel"

    sequence:
      # Visual feedback
      - service: script.claude_led
        data:
          mode: solid
          color: "{{ 'green' if approved else 'red' }}"

      # Publish to MQTT
      - service: mqtt.publish
        data:
          topic: claude/approval-response
          payload: >
            {{ {
              "requestId": states('input_text.claude_request_id'),
              "type": "approved" if approved else "rejected",
              "reason": reason | default(omit)
            } | to_json }}

      # Cancel timers
      - service: timer.cancel
        target:
          entity_id:
            - timer.claude_preview
            - timer.claude_approval

      # Voice feedback
      - if: "{{ not approved }}"
        then:
          - service: script.claude_voice
            data: { message: cancelled }

      # State transition
      - service: input_select.select_option
        target: { entity_id: input_select.claude_state }
        data:
          option: "{{ 'EXECUTING' if approved else 'IDLE' }}"

      # LED transition
      - delay: { seconds: 1 }
      - service: script.claude_led
        data:
          mode: "{{ 'solid' if approved else 'off' }}"
          color: "{{ 'blue' if approved else omit }}"
```

---

## Timer Handlers

```yaml
automation:
  - alias: "Claude Preview Timeout"
    id: claude_preview_timeout
    trigger:
      - platform: event
        event_type: timer.finished
        event_data:
          entity_id: timer.claude_preview
    action:
      - service: script.claude_transition
        data:
          event: preview_timeout

  - alias: "Claude Approval Warning"
    id: claude_approval_warning
    trigger:
      - platform: template
        value_template: >
          {{ state_attr('timer.claude_approval', 'remaining') | int <= 5 and
             states('input_select.claude_state') == 'WAITING' }}
    action:
      - service: script.claude_voice
        data: { message: timeout_warning }

  - alias: "Claude Approval Timeout"
    id: claude_approval_timeout
    trigger:
      - platform: event
        event_type: timer.finished
        event_data:
          entity_id: timer.claude_approval
    action:
      - service: script.claude_transition
        data:
          event: timeout
```

---

## Sequence Diagrams

### Scenario 1: Simple Question

```
┌──────┐   ┌─────────┐   ┌────────────┐   ┌──────────┐   ┌─────────────┐   ┌───────────┐
│ User │   │Voice PE │   │    HA      │   │  MQTT    │   │ClaudeCodeUI │   │Claude API │
└──┬───┘   └────┬────┘   └─────┬──────┘   └────┬─────┘   └──────┬──────┘   └─────┬─────┘
   │            │              │               │                │                │
   │ "Hey Nabu, │              │               │                │                │
   │  what's    │              │               │                │                │
   │  2+2?"     │              │               │                │                │
   │───────────►│              │               │                │                │
   │            │              │               │                │                │
   │            │ STT: "what's 2+2"            │                │                │
   │            │─────────────►│               │                │                │
   │            │              │               │                │                │
   │            │              │ intent: ask_claude             │                │
   │            │              │ set state: THINKING            │                │
   │            │              │───────────────┼───────────────►│                │
   │            │              │ claude/command│                │                │
   │            │              │ {message:"what's 2+2"}         │                │
   │            │              │               │                │                │
   │            │◄─────────────│               │                │                │
   │            │ LED: blue    │               │                │                │
   │            │              │               │                │                │
   │            │◄─────────────│               │                │                │
   │            │ TTS: "Asking │               │                │                │
   │            │      Claude" │               │                │                │
   │            │              │               │                │ POST /messages │
   │            │              │               │                │───────────────►│
   │            │              │               │                │                │
   │            │              │               │                │◄───────────────│
   │            │              │               │                │ "Four"         │
   │            │              │               │                │                │
   │            │              │◄──────────────┼────────────────│                │
   │            │              │ claude/home/response           │                │
   │            │              │ {type:"answer",text:"Four"}    │                │
   │            │              │               │                │                │
   │            │              │ set state: IDLE                │                │
   │            │◄─────────────│               │                │                │
   │            │ LED: off     │               │                │                │
   │            │              │               │                │                │
   │            │◄─────────────│               │                │                │
   │            │ TTS: "Four"  │               │                │                │
   │            │              │               │                │                │
   │◄───────────│              │               │                │                │
   │ (hears     │              │               │                │                │
   │  "Four")   │              │               │                │                │
   │            │              │               │                │                │
```

### Scenario 2a: Binary Approval (Approve via Dial)

```
┌──────┐   ┌─────────┐   ┌────────────┐   ┌──────────┐   ┌─────────────┐   ┌───────────┐
│ User │   │Voice PE │   │    HA      │   │  MQTT    │   │ClaudeCodeUI │   │Claude API │
└──┬───┘   └────┬────┘   └─────┬──────┘   └────┬─────┘   └──────┬──────┘   └─────┬─────┘
   │            │              │               │                │                │
   │ "check my  │              │               │                │                │
   │  k8s nodes"│              │               │                │                │
   │───────────►│──────────────►──────────────►│───────────────►│───────────────►│
   │            │              │               │                │                │
   │            │◄─────────────│ LED: blue     │                │◄───────────────│
   │            │              │               │                │ tool_use:      │
   │            │              │               │                │ Bash(kubectl)  │
   │            │              │               │                │                │
   │            │              │◄──────────────┼────────────────│                │
   │            │              │ claude/approval-request        │                │
   │            │              │ {requestId:"abc",              │                │
   │            │              │  command:"kubectl get nodes"}  │                │
   │            │              │               │                │                │
   │            │              │ state: WAITING, store requestId│                │
   │            │◄─────────────│ LED: orange   │                │                │
   │            │◄─────────────│ TTS: "Run kubectl get nodes?"  │                │
   │            │              │               │                │                │
   │ [rotate CW]│              │               │                │                │
   │───────────►│─────────────►│               │                │                │
   │            │              │ state: PREVIEW_APPROVE         │                │
   │            │◄─────────────│ LED: lt_green │                │                │
   │            │              │               │                │                │
   │ [press btn]│              │               │                │                │
   │───────────►│─────────────►│               │                │                │
   │            │              │ state: EXECUTING               │                │
   │            │◄─────────────│ LED: green(1s)│                │                │
   │            │              │───────────────┼───────────────►│                │
   │            │              │ {requestId:"abc",approved:true}│                │
   │            │◄─────────────│ LED: blue     │                │                │
   │            │              │               │                │ (executes...)  │
   │            │              │◄──────────────┼────────────────│                │
   │            │              │ {type:"answer",text:"3 ready"} │                │
   │            │              │ state: IDLE   │                │                │
   │            │◄─────────────│ LED: off, TTS:"3 nodes ready"  │                │
   │            │              │               │                │                │
```

### Scenario 2b: Binary Approval (Reject via Dial)

```
┌──────┐   ┌─────────┐   ┌────────────┐   ┌──────────┐   ┌─────────────┐
│ User │   │Voice PE │   │    HA      │   │  MQTT    │   │ClaudeCodeUI │
└──┬───┘   └────┬────┘   └─────┬──────┘   └────┬─────┘   └──────┬──────┘
   │            │              │               │                │
   │  ... (approval request arrives, LED orange, TTS prompt) ...│
   │            │              │ state: WAITING                 │
   │            │              │               │                │
   │[rotate CCW]│              │               │                │
   │───────────►│─────────────►│               │                │
   │            │              │ state: PREVIEW_REJECT          │
   │            │◄─────────────│ LED: lt_red   │                │
   │            │              │               │                │
   │ [press btn]│              │               │                │
   │───────────►│─────────────►│               │                │
   │            │              │ state: IDLE   │                │
   │            │◄─────────────│ LED: red(1s)  │                │
   │            │              │───────────────┼───────────────►│
   │            │              │ {approved:false}               │
   │            │◄─────────────│ TTS:"Cancelled", LED: off      │
   │            │              │               │                │
```

### Scenario 2c: Binary Approval (Voice "yes")

```
┌──────┐   ┌─────────┐   ┌────────────┐   ┌──────────┐   ┌─────────────┐
│ User │   │Voice PE │   │    HA      │   │  MQTT    │   │ClaudeCodeUI │
└──┬───┘   └────┬────┘   └─────┬──────┘   └────┬─────┘   └──────┬──────┘
   │            │              │               │                │
   │  ... (approval request arrives, LED orange, TTS prompt) ...│
   │            │              │ state: WAITING                 │
   │            │              │               │                │
   │ "yes"      │              │               │                │
   │───────────►│ STT: "yes"   │               │                │
   │            │─────────────►│               │                │
   │            │              │ intent: claude_approve         │
   │            │              │ state: EXECUTING               │
   │            │◄─────────────│ LED: green(1s)│                │
   │            │              │───────────────┼───────────────►│
   │            │              │ {approved:true}                │
   │            │◄─────────────│ LED: blue     │ (executes...)  │
   │            │              │               │                │
   │            │  ... (response comes back, TTS speaks it) ... │
   │            │              │               │                │
```

### Scenario 2d: Timeout

```
┌──────┐   ┌─────────┐   ┌────────────┐   ┌──────────┐   ┌─────────────┐
│ User │   │Voice PE │   │    HA      │   │  MQTT    │   │ClaudeCodeUI │
└──┬───┘   └────┬────┘   └─────┬──────┘   └────┬─────┘   └──────┬──────┘
   │            │              │               │                │
   │  ... (approval request arrives, LED orange, TTS prompt) ...│
   │            │              │ state: WAITING                 │
   │            │              │ timer: 15s    │                │
   │            │              │               │                │
   │ (no input) │              │               │                │
   │            │              │ ─── 10 seconds ───             │
   │            │◄─────────────│ TTS: "Still there?"            │
   │            │              │               │                │
   │ (no input) │              │               │                │
   │            │              │ ─── 5 more seconds ───         │
   │            │              │ timer: finished                │
   │            │              │ state: IDLE   │                │
   │            │              │───────────────┼───────────────►│
   │            │              │ {approved:false,reason:"timeout"}
   │            │◄─────────────│ TTS: "Never mind", LED: off    │
   │            │              │               │                │
```

### Scenario 3: Multiple Approvals (3 commands)

```
┌──────┐   ┌─────────┐   ┌────────────┐   ┌──────────┐   ┌─────────────┐
│ User │   │Voice PE │   │    HA      │   │  MQTT    │   │ClaudeCodeUI │
└──┬───┘   └────┬────┘   └─────┬──────┘   └────┬─────┘   └──────┬──────┘
   │            │              │               │                │
   │ "deploy my app"           │               │                │
   │───────────►│──────────────►──────────────►│───────────────►│
   │            │              │               │                │
   │            │              │◄──────────────┼────────────────│
   │            │              │ approval-request               │
   │            │              │ {r1, cmd:"kubectl apply",      │
   │            │              │  approvalIndex:1, total:3}     │
   │            │              │               │                │
   │            │◄─────────────│ LED: [◯◯◯◯◯◯◯◯◯◯◯●]            │
   │            │              │ (12 o'clock blinks orange)     │
   │            │◄─────────────│ TTS: "1 of 3: kubectl apply?"  │
   │            │              │               │                │
   │ [approve]  │              │               │                │
   │───────────►│─────────────►│───────────────┼───────────────►│
   │            │◄─────────────│ LED: [●◯◯◯◯◯◯◯◯◯◯◯]            │
   │            │              │ (12 solid green)               │
   │            │              │               │                │
   │            │              │◄──────────────┼────────────────│
   │            │              │ {r2, "docker push", 2/3}       │
   │            │◄─────────────│ LED: [●●◯◯◯◯◯◯◯◯◯◯]            │
   │            │◄─────────────│ TTS: "2 of 3: docker push?"    │
   │            │              │               │                │
   │ [approve]  │              │               │                │
   │───────────►│─────────────►│───────────────┼───────────────►│
   │            │◄─────────────│ LED: [●●◯◯◯◯◯◯◯◯◯◯]            │
   │            │              │ (2 solid green)                │
   │            │              │               │                │
   │            │              │◄──────────────┼────────────────│
   │            │              │ {r3, "notify", 3/3}            │
   │            │◄─────────────│ LED: [●●●◯◯◯◯◯◯◯◯◯]            │
   │            │◄─────────────│ TTS: "3 of 3: send notify?"    │
   │            │              │               │                │
   │ [approve]  │              │               │                │
   │───────────►│─────────────►│───────────────┼───────────────►│
   │            │◄─────────────│ LED: [●●●] flash → off         │
   │            │              │               │                │
   │            │              │◄──────────────┼────────────────│
   │            │              │ response: "Deployed!"          │
   │            │◄─────────────│ TTS: "Deployed successfully"   │
   │            │              │               │                │
```

### Scenario 5: Error (MQTT Timeout)

```
┌──────┐   ┌─────────┐   ┌────────────┐   ┌──────────┐   ┌─────────────┐
│ User │   │Voice PE │   │    HA      │   │  MQTT    │   │ClaudeCodeUI │
└──┬───┘   └────┬────┘   └─────┬──────┘   └────┬─────┘   └──────┬──────┘
   │            │              │               │                │
   │ "check status"            │               │                │
   │───────────►│──────────────►               │                │
   │            │              │───────────────►      ╳         │
   │            │              │ claude/command│  (broker down) │
   │            │              │               │                │
   │            │              │ ─── 10 second timeout ───      │
   │            │              │               │                │
   │            │              │ MQTT publish failed            │
   │            │              │ state: ERROR  │                │
   │            │◄─────────────│ LED: red      │                │
   │            │◄─────────────│ TTS: "MQTT publish to claude   │
   │            │              │  request timed out after 10    │
   │            │              │  seconds."    │                │
   │            │              │ state: IDLE   │                │
   │            │◄─────────────│ LED: off      │                │
   │            │              │               │                │
```

### Scenario 6: Multiple Choice (Dial Selection)

```
┌──────┐   ┌─────────┐   ┌────────────┐   ┌──────────┐   ┌─────────────┐
│ User │   │Voice PE │   │    HA      │   │  MQTT    │   │ClaudeCodeUI │
└──┬───┘   └────┬────┘   └─────┬──────┘   └────┬─────┘   └──────┬──────┘
   │            │              │               │                │
   │ "restart a service"       │               │                │
   │───────────►│──────────────►──────────────►│───────────────►│
   │            │              │               │                │
   │            │              │◄──────────────┼────────────────│
   │            │              │ {type:"choice",                │
   │            │              │  question:"Which service?",    │
   │            │              │  options:["nginx","postgres",  │
   │            │              │           "redis"],            │
   │            │              │  requestId:"ch1"}              │
   │            │              │               │                │
   │            │              │ state: MULTIPLE_CHOICE         │
   │            │              │ store options, selected=1      │
   │            │◄─────────────│ LED: [████    ████    ████]    │
   │            │              │ (3 segments, #1 bright)        │
   │            │◄─────────────│ TTS: "Which service? 1 nginx,  │
   │            │              │       2 postgres, 3 redis"     │
   │            │              │               │                │
   │ [rotate CW]│              │               │                │
   │───────────►│─────────────►│ selected = 2  │                │
   │            │◄─────────────│ LED: segment 2 bright          │
   │            │◄─────────────│ TTS: "postgres"                │
   │            │              │               │                │
   │ [rotate CW]│              │               │                │
   │───────────►│─────────────►│ selected = 3  │                │
   │            │◄─────────────│ LED: segment 3 bright          │
   │            │◄─────────────│ TTS: "redis"  │                │
   │            │              │               │                │
   │ [press btn]│              │               │                │
   │───────────►│─────────────►│               │                │
   │            │              │ state: WAITING                 │
   │            │◄─────────────│ LED: orange   │                │
   │            │◄─────────────│ TTS: "Restart redis?"          │
   │            │              │               │                │
   │ [approve]  │              │               │                │
   │───────────►│─────────────►│───────────────┼───────────────►│
   │            │              │ {type:"choice", selectedOption:3}
   │            │◄─────────────│ LED: blue     │ (executes...)  │
   │            │              │◄──────────────┼────────────────│
   │            │              │ {text:"Redis restarted"}       │
   │            │◄─────────────│ TTS: "Redis restarted", LED:off│
   │            │              │               │                │
```

### Scenario 6b: Multiple Choice (Voice Selection)

```
┌──────┐   ┌─────────┐   ┌────────────┐   ┌──────────┐   ┌─────────────┐
│ User │   │Voice PE │   │    HA      │   │  MQTT    │   │ClaudeCodeUI │
└──┬───┘   └────┬────┘   └─────┬──────┘   └────┬─────┘   └──────┬──────┘
   │            │              │               │                │
   │  ... (choice prompt arrives, LED segments, TTS options) ...│
   │            │              │ state: MULTIPLE_CHOICE         │
   │            │              │               │                │
   │ "postgres" │              │               │                │
   │───────────►│ STT:"postgres"               │                │
   │            │─────────────►│               │                │
   │            │              │ intent: claude_select          │
   │            │              │ match "postgres" → option 2    │
   │            │              │ state: WAITING                 │
   │            │◄─────────────│ LED: orange   │                │
   │            │◄─────────────│ TTS: "Restart postgres?"       │
   │            │              │               │                │
   │            │  ... (approval flow continues) ...            │
   │            │              │               │                │
```

### Scenario 7: Resume Previous Conversation (V2)

```
┌──────┐   ┌─────────┐   ┌────────────┐   ┌──────────┐   ┌─────────────┐
│ User │   │Voice PE │   │    HA      │   │  MQTT    │   │ClaudeCodeUI │
└──┬───┘   └────┬────┘   └─────┬──────┘   └────┬─────┘   └──────┬──────┘
   │            │              │               │                │
   │            │              │ (context timer expired,        │
   │            │              │  LED ring empty)               │
   │            │              │               │                │
   │ "Hey Nabu, ask Claude to resume"          │                │
   │───────────►│ STT: "ask claude to resume"  │                │
   │            │─────────────►│               │                │
   │            │              │ intent: claude_resume          │
   │            │              │───────────────┼───────────────►│
   │            │              │ {message:"resume", resume:true}│
   │            │◄─────────────│ LED: blue     │                │
   │            │              │               │ (loads last    │
   │            │              │               │  conversation) │
   │            │              │◄──────────────┼────────────────│
   │            │              │ {text:"Resuming. We were       │
   │            │              │  discussing server status.",   │
   │            │              │  session_id:"restored-abc"}    │
   │            │              │               │                │
   │            │              │ restore context color          │
   │            │◄─────────────│ LED: context ring (gray)       │
   │            │◄─────────────│ TTS: "Resuming. We were        │
   │            │              │  discussing server status."    │
   │            │              │               │                │
   │ "which has the most pods?"│               │                │
   │───────────►│──────────────►──────────────►│───────────────►│
   │            │              │               │ (uses restored │
   │            │              │               │  context)      │
   │            │              │◄──────────────┼────────────────│
   │            │              │ {text:"Node 2 has 47 pods"}    │
   │            │◄─────────────│ TTS: "Node 2 has 47 pods"      │
   │            │              │               │                │
```

### Scenario 8: Cancel During Execution (V2)

```
┌──────┐   ┌─────────┐   ┌────────────┐   ┌──────────┐   ┌─────────────┐   ┌───────────┐
│ User │   │Voice PE │   │    HA      │   │  MQTT    │   │ClaudeCodeUI │   │  Shell    │
└──┬───┘   └────┬────┘   └─────┬──────┘   └────┬─────┘   └──────┬──────┘   └─────┬─────┘
   │            │              │               │                │                │
   │  ... (user approved, now executing long-running command) ..│                │
   │            │              │ state: EXECUTING               │                │
   │            │◄─────────────│ LED: blue     │                │ kubectl logs   │
   │            │              │               │                │ --follow       │
   │            │              │               │                │───────────────►│
   │            │              │               │                │ (streaming...) │
   │            │              │               │                │◄───────────────│
   │            │              │               │                │                │
   │ "stop" or [long press]    │               │                │                │
   │───────────►│─────────────►│               │                │                │
   │            │              │ intent: claude_cancel          │                │
   │            │              │───────────────┼───────────────►│                │
   │            │              │ {type:"cancel"}                │                │
   │            │              │               │                │ SIGINT         │
   │            │              │               │                │───────────────►│
   │            │              │               │                │◄───────────────│
   │            │              │               │                │ (terminated)   │
   │            │              │◄──────────────┼────────────────│                │
   │            │              │ {type:"cancelled",             │                │
   │            │              │  text:"Command stopped"}       │                │
   │            │              │ state: IDLE   │                │                │
   │            │◄─────────────│ LED: red(1s) → off             │                │
   │            │◄─────────────│ TTS: "Stopping"                │                │
   │            │              │               │                │                │
```

---

## File Structure

```
scripts/claudecodeui/voice-pe/
├── APPROVAL-UX-SCENARIOS.md      # UX requirements
├── ARCHITECTURE.md               # This document
│
├── ha/
│   └── claude_voice_pe.yaml      # HA package (single file)
│       ├── input_select          # State machine
│       ├── input_text/number     # Helpers
│       ├── timer                 # Timers
│       ├── script                # LED, Voice, Transition
│       └── automation            # Event router, MQTT handlers
│
├── claudecodeui/
│   ├── voice-pe-handler.ts       # MQTT ↔ Claude bridge
│   ├── voice-pe-protocol.ts      # TypeScript types
│   └── voice-pe-conversation.ts  # Context manager
│
└── deploy.sh                     # Deploy HA package
```

---

## Why This Architecture

### Voice PE stays untouched
- No firmware modifications
- Updates won't break our code
- Use standard HA services

### HA owns the state
- Single source of truth
- Easy to debug (HA logs)
- Version controllable (YAML)
- Testable with HA dev tools

### Separation of concerns
- Voice PE: Hardware I/O
- HA: State + UI logic
- ClaudeCodeUI: Claude bridge

### DRY implementation
- LED colors defined once
- Voice templates defined once
- Transitions defined once
- Reused across all scenarios

---

## Implementation Phases

### Phase 0: Feasibility Tests ✅ COMPLETE

**Status**: All core data paths verified working (2025-12-17).

**What We Tested:**

```
Voice PE → HA → ClaudeCodeUI → Claude Code → Approval Request
    │                                              │
    │         ← claude/approval-request ←──────────┘
    │
    └──► HA stores requestId → Dial CW/CCW → MQTT Response
                                              │
                                              ▼
                               ClaudeCodeUI receives approval
                               Claude executes command
                               Response speaks on Voice PE
```

**Test Scripts Created:**

```bash
scripts/claudecodeui/voice-pe/
├── 00-test-mqtt-flow.sh          # ✅ Verify MQTT pub/sub
├── clean-trace-test.sh           # ✅ Single command → single request verification
├── diagnose-approval-flow.sh     # ✅ Trace requestId through system
├── trace-approval-requests.sh    # ✅ Monitor approval-request topic
│
├── test-mqtt.sh (in claudecodeui repo)  # ✅ Full E2E test with --test flag
└── run-local.sh (in claudecodeui repo)  # ✅ Local dev with --test flag
```

**Key Verification Results:**

```bash
# ONE command produces ONE approval-request
$ ./clean-trace-test.sh
=== Approval-requests captured ===
Count: 1
98f6646f-6bc4-497d-ab18-92a788e68deb

# RequestId matches stored value
$ ./diagnose-approval-flow.sh
stored_request_id: "98f6646f-6bc4-497d-ab18-92a788e68deb"
✓ RequestId matches!
```

---

### Phase 1: Core Infrastructure (Day 1)

```
1. Deploy helper entities
   - input_select.claude_state
   - input_text: request_id, pending_command
   - timers: preview, approval

2. Deploy LED controller
   - Modes: off, solid (full ring)
   - Colors: orange, green, red, blue, lt_green, lt_red

3. Deploy voice controller
   - Basic templates: asking_claude, approval_prompt, cancelled

4. Test manually via HA Developer Tools
```

### Phase 2: Event System (Day 2)

```
1. Deploy event router automation
   - Dial CW/CCW detection
   - Button press types

2. Deploy transition handler
   - IDLE → THINKING → WAITING flow
   - WAITING → PREVIEW_* flow

3. Deploy timer handlers
   - Preview timeout
   - Approval timeout + warning

4. Test dial/button → state transitions
```

### Phase 3: MQTT Integration (Day 3)

```
1. Deploy approval executor script
   - MQTT publish
   - LED + voice feedback

2. ClaudeCodeUI: Basic MQTT handler
   - Subscribe to claude/request
   - Publish to claude/response

3. Test: Voice request → ClaudeCodeUI → Response

4. Test: Approval → MQTT → ClaudeCodeUI
```

### Phase 4: Full Scenarios (Day 4-5)

```
1. Simple question (Scenario 1)
2. Binary approval (Scenario 2)
3. Multiple approvals (Scenario 3)
4. Error handling (Scenario 5)
5. Multiple choice (Scenario 6)
6. Context/follow-up (Scenario 4)
```

---

## Testing Strategy

### Parallel Testing (Local vs K8s)

**CRITICAL**: Use topic isolation to test locally without affecting production.

```bash
# LOCAL DEVELOPMENT (uses test/ prefix - isolated)
cd /Users/10381054/code/claudecodeui
./scripts/run-local.sh --test       # Subscribes to test/claude/*
./scripts/test-mqtt.sh --test       # Publishes to test/claude/*

# PRODUCTION (no prefix)
# K8s pod subscribes to claude/command
./scripts/test-mqtt.sh              # Tests prod (no --test flag)
```

**Before testing production**: Verify local container is stopped.
```bash
docker stop claudecodeui-local || true
```

### Unit Tests (HA Developer Tools)

```yaml
# Test state transition
service: script.claude_transition
data:
  event: dial_cw
# Verify: input_select.claude_state changes

# Test LED color
service: script.claude_led
data:
  mode: solid
  color: orange
# Verify: LED ring lights up orange

# Test voice
service: script.claude_voice
data:
  message: approval_prompt
  command: "kubectl get nodes"
# Verify: TTS speaks "Run kubectl get nodes?"
```

### Integration Tests (MQTT)

```bash
# Simulate ClaudeCodeUI approval request
mosquitto_pub -h homeassistant.maas -t "claude/approval-request" \
  -m '{"requestId":"test-123","toolName":"Bash","input":{"command":"kubectl get pods"}}'

# Monitor approval response
mosquitto_sub -h homeassistant.maas -t "claude/approval-response"

# Then: rotate dial CW, press button
# Verify: MQTT receives {"requestId":"test-123","approved":true}
```

### E2E Scenario Tests

Each scenario from `APPROVAL-UX-SCENARIOS.md`:

| Scenario | Test Method |
|----------|-------------|
| Simple Question | Voice request → verify TTS response |
| Binary Approval | Voice request → dial → button → verify MQTT |
| Preview Timeout | dial → wait 10s → verify return to orange |
| Approval Timeout | wait 15s → verify "Never mind" + IDLE |
| Multiple Choice | dial through options → verify voice announces each |
| Error | Disconnect MQTT → verify error TTS |

### Verified Test Commands

```bash
# Check requestId is stored correctly
scripts/claudecodeui/voice-pe/diagnose-approval-flow.sh

# Verify single request (no duplicates)
scripts/claudecodeui/voice-pe/clean-trace-test.sh

# List HA automations
scripts/haos/list-automations.sh claude

# Get automation config
scripts/haos/get-automation-config.sh <automation_id>
```

---

## Debugging

### HA Logs

```bash
# Real-time automation traces
ssh root@chief-horse.maas "tail -f /config/home-assistant.log | grep -E 'claude|transition|led|voice'"

# Check state
curl -H "Authorization: Bearer $HA_TOKEN" http://homeassistant.maas:8123/api/states/input_select.claude_state
```

### MQTT

```bash
# Monitor all Claude topics
mosquitto_sub -h homeassistant.maas -t "claude/#" -v

# Check last message
mosquitto_sub -h homeassistant.maas -t "claude/response" -C 1
```

### Voice PE Events

```yaml
# In HA Developer Tools > Events
# Listen to: esphome.voice_pe_dial, esphome.voice_pe_button
```

---

## References

- [Voice PE GitHub](https://github.com/esphome/home-assistant-voice-pe)
- [Voice PE DeepWiki](https://deepwiki.com/esphome/home-assistant-voice-pe)
- [HA FSM Sensor](https://github.com/edalquist/ha_state_machine) (optional)
- Scenarios: `APPROVAL-UX-SCENARIOS.md`

---

# System Architecture Views

*Standard architectural diagrams for the Voice PE + Claude integration*

---

## C4 Level 1: System Context

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SYSTEM CONTEXT                                     │
│                                                                              │
│                              ┌─────────┐                                    │
│                              │  User   │                                    │
│                              │(Person) │                                    │
│                              └────┬────┘                                    │
│                                   │ Voice                                   │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                       │   │
│  │                    Claude Voice Assistant                            │   │
│  │                       [Software System]                              │   │
│  │                                                                       │   │
│  │   Accepts voice commands, gets AI responses, speaks answers          │   │
│  │                                                                       │   │
│  └───────────────────────────────┬───────────────────────────────────────┘   │
│                                   │ API                                     │
│                                   ▼                                         │
│                         ┌─────────────────┐                                 │
│                         │   Claude API    │                                 │
│                         │ [External System]│                                │
│                         └─────────────────┘                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## C4 Level 2: Container Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CONTAINER DIAGRAM                                   │
│                                                                              │
│    ┌──────────────┐                                                         │
│    │     User     │                                                         │
│    └──────┬───────┘                                                         │
│           │ Voice / Touch                                                   │
│           ▼                                                                 │
│    ┌──────────────┐         ┌──────────────┐         ┌──────────────┐      │
│    │   Voice PE   │ Events  │     Home     │  MQTT   │ ClaudeCodeUI │      │
│    │  [Device]    │────────►│  Assistant   │◄───────►│ [Container]  │      │
│    │              │◄────────│ [Container]  │         │              │      │
│    │ ESPHome      │ Services│              │         │ Node.js      │      │
│    │ Wake word    │         │ Automations  │         │ Claude SDK   │      │
│    │ STT/TTS      │         │ State machine│         │ MQTT Bridge  │      │
│    │ LED/Button   │         │ MQTT client  │         │              │      │
│    └──────────────┘         └──────────────┘         └──────┬───────┘      │
│                                                              │              │
│                                                              │ HTTPS        │
│                                                              ▼              │
│                                                       ┌──────────────┐      │
│                                                       │  Claude API  │      │
│                                                       │  [External]  │      │
│                                                       └──────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## C4 Level 3: Component Diagram (Home Assistant)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HOME ASSISTANT - COMPONENTS                               │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         AUTOMATIONS                                  │   │
│  │                                                                       │   │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────┐  │   │
│  │  │ claude_send_      │  │ claude_speak_     │  │ claude_handle_  │  │   │
│  │  │ request           │  │ response          │  │ interrupt       │  │   │
│  │  │                   │  │                   │  │                 │  │   │
│  │  │ Intent trigger    │  │ MQTT trigger      │  │ Button/Dial     │  │   │
│  │  │ → Set state       │  │ → Set state       │  │ trigger         │  │   │
│  │  │ → LED blue        │  │ → LED off         │  │ → Beep/Cancel   │  │   │
│  │  │ → Voice prompt    │  │ → Voice answer    │  │                 │  │   │
│  │  │ → MQTT publish    │  │                   │  │                 │  │   │
│  │  └─────────┬─────────┘  └─────────┬─────────┘  └────────┬────────┘  │   │
│  │            │                      │                      │           │   │
│  └────────────┼──────────────────────┼──────────────────────┼───────────┘   │
│               │                      │                      │               │
│               ▼                      ▼                      ▼               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          HELPER ENTITIES                             │   │
│  │                                                                       │   │
│  │  input_select.claude_state     [IDLE | THINKING | WAITING | ...]    │   │
│  │  input_text.claude_approval_request_id                              │   │
│  │                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          INTEGRATIONS                                │   │
│  │                                                                       │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │   │
│  │  │    MQTT     │    │   ESPHome   │    │    Piper    │              │   │
│  │  │             │    │             │    │    (TTS)    │              │   │
│  │  │ Pub/Sub to  │    │ Voice PE    │    │             │              │   │
│  │  │ ClaudeCodeUI│    │ events/svcs │    │ Text→Speech │              │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘              │   │
│  │                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Deployment View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEPLOYMENT VIEW                                    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Physical: Kitchen Counter                                            │   │
│  │                                                                       │   │
│  │   ┌─────────────────────────────┐                                    │   │
│  │   │ Voice PE                    │                                    │   │
│  │   │ [ESP32-S3 Device]           │                                    │   │
│  │   │                             │                                    │   │
│  │   │ • ESPHome firmware          │                                    │   │
│  │   │ • 192.168.86.245 (WiFi)     │                                    │   │
│  │   └──────────────┬──────────────┘                                    │   │
│  │                  │ WiFi (Google Mesh)                                │   │
│  └──────────────────┼──────────────────────────────────────────────────┘   │
│                     │                                                       │
│                     ▼                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Proxmox Host: chief-horse.maas (192.168.4.19)                       │   │
│  │                                                                       │   │
│  │   ┌─────────────────────────────┐                                    │   │
│  │   │ VM 116: Home Assistant OS   │                                    │   │
│  │   │ [QEMU/KVM]                  │                                    │   │
│  │   │                             │                                    │   │
│  │   │ • homeassistant.maas        │                                    │   │
│  │   │ • 192.168.4.240:8123 (API)  │                                    │   │
│  │   │ • :1883 (MQTT broker)       │                                    │   │
│  │   │                             │                                    │   │
│  │   │ Add-ons:                    │                                    │   │
│  │   │ • Mosquitto MQTT            │                                    │   │
│  │   │ • Piper TTS                 │                                    │   │
│  │   │ • Whisper STT               │                                    │   │
│  │   │ • ESPHome Dashboard         │                                    │   │
│  │   └─────────────────────────────┘                                    │   │
│  │                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                     │                                                       │
│                     │ MQTT :1883                                           │
│                     ▼                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Proxmox Host: still-fawn.maas                                        │   │
│  │                                                                       │   │
│  │   ┌─────────────────────────────┐                                    │   │
│  │   │ VM 108: K3s Node            │                                    │   │
│  │   │ [QEMU/KVM]                  │                                    │   │
│  │   │                             │                                    │   │
│  │   │ Namespace: claudecodeui     │                                    │   │
│  │   │ ┌─────────────────────────┐ │                                    │   │
│  │   │ │ Pod: claudecodeui-blue  │ │                                    │   │
│  │   │ │                         │ │                                    │   │
│  │   │ │ • Node.js server        │ │                                    │   │
│  │   │ │ • Claude SDK            │ │                                    │   │
│  │   │ │ • MQTT Bridge           │ │                                    │   │
│  │   │ └─────────────────────────┘ │                                    │   │
│  │   └─────────────────────────────┘                                    │   │
│  │                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                     │                                                       │
│                     │ HTTPS                                                │
│                     ▼                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ External: api.anthropic.com                                          │   │
│  │                                                                       │   │
│  │   Claude API                                                         │   │
│  │                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Network View (with socat proxy)

**CRITICAL**: Voice PE and HAOS are on different networks that cannot route directly.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              NETWORK VIEW                                        │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    GOOGLE WIFI (192.168.86.0/24)                           │  │
│  │                                                                             │  │
│  │     ┌─────────────┐                      ┌─────────────┐                   │  │
│  │     │  Voice PE   │        WiFi          │ Google WiFi │                   │  │
│  │     │ .86.245     │◄────────────────────►│   Router    │                   │  │
│  │     │             │                      │   .86.1     │                   │  │
│  │     └──────┬──────┘                      └──────┬──────┘                   │  │
│  │            │                                    │                           │  │
│  │            │ ESPHome API :6053                  │                           │  │
│  │            │ (TTS streaming)                    │                           │  │
│  │            │                                    │                           │  │
│  └────────────┼────────────────────────────────────┼───────────────────────────┘  │
│               │                                    │                              │
│               │                                    │ Uplink                       │
│               │                                    ▼                              │
│  ┌────────────┼──────────────────────────────────────────────────────────────┐   │
│  │            │           ISP NETWORK (192.168.1.0/24)                        │   │
│  │            │                                                               │   │
│  │            │     ┌─────────────┐          ┌─────────────────────┐         │   │
│  │            │     │ ISP Router  │          │    pve (Proxmox)    │         │   │
│  │            │     │  .1.254     │◄────────►│    .1.122           │         │   │
│  │            │     └─────────────┘          │                     │         │   │
│  │            │                              │  ┌───────────────┐  │         │   │
│  │            │                              │  │  socat proxy  │  │         │   │
│  │            │                              │  │  :8123        │  │         │   │
│  │            │ HTTP                         │  │  ↓ forward    │  │         │   │
│  │            └─────────────────────────────►│  │  192.168.4.240│  │         │   │
│  │              TTS audio fetch              │  └───────────────┘  │         │   │
│  │              (via proxy)                  │                     │         │   │
│  │                                           └──────────┬──────────┘         │   │
│  └──────────────────────────────────────────────────────┼────────────────────┘   │
│                                                         │                        │
│                                                         │ .4.122                 │
│                                                         ▼                        │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                      HOMELAB NETWORK (192.168.4.0/24)                     │   │
│  │                                                                           │   │
│  │    ┌─────────────┐        ┌─────────────┐        ┌─────────────┐         │   │
│  │    │chief-horse  │        │  HAOS VM    │        │ still-fawn  │         │   │
│  │    │  .4.19      │        │  116        │        │  K3s VM 108 │         │   │
│  │    │             │        │  .4.240     │        │             │         │   │
│  │    │ vmbr2 ──────┼───────►│  :8123 API  │        │ ClaudeCodeUI│         │   │
│  │    │ (86.22)     │        │  :1883 MQTT │◄──────►│  Pod        │         │   │
│  │    └─────────────┘        └─────────────┘        └─────────────┘         │   │
│  │          │                                                                │   │
│  │          │ USB Ethernet + Flint 3 bridge                                 │   │
│  │          │ (ESPHome API path back to Voice PE)                           │   │
│  │          ▼                                                                │   │
│  │    ┌──────────────────────────────────────────────────────────────────┐  │   │
│  │    │  PATH 2: HA → Voice PE (ESPHome API :6053)                       │  │   │
│  │    │  chief-horse vmbr2 (86.22) → Flint 3 → Google WiFi → Voice PE    │  │   │
│  │    └──────────────────────────────────────────────────────────────────┘  │   │
│  │                                                                           │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Two Communication Paths (Critical!)

| Path | Direction | Purpose | Route |
|------|-----------|---------|-------|
| **PATH 1** | Voice PE → HAOS | HTTP API, TTS audio fetch | 86.245 → Google WiFi → ISP → **socat on pve** → 4.240:8123 |
| **PATH 2** | HAOS → Voice PE | ESPHome API, TTS streaming | 4.240 → chief-horse vmbr2 (86.22) → Flint 3 → 86.245:6053 |

### socat Proxy Configuration

```ini
# /etc/systemd/system/ha-proxy.service on pve
[Service]
ExecStart=/usr/bin/socat TCP-LISTEN:8123,bind=192.168.1.122,reuseaddr,fork TCP:192.168.4.240:8123
```

**HA must advertise `http://192.168.1.122:8123`** as its internal URL so Voice PE fetches media from the reachable proxy.

---

## CI/CD Pipeline View

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CI/CD PIPELINE                                      │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                         DEVELOPMENT                                        │  │
│  │                                                                             │  │
│  │    ┌─────────────┐        ┌─────────────┐        ┌─────────────┐          │  │
│  │    │   macOS     │  git   │   GitHub    │        │   GitHub    │          │  │
│  │    │   Dev       │───────►│   Repo      │───────►│   Actions   │          │  │
│  │    │             │  push  │ homeiac/    │ trigger│             │          │  │
│  │    │ Claude Code │        │ claudecodeui│        │ • build     │          │  │
│  │    └─────────────┘        └─────────────┘        │ • test      │          │  │
│  │                                                   │ • docker    │          │  │
│  │                                                   └──────┬──────┘          │  │
│  └──────────────────────────────────────────────────────────┼────────────────┘  │
│                                                              │                   │
│                                                              │ push image        │
│                                                              ▼                   │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                         REGISTRY                                           │  │
│  │                                                                             │  │
│  │                      ┌─────────────────────┐                               │  │
│  │                      │  ghcr.io/homeiac/   │                               │  │
│  │                      │  claudecodeui:main  │                               │  │
│  │                      └──────────┬──────────┘                               │  │
│  │                                 │                                           │  │
│  └─────────────────────────────────┼───────────────────────────────────────────┘  │
│                                    │                                              │
│                                    │ Flux ImagePolicy                             │
│                                    ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                         GITOPS (home repo)                                 │  │
│  │                                                                             │  │
│  │    ┌─────────────────────────────────────────────────────────────────┐    │  │
│  │    │  gitops/clusters/homelab/apps/claudecodeui/                      │    │  │
│  │    │                                                                   │    │  │
│  │    │  ├── blue/                                                        │    │  │
│  │    │  │   ├── deployment-blue.yaml  ◄── image: ghcr.io/.../main       │    │  │
│  │    │  │   ├── service.yaml                                             │    │  │
│  │    │  │   └── pvc.yaml                                                 │    │  │
│  │    │  └── kustomization.yaml                                           │    │  │
│  │    └─────────────────────────────────────────────────────────────────┘    │  │
│  │                                 │                                           │  │
│  └─────────────────────────────────┼───────────────────────────────────────────┘  │
│                                    │                                              │
│                                    │ Flux reconcile                               │
│                                    ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                         K3S CLUSTER                                        │  │
│  │                                                                             │  │
│  │    ┌─────────────────────────────────────────────────────────────────┐    │  │
│  │    │  Namespace: claudecodeui                                         │    │  │
│  │    │                                                                   │    │  │
│  │    │    ┌─────────────────┐     ┌─────────────────┐                   │    │  │
│  │    │    │ Flux            │     │ claudecodeui-   │                   │    │  │
│  │    │    │ source-controller────►│ blue            │                   │    │  │
│  │    │    │ kustomize-ctrl  │     │ (Deployment)    │                   │    │  │
│  │    │    └─────────────────┘     └─────────────────┘                   │    │  │
│  │    │                                                                   │    │  │
│  │    └─────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                             │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## ESPHome Firmware Update View

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         ESPHOME FIRMWARE UPDATES                                 │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    INITIAL FLASH (USB)                                     │  │
│  │                                                                             │  │
│  │    ┌─────────────┐        ┌─────────────┐        ┌─────────────┐          │  │
│  │    │   macOS     │  USB   │  Voice PE   │        │   HAOS      │          │  │
│  │    │             │◄──────►│  (ESP32-S3) │        │  ESPHome    │          │  │
│  │    │ esptool.py  │        │             │        │  Dashboard  │          │  │
│  │    │ or Docker   │        │ Boot mode:  │        │  (Add-on)   │          │  │
│  │    │             │        │ Hold button │        │             │          │  │
│  │    └──────┬──────┘        │ + plug USB  │        └─────────────┘          │  │
│  │           │               └─────────────┘                                  │  │
│  │           │                                                                │  │
│  │           │ esphome run voice-pe.yaml --device /dev/cu.usbmodem*          │  │
│  │           │                                                                │  │
│  └───────────┼────────────────────────────────────────────────────────────────┘  │
│              │                                                                   │
│              │ After initial flash, device connects to WiFi                      │
│              ▼                                                                   │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    OTA UPDATES (WiFi)                                      │  │
│  │                                                                             │  │
│  │    ┌─────────────────────────────────────────────────────────────────┐    │  │
│  │    │                    HAOS VM 116                                   │    │  │
│  │    │                                                                   │    │  │
│  │    │    ┌─────────────────┐                                           │    │  │
│  │    │    │ ESPHome Add-on  │                                           │    │  │
│  │    │    │                 │                                           │    │  │
│  │    │    │ • Dashboard UI  │                                           │    │  │
│  │    │    │ • YAML editor   │                                           │    │  │
│  │    │    │ • Compile       │                                           │    │  │
│  │    │    │ • OTA push      │                                           │    │  │
│  │    │    └────────┬────────┘                                           │    │  │
│  │    │             │                                                     │    │  │
│  │    └─────────────┼─────────────────────────────────────────────────────┘    │  │
│  │                  │                                                          │  │
│  │                  │ ESPHome API :6053 (OTA upload)                           │  │
│  │                  │ via chief-horse vmbr2 → Flint 3 → Google WiFi            │  │
│  │                  ▼                                                          │  │
│  │    ┌─────────────────────────────────────────────────────────────────┐    │  │
│  │    │                    Voice PE                                      │    │  │
│  │    │                    192.168.86.245                                │    │  │
│  │    │                                                                   │    │  │
│  │    │    Receives OTA update, reboots with new firmware                │    │  │
│  │    │                                                                   │    │  │
│  │    └─────────────────────────────────────────────────────────────────┘    │  │
│  │                                                                             │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## HAOS Add-ons View

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         HAOS ADD-ONS (VM 116)                                    │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    Home Assistant OS                                       │  │
│  │                    chief-horse.maas / 192.168.4.240                        │  │
│  │                                                                             │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │  │
│  │  │                         CORE                                         │  │  │
│  │  │                                                                       │  │  │
│  │  │    Home Assistant Core        Supervisor         DNS                 │  │  │
│  │  │    :8123 (HTTP API)           (Add-on mgmt)      (internal)          │  │  │
│  │  │                                                                       │  │  │
│  │  └─────────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                             │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │  │
│  │  │                    VOICE PIPELINE ADD-ONS                            │  │  │
│  │  │                                                                       │  │  │
│  │  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                │  │  │
│  │  │  │   Whisper   │   │   Piper     │   │ openWakeWord│                │  │  │
│  │  │  │   (STT)     │   │   (TTS)     │   │  (optional) │                │  │  │
│  │  │  │             │   │             │   │              │                │  │  │
│  │  │  │ Wyoming     │   │ Wyoming     │   │ Wyoming      │                │  │  │
│  │  │  │ :10300      │   │ :10200      │   │ :10400       │                │  │  │
│  │  │  └──────┬──────┘   └──────┬──────┘   └──────────────┘                │  │  │
│  │  │         │                 │                                           │  │  │
│  │  │         │    Wyoming Protocol (audio streaming)                       │  │  │
│  │  │         │                 │                                           │  │  │
│  │  │         ▼                 ▼                                           │  │  │
│  │  │  ┌─────────────────────────────────────────────────────────────┐    │  │  │
│  │  │  │              Assist Pipeline                                 │    │  │  │
│  │  │  │              (HA Core integration)                           │    │  │  │
│  │  │  │                                                               │    │  │  │
│  │  │  │  Voice PE ──► Whisper STT ──► Intent ──► Piper TTS ──► Voice PE│  │  │  │
│  │  │  └─────────────────────────────────────────────────────────────┘    │  │  │
│  │  │                                                                       │  │  │
│  │  └─────────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                             │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │  │
│  │  │                    INFRASTRUCTURE ADD-ONS                            │  │  │
│  │  │                                                                       │  │  │
│  │  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                │  │  │
│  │  │  │  Mosquitto  │   │  ESPHome    │   │  File       │                │  │  │
│  │  │  │  (MQTT)     │   │  Dashboard  │   │  Editor     │                │  │  │
│  │  │  │             │   │             │   │             │                │  │  │
│  │  │  │ :1883       │   │ :6052 (UI)  │   │             │                │  │  │
│  │  │  │ (broker)    │   │             │   │             │                │  │  │
│  │  │  └──────┬──────┘   └─────────────┘   └─────────────┘                │  │  │
│  │  │         │                                                             │  │  │
│  │  │         │ MQTT pub/sub                                                │  │  │
│  │  │         ▼                                                             │  │  │
│  │  │  ┌──────────────────────────────────────────────────────┐            │  │  │
│  │  │  │  Claude Topics:                                       │            │  │  │
│  │  │  │  • claude/command         (Voice PE → ClaudeCodeUI)  │            │  │  │
│  │  │  │  • claude/home/response   (ClaudeCodeUI → HA)        │            │  │  │
│  │  │  │  • claude/approval-request  (ClaudeCodeUI → HA)      │            │  │  │
│  │  │  │  • claude/approval-response (HA → ClaudeCodeUI)      │            │  │  │
│  │  │  └──────────────────────────────────────────────────────┘            │  │  │
│  │  │                                                                       │  │  │
│  │  └─────────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                             │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Blue/Green Deployment View

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         BLUE/GREEN DEPLOYMENT                                    │
│                                                                                  │
│  PRODUCTION ENDPOINT (traffic switch)                                            │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                                                                             │  │
│  │  claude.app.homelab  ─────────────────────┐                                │  │
│  │  (Ingress - points to LIVE deployment)    │                                │  │
│  │                                           ▼                                │  │
│  │  MQTT topics: claude/*            ┌──────────────┐                         │  │
│  │  (prod traffic)                   │   ACTIVE     │                         │  │
│  │                                   │  (blue OR    │                         │  │
│  │                                   │   green)     │                         │  │
│  │                                   └──────────────┘                         │  │
│  │                                                                             │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  K3S NAMESPACE: claudecodeui                                                     │
│  ┌─────────────────────────────┐   ┌─────────────────────────────┐             │
│  │  claude-blue.app.homelab    │   │  claude-green.app.homelab   │             │
│  │  (direct access)            │   │  (direct access)            │             │
│  │                             │   │                             │             │
│  │  claudecodeui-blue          │   │  claudecodeui-green         │             │
│  │  replicas: 1                │   │  replicas: 1                │             │
│  │  image: :v1.2.0             │   │  image: :v1.3.0             │             │
│  │                             │   │                             │             │
│  │  ◄── LIVE                   │   │  ◄── STANDBY                │             │
│  │  Subscribes: claude/*       │   │  Subscribes: test/claude/*  │             │
│  │                             │   │                             │             │
│  └─────────────────────────────┘   └─────────────────────────────┘             │
│                                                                                  │
│  SWITCHOVER WORKFLOW:                                                            │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                                                                             │  │
│  │  1. Deploy v1.3.0 to GREEN (standby)                                       │  │
│  │  2. Validate via claude-green.app.homelab + test/claude/* topics           │  │
│  │  3. Update GREEN env: MQTT topics → claude/* (prod)                        │  │
│  │  4. Update Ingress: claude.app.homelab → green service                     │  │
│  │  5. Update BLUE env: MQTT topics → test/claude/* (standby)                 │  │
│  │  6. GREEN is now LIVE, BLUE is now STANDBY                                 │  │
│  │                                                                             │  │
│  │  Rollback = reverse steps 3-5 (switch Ingress + topics back)               │  │
│  │                                                                             │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ⚠️  CONSTRAINT: Only LIVE pod subscribes to claude/* at any time               │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Dev/Test Workflow

### Fast Local Development (~45s cycle)

```
┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐
│  Edit    │ ───► │  Build   │ ───► │  Run     │ ───► │  Test    │
│  code    │      │  local   │      │  --test  │      │  --test  │
└──────────┘      └──────────┘      └──────────┘      └──────────┘
     │                 │                 │                 │
     ▼                 ▼                 ▼                 ▼
vim/vscode      docker build       run-local.sh      test-mqtt.sh
                -t :local          --test            --test
                (~30s)             (~5s)             (~10s)

Topics: test/claude/*  ◄── ISOLATED FROM PROD
```

### Topic Isolation

| Environment | Topic Prefix | Use Case |
|-------------|--------------|----------|
| **Local dev** | `test/` | Fast iteration, won't touch K8s |
| **Standby pod** | `test/` | Pre-switchover validation |
| **Production** | (none) | Live traffic (LIVE pod only) |

### MQTT Flow for Blue/Green Testing

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    MQTT TOPIC FLOW - BLUE/GREEN                                  │
│                                                                                  │
│  BEFORE SWITCHOVER (Blue is LIVE)                                               │
│  ═══════════════════════════════════════════════════════════════════════════    │
│                                                                                  │
│  Voice PE / HA                    MQTT Broker                  ClaudeCodeUI     │
│       │                         (homeassistant.maas:1883)           │           │
│       │                                  │                          │           │
│       │   claude/command ───────────────►│──────────────────────────►│ BLUE     │
│       │◄──────────────────────────────────│◄── claude/home/response ─│ (LIVE)   │
│       │                                  │                          │           │
│       │                                  │                          │           │
│       │   test/claude/command ──────────►│──────────────────────────►│ GREEN    │
│       │   (manual test only)             │◄── test/claude/response ──│ (STANDBY)│
│       │                                  │                          │           │
│                                                                                  │
│  VALIDATION STEPS (before switchover)                                           │
│  ═══════════════════════════════════════════════════════════════════════════    │
│                                                                                  │
│  1. GREEN subscribes to: test/claude/*                                          │
│                                                                                  │
│  2. Test GREEN directly:                                                        │
│     $ ./scripts/test-mqtt.sh --test                                             │
│     → Publishes to test/claude/command                                          │
│     → GREEN responds on test/claude/home/response                               │
│     → Verify response is correct                                                │
│                                                                                  │
│  3. Test approval flow:                                                         │
│     $ ./scripts/test-mqtt.sh --test --approval                                  │
│     → Verify test/claude/approval-request received                              │
│     → Send test/claude/approval-response                                        │
│     → Verify execution completes                                                │
│                                                                                  │
│  SWITCHOVER (GitOps)                                                             │
│  ═══════════════════════════════════════════════════════════════════════════    │
│                                                                                  │
│  Step 1: Edit deployment-green.yaml - set prod topics                           │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  # gitops/clusters/homelab/apps/claudecodeui/green/deployment-green.yaml│   │
│  │  env:                                                                   │   │
│  │    - name: MQTT_COMMAND_TOPIC                                           │   │
│  │      value: "claude/command"           # was: test/claude/command       │   │
│  │    - name: MQTT_RESPONSE_TOPIC                                          │   │
│  │      value: "claude/home/response"     # was: test/claude/home/response │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  Step 2: Edit deployment-blue.yaml - set test topics (becomes standby)          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  # gitops/clusters/homelab/apps/claudecodeui/blue/deployment-blue.yaml  │   │
│  │  env:                                                                   │   │
│  │    - name: MQTT_COMMAND_TOPIC                                           │   │
│  │      value: "test/claude/command"      # was: claude/command            │   │
│  │    - name: MQTT_RESPONSE_TOPIC                                          │   │
│  │      value: "test/claude/home/response"# was: claude/home/response      │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  Step 3: Edit ingress.yaml - point to green service                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  # gitops/clusters/homelab/apps/claudecodeui/ingress.yaml               │   │
│  │  rules:                                                                 │   │
│  │    - host: claude.app.homelab                                           │   │
│  │      http:                                                              │   │
│  │        paths:                                                           │   │
│  │          - backend:                                                     │   │
│  │              service:                                                   │   │
│  │                name: claudecodeui-green  # was: claudecodeui-blue       │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  Step 4: Commit, push, Flux reconciles                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  git add gitops/clusters/homelab/apps/claudecodeui/                     │   │
│  │  git commit -m "chore: switch live to green"                            │   │
│  │  git push                                                               │   │
│  │  flux reconcile kustomization claudecodeui --with-source                │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  AFTER SWITCHOVER (Green is LIVE)                                               │
│  ═══════════════════════════════════════════════════════════════════════════    │
│                                                                                  │
│  Voice PE / HA                    MQTT Broker                  ClaudeCodeUI     │
│       │                                  │                          │           │
│       │   claude/command ───────────────►│──────────────────────────►│ GREEN    │
│       │◄──────────────────────────────────│◄── claude/home/response ─│ (LIVE)   │
│       │                                  │                          │           │
│       │   test/claude/command ──────────►│──────────────────────────►│ BLUE     │
│       │   (manual test only)             │◄── test/claude/response ──│ (STANDBY)│
│       │                                  │                          │           │
│                                                                                  │
│  ROLLBACK = Reverse Steps 1-3                                                   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Critical: Avoid Duplicate Subscriptions

⚠️ **Never have both pods subscribe to `claude/*` simultaneously**

During switchover, there's a brief moment where both might receive messages.
The MQTT bridge includes deduplication, but best practice:

1. Scale down STANDBY before changing its topics
2. Change topics
3. Scale back up

Or use MQTT client ID collision (same client ID = broker disconnects old client).

---

## MQTT Event Schema

### Topic Hierarchy

```
claude/
├── command                    # Voice PE → ClaudeCodeUI (user request)
├── home/
│   └── response               # ClaudeCodeUI → HA (all response types)
├── approval-request           # ClaudeCodeUI → HA (needs user decision)
└── approval-response          # HA → ClaudeCodeUI (user decision)

test/claude/...                # Same structure, isolated for dev
staging/claude/...             # Same structure, isolated for pre-prod
```

### Event: `claude/command`

**Direction**: Voice PE → HA → ClaudeCodeUI

```json
{
  "source": "voice_pe",
  "message": "what is the status of my k8s cluster",
  "session_id": "voice-pe-1702847123",
  "stream": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | string | ✓ | Origin device identifier |
| `message` | string | ✓ | User's natural language query |
| `session_id` | string | | Conversation continuity |
| `stream` | boolean | | true = streaming TTS |

### Event: `claude/home/response`

**Direction**: ClaudeCodeUI → HA

#### Type: `answer`

```json
{
  "type": "answer",
  "text": "All three nodes are healthy.",
  "session_id": "voice-pe-1702847123",
  "timestamp": 1702847125000
}
```

#### Type: `chunk` (streaming)

```json
{
  "type": "chunk",
  "content": {"data": {"type": "text", "text": "Checking"}},
  "session_id": "voice-pe-1702847123",
  "timestamp": 1702847124500
}
```

#### Type: `complete`

```json
{
  "type": "complete",
  "session_id": "voice-pe-1702847123",
  "duration_ms": 3420,
  "timestamp": 1702847126000
}
```

#### Type: `error`

```json
{
  "type": "error",
  "error": "Claude CLI not authenticated.",
  "session_id": "voice-pe-1702847123",
  "timestamp": 1702847124000
}
```

### Event: `claude/approval-request`

**Direction**: ClaudeCodeUI → HA

```json
{
  "requestId": "9f279968-9540-44a0-a498-450b262a6ea6",
  "toolName": "Bash",
  "input": {
    "command": "kubectl get nodes -o wide",
    "description": "List Kubernetes nodes"
  },
  "sessionId": "voice-pe-1702847123",
  "sourceDevice": "voice_pe",
  "timestamp": 1702847124000
}
```

### Event: `claude/approval-response`

**Direction**: HA → ClaudeCodeUI

#### Approved

```json
{
  "requestId": "9f279968-9540-44a0-a498-450b262a6ea6",
  "approved": true
}
```

#### Rejected

```json
{
  "requestId": "9f279968-9540-44a0-a498-450b262a6ea6",
  "approved": false,
  "reason": "user_reject"
}
```

---

## Script Organization (Proposed)

```
scripts/claudecodeui/voice-pe/
│
├── README.md                      # Index
│
├── tests/                         # Automated test suite
│   ├── run-all.sh                 # Test runner
│   ├── unit/                      # Single component
│   │   ├── test-mqtt-publish.sh
│   │   ├── test-led-service.sh
│   │   └── test-tts-service.sh
│   ├── integration/               # Two components
│   │   ├── test-approval-roundtrip.sh
│   │   └── test-dial-to-mqtt.sh
│   └── e2e/                       # Full workflow
│       └── test-scenario-*.sh
│
├── diagnostics/                   # Troubleshooting
│   ├── trace-mqtt.sh              # Live MQTT viewer
│   ├── trace-approval-flow.sh     # Follow requestId
│   ├── dump-ha-state.sh           # Snapshot entities
│   └── check-health.sh            # System health
│
├── deploy/                        # Deployment
│   ├── deploy-automations.sh
│   └── deploy-helpers.sh
│
├── utils/                         # Utilities
│   ├── backup-config.sh
│   ├── restore-config.sh
│   └── cleanup-old-automations.sh
│
└── archive/                       # Deprecated
```

---

## Observability

### Current (MVP)

| Layer | Implementation | Notes |
|-------|----------------|-------|
| **Correlation ID** | `requestId` in all messages | Already implemented |
| **Structured Logs** | JSON logs in ClaudeCodeUI | `kubectl logs` |
| **Live Tracing** | `mosquitto_sub -t "claude/#"` | Real-time |
| **HA Traces** | Automation traces in UI | Last 20 runs |

### Future Enhancements

| Enhancement | Effort | Value |
|-------------|--------|-------|
| MQTT trace topics (`claude/trace/*`) | 2h | Real-time debugging |
| Loki log aggregation | 4h | Persistent, searchable |
| Prometheus metrics | 4h | Dashboards, alerts |
| Grafana dashboard | 2h | Visualization |

---

## Protocols Summary

| Connection | Protocol | Port | Direction |
|------------|----------|------|-----------|
| Voice PE ↔ HAOS | ESPHome Native API | 6053 | Bidirectional |
| Voice PE ← HAOS | Media stream | dynamic | HAOS → Voice PE |
| Voice PE → HAOS | HTTP (via socat) | 8123 | Voice PE → pve → HAOS |
| HAOS ↔ ClaudeCodeUI | MQTT | 1883 | Bidirectional |
| ClaudeCodeUI → Claude | HTTPS | 443 | Outbound only |
