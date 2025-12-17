# Voice PE Claude Approval - Architecture

*Updated: 2025-12-17*

---

## Design Principles

1. **Voice PE = I/O only** - Events in, LED/TTS out
2. **HA = State machine** - Single source of truth
3. **ClaudeCodeUI = Bridge** - MQTT ↔ Claude Code
4. **No firmware mods** - Use Voice PE as-is
5. **DRY** - Define patterns/templates once, reuse everywhere

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
│                        STATE MACHINE OWNER                               │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     STATE MACHINE                                │   │
│  │  input_select.claude_state                                       │   │
│  │                                                                   │   │
│  │  IDLE ←──────────────────────────────────────────────────────┐  │   │
│  │    │                                                          │  │   │
│  │    ▼ (request_sent)                                           │  │   │
│  │  THINKING ──────────────────────────────────────────────────┐ │  │   │
│  │    │         │           │                                   │ │  │   │
│  │    │    (response)  (approval)  (choice)                     │ │  │   │
│  │    │         │           │           │                       │ │  │   │
│  │    │         ▼           ▼           ▼                       │ │  │   │
│  │    │       IDLE      WAITING    MULTIPLE_CHOICE              │ │  │   │
│  │    │                   │ │           │                       │ │  │   │
│  │    │          (dial_cw)│ │(dial_ccw) │                       │ │  │   │
│  │    │                   ▼ ▼           │                       │ │  │   │
│  │    │         PREVIEW_APPROVE         │                       │ │  │   │
│  │    │         PREVIEW_REJECT          │                       │ │  │   │
│  │    │                   │             │                       │ │  │   │
│  │    │            (confirm)            │                       │ │  │   │
│  │    │                   ▼             │                       │ │  │   │
│  │    │              EXECUTING ─────────┘                       │ │  │   │
│  │    │                   │                                     │ │  │   │
│  │    └───────────────────┴─────────────────────────────────────┘ │  │   │
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

### Phase 0: Feasibility Tests (Before Implementation)

Validate the existing infrastructure before building the state machine.

**Goal**: Prove the data path works end-to-end.

```
┌──────────┐    ┌─────────┐    ┌─────────────┐    ┌────────────┐
│ Voice PE │───►│   HA    │───►│ ClaudeCodeUI│───►│ Claude Code│
│   STT    │    │  MQTT   │    │   Bridge    │    │   (ask)    │
└──────────┘    └─────────┘    └─────────────┘    └────────────┘
                                     │
                                     ▼
                              claude/response
                              {type: "approval",
                               command: "kubectl..."}
                                     │
                                     ▼
                              ┌─────────────┐
                              │ Feasibility │
                              │ Test Script │
                              │ (auto-yes)  │
                              └─────────────┘
```

**Test Scripts:**

```bash
scripts/claudecodeui/voice-pe/
├── 00-test-mqtt-flow.sh          # Verify MQTT pub/sub works
├── 01-test-voice-to-mqtt.sh      # Voice PE → HA → MQTT
├── 02-test-auto-approve.sh       # Auto-approve read-only commands
└── 03-test-e2e-voice-approval.sh # Full voice → Claude → approval → response
```

**02-test-auto-approve.sh Logic:**

```bash
# Subscribe to claude/response, auto-approve read-only commands
mosquitto_sub -h homeassistant.maas -t "claude/response" | while read msg; do
  type=$(echo "$msg" | jq -r '.type')
  command=$(echo "$msg" | jq -r '.command // empty')
  requestId=$(echo "$msg" | jq -r '.requestId')

  if [[ "$type" == "approval" ]]; then
    # Auto-approve read-only operations
    if [[ "$command" =~ ^kubectl\ (get|describe|logs|top) ]] || \
       [[ "$command" =~ ^(cat|ls|head|tail|grep|find|which|echo|date) ]]; then
      echo "AUTO-APPROVE (read-only): $command"
      mosquitto_pub -h homeassistant.maas -t "claude/approval-response" \
        -m "{\"requestId\":\"$requestId\",\"type\":\"approved\"}"
    else
      echo "NEEDS MANUAL APPROVAL: $command"
    fi
  fi
done
```

**Test Procedure:**

```
1. Start ClaudeCodeUI locally: ./scripts/run-local.sh
2. Run auto-approve script: ./02-test-auto-approve.sh
3. Voice: "Hey Nabu, ask Claude to get me the home cluster status"
4. Verify:
   - ClaudeCodeUI receives request
   - Claude asks for approval (kubectl get nodes or similar)
   - Auto-approve script approves it
   - Claude executes and responds
   - Voice PE speaks the response
```

**Read-Only Command Patterns (auto-approve):**

| Pattern | Example |
|---------|---------|
| `kubectl get *` | kubectl get nodes, kubectl get pods -A |
| `kubectl describe *` | kubectl describe node still-fawn |
| `kubectl logs *` | kubectl logs -n frigate deployment/frigate |
| `kubectl top *` | kubectl top nodes |
| `cat`, `ls`, `head`, `tail` | cat /etc/hosts |
| `grep`, `find`, `which` | find . -name "*.yaml" |
| `echo`, `date`, `uptime` | date, uptime |

**NOT auto-approved (destructive):**

| Pattern | Example |
|---------|---------|
| `kubectl delete *` | kubectl delete pod ... |
| `kubectl apply *` | kubectl apply -f ... |
| `kubectl edit *` | kubectl edit deployment ... |
| `rm`, `mv`, `cp` | rm -rf ... |
| `systemctl *` | systemctl restart ... |
| `reboot`, `shutdown` | reboot |

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
mosquitto_pub -h homeassistant.maas -t "claude/response" \
  -m '{"type":"approval","requestId":"test-123","command":"kubectl get pods"}'

# Monitor approval response
mosquitto_sub -h homeassistant.maas -t "claude/approval-response"

# Then: rotate dial CW, press button
# Verify: MQTT receives {"requestId":"test-123","type":"approved"}
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
