# Voice PE Reminders with Ollama Setup Guide

## Overview

This guide documents the setup of voice-controlled reminders for Home Assistant Voice PE using local Ollama LLM for natural language time parsing and Voice PE for audio announcements.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         REMINDER FLOW                                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │   Voice PE   │───►│  HA Assist   │───►│   Ollama     │───►│  Todo List   │   │
│  │              │    │  (Whisper)   │    │  (llama3.2)  │    │  (Reminders) │   │
│  │ "Set reminder│    │              │    │              │    │              │   │
│  │  to X in Y"  │    │ Speech→Text  │    │ Parse Time   │    │ Store item   │   │
│  └──────────────┘    └──────────────┘    └──────────────┘    └──────┬───────┘   │
│                                                                      │           │
│                                                                      │           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐           │           │
│  │   Voice PE   │◄───│    Piper     │◄───│  Automation  │◄──────────┘           │
│  │              │    │    (TTS)     │    │ (every min)  │                       │
│  │  "Reminder:  │    │              │    │              │                       │
│  │   Take trash │    │ Text→Speech  │    │ Check due    │                       │
│  │   out"       │    │              │    │ items        │                       │
│  └──────────────┘    └──────────────┘    └──────────────┘                       │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Components

| Component | Purpose | Location |
|-----------|---------|----------|
| Voice PE | Voice input/output device | 192.168.86.245 (Google WiFi) |
| Whisper | Speech-to-text | HA Add-on (core_whisper) |
| Piper | Text-to-speech | HA Add-on (core_piper) |
| Ollama | LLM for time parsing | K3s cluster (192.168.4.81) |
| Local To-do | Reminder storage | HA Integration |
| Automations | Reminder logic | HA Automations |

## Prerequisites

- Home Assistant Voice PE connected and working
- Whisper and Piper add-ons installed
- Ollama integration configured (http://192.168.4.81)
- Full local assistant pipeline configured

## Setup Steps

### 1. Install Time & Date Integration

Required for the automation to know current time.

**Settings → Devices & Services → Add Integration → "Time & Date"**

This creates `sensor.date` and `sensor.time` entities.

### 2. Create Reminders Todo List

**Settings → Devices & Services → Add Integration → "Local To-do"**

Name the list: **Reminders**

This creates `todo.reminders` entity.

### 3. Import Reminder Blueprint

**Settings → Automations & Scenes → Blueprints → Import Blueprint**

URL: `https://gist.github.com/badnetmask/9a36cb18dcc093e3c6e31a8515abc7a2`

This is the Ollama-compatible fork of the voice reminders blueprint.

### 4. Create Blueprint Automation

From the imported blueprint, create an automation with:

| Setting | Value |
|---------|-------|
| Reminder time | `Remind me to {reminderDescription} at {reminderTime}` |
| HA Companion app notify service | `notify.my_phone` (can leave default) |
| Ollama Configuration | Select your Ollama integration |
| Response sentence text | (leave default) |
| Name of the reminder todo list | `todo.reminders` |

### 5. Create Relative Time Automation

The blueprint only handles "at [time]" patterns. For "in [duration]" support, create this automation via HA API or UI:

**Automation: Reminder Relative Time**

```yaml
alias: Reminder Relative Time
description: Handle remind me in X minutes/hours patterns
trigger:
  - platform: conversation
    command:
      - set a reminder to {reminderDescription} in {reminderTime}
      - set reminder to {reminderDescription} in {reminderTime}
      - create a reminder to {reminderDescription} in {reminderTime}
      - reminder to {reminderDescription} in {reminderTime}
action:
  - service: conversation.process
    data:
      agent_id: conversation.ollama_conversation
      text: >
        The current time is {{ now().strftime("%Y-%m-%d %H:%M:%S") }}.
        Calculate the datetime that is {{ trigger.slots.reminderTime }} from now.
        Return ONLY the result in format YYYY-MM-DD HH:MM:SS with exactly 19 characters.
        No other text.
    response_variable: response_from_ai
  - service: todo.add_item
    target:
      entity_id: todo.reminders
    data:
      item: "{{ trigger.slots.reminderDescription }}"
      due_datetime: "{{ response_from_ai.response.speech.plain.speech | trim }}"
  - set_conversation_response: >
      Reminder set: {{ trigger.slots.reminderDescription }} in {{ trigger.slots.reminderTime }}
mode: single
```

### 6. Create Voice PE Announcer Automation

This automation checks for due reminders and announces them via Voice PE:

**Automation: Voice PE Reminder Announcer**

```yaml
alias: Voice PE Reminder Announcer
description: Announces reminders via Voice PE when they are due
trigger:
  - platform: time_pattern
    minutes: /1
condition:
  - condition: template
    value_template: "{{ states('todo.reminders') | int(0) > 0 }}"
action:
  - service: todo.get_items
    target:
      entity_id: todo.reminders
    data:
      status: needs_action
    response_variable: items
  - repeat:
      for_each: "{{ items['todo.reminders']['items'] }}"
      sequence:
        - condition: template
          value_template: >
            {% set reminder_ts = as_timestamp(as_datetime(repeat.item.due)) %}
            {% set now_ts = as_timestamp(now()) %}
            {{ (reminder_ts >= now_ts - 30) and (reminder_ts <= now_ts + 30) and repeat.item.status == "needs_action" }}
        - service: assist_satellite.announce
          target:
            entity_id: assist_satellite.home_assistant_voice_09f5a3_assist_satellite
          data:
            message: "Reminder: {{ repeat.item.summary }}"
        - service: todo.update_item
          target:
            entity_id: todo.reminders
          data:
            item: "{{ repeat.item.summary }}"
            status: completed
mode: single
```

**Note**: Replace `assist_satellite.home_assistant_voice_09f5a3_assist_satellite` with your Voice PE's actual entity ID.

## Usage

### Working Voice Commands

| Command Pattern | Example |
|-----------------|---------|
| Set a reminder to [task] in [duration] | "Set a reminder to take out trash in 30 minutes" |
| Set reminder to [task] in [duration] | "Set reminder to call mom in 2 hours" |
| Remind me to [task] at [time] | "Remind me to check oven at 6pm" |
| Reminder to [task] in [duration] | "Reminder to feed cat in 1 hour" |

### Important Notes

1. **Use "set a reminder" for relative times** - "remind me" conflicts with HA's built-in delayed commands feature

2. **Ollama time parsing** - llama3.2:3b handles simple durations well (minutes, hours) but may struggle with complex dates like "next Tuesday"

3. **30-second window** - Reminders trigger within ±30 seconds of the due time

4. **Automatic completion** - After announcing, reminders are marked complete in the todo list

## Troubleshooting

### "Command will be executed in X minutes" instead of reminder

**Cause**: HA's built-in delayed commands intercepted "remind me to X in Y"

**Fix**: Use "set a reminder to" or "set reminder to" instead of "remind me to"

### Reminder not announcing

1. Check automation is enabled:
   ```bash
   curl -s -H "Authorization: Bearer $HA_TOKEN" \
     "http://192.168.4.240:8123/api/states/automation.voice_pe_reminder_announcer" | jq '.state'
   ```

2. Verify reminder has valid due_datetime in todo list

3. Check Voice PE entity ID matches automation

### Ollama returns wrong time

**Cause**: Small models sometimes parse complex time expressions incorrectly

**Fix**: Use simpler time expressions like "in 30 minutes" rather than "in half an hour"

### Verify Reminder Was Created

```bash
# Check todo list items
HA_TOKEN=$(grep "^HA_TOKEN=" ~/code/home/proxmox/homelab/.env | cut -d'=' -f2 | tr -d '"')

curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  "http://192.168.4.240:8123/api/services/todo/get_items?return_response" \
  -d '{"entity_id": "todo.reminders", "status": "needs_action"}'
```

## Automations Summary

| Automation | Purpose | Trigger |
|------------|---------|---------|
| Reminders via voice assist | Handle "at [time]" reminders | Conversation: "Remind me to..." |
| Reminder Relative Time | Handle "in [duration]" reminders | Conversation: "Set a reminder to..." |
| Voice PE Reminder Announcer | Announce due reminders | Time pattern: every minute |

## Services Used

| Service | Purpose |
|---------|---------|
| `conversation.process` | Send text to Ollama for time parsing |
| `todo.add_item` | Create reminder in todo list |
| `todo.get_items` | Retrieve pending reminders |
| `todo.update_item` | Mark reminder as completed |
| `assist_satellite.announce` | Announce via Voice PE |

## Related Documentation

- [Voice PE Complete Setup Guide](voice-pe-complete-setup-guide.md)
- [Voice PE Network Proxy Setup](voice-pe-network-proxy.md)
- [Homelab Network Topology](homelab-network-topology.md)

## Tags

voice-pe, voicepe, reminders, reminder, ollama, llm, local-llm, voice-assistant, home-assistant, homeassistant, todo, automation, whisper, piper, tts, stt, natural-language, time-parsing

---

*Document created: 2025-12-05*
