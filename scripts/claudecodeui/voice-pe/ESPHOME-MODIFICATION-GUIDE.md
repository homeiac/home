# Voice PE ESPHome Modification Guide

## Goal
Expose LED effects and dial rotation events to Home Assistant for Claude Code integration.

## Current State
- **LED ring** (`led_ring`): Exposed to HA, supports RGB color BUT effects are internal
- **Effects** (`voice_assistant_leds`): Internal only, defined as `addressable_lambda`
- **Dial**: Only triggers internal `control_volume`/`control_hue` scripts

## Required Modifications

### 1. Expose LED Effects as HA Services

Add to `api:` section:

```yaml
api:
  encryption:
    key: !secret api_encryption_key

  services:
    # Expose LED effect control
    - service: set_led_effect
      variables:
        effect_name: string
      then:
        - lambda: |-
            // Map effect name to internal effect
            if (effect_name == "thinking") {
              id(voice_assistant_phase) = 4;  // thinking phase
              id(control_leds).execute();
            } else if (effect_name == "listening") {
              id(voice_assistant_phase) = 3;  // listening phase
              id(control_leds).execute();
            } else if (effect_name == "idle") {
              id(voice_assistant_phase) = 1;  // idle phase
              id(control_leds).execute();
            }

    # Alternative: Direct effect trigger
    - service: trigger_thinking_effect
      then:
        - script.execute: control_leds_voice_assistant_thinking_phase

    - service: stop_effects
      then:
        - lambda: id(voice_assistant_phase) = 1;
        - script.execute: control_leds
```

### 2. Expose Dial Rotation Events

Add to existing `sensor:` or `binary_sensor:` rotary encoder config:

```yaml
sensor:
  - platform: rotary_encoder
    id: dial
    pin_a: GPIO16
    pin_b: GPIO18
    resolution: 2

    on_clockwise:
      # Existing volume control
      - if:
          condition:
            binary_sensor.is_off: center_button
          then:
            - script.execute: control_volume_up
      # NEW: Fire HA event for Claude approval
      - homeassistant.event:
          event: esphome.voice_pe_dial
          data:
            direction: clockwise
            device_id: !lambda 'return App.get_name().c_str();'

    on_anticlockwise:
      # Existing volume control
      - if:
          condition:
            binary_sensor.is_off: center_button
          then:
            - script.execute: control_volume_down
      # NEW: Fire HA event for Claude approval
      - homeassistant.event:
          event: esphome.voice_pe_dial
          data:
            direction: anticlockwise
            device_id: !lambda 'return App.get_name().c_str();'
```

### 3. Add Center Button Event (for confirmation)

```yaml
binary_sensor:
  - platform: gpio
    id: center_button
    pin:
      number: GPIO17  # Check actual pin
      mode: INPUT_PULLUP
      inverted: true

    on_press:
      - homeassistant.event:
          event: esphome.voice_pe_button
          data:
            action: press

    on_multi_click:
      - timing:
          - ON for at least 1s
        then:
          - homeassistant.event:
              event: esphome.voice_pe_button
              data:
                action: long_press
```

## How to Apply

1. **Access ESPHome Dashboard**
   - Open HA → Add-ons → ESPHome
   - Or: http://homeassistant.maas:6052

2. **Edit Voice PE Config**
   - Find "Home Assistant Voice" device
   - Click EDIT
   - Add the modifications above

3. **Validate & Install**
   - Click "Validate" to check syntax
   - Click "Install" → Wirelessly (OTA)
   - Wait for reboot (~30 seconds)

4. **Test in HA**
   - Check Services: `esphome.home_assistant_voice_XXXX_set_led_effect`
   - Check Events: Listen for `esphome.voice_pe_dial`

## HA Automation Example

```yaml
automation:
  - alias: "Claude Thinking LED"
    trigger:
      - platform: mqtt
        topic: claude/command
    action:
      - service: esphome.home_assistant_voice_09f5a3_trigger_thinking_effect

  - alias: "Claude Dial Approval"
    trigger:
      - platform: event
        event_type: esphome.voice_pe_dial
    condition:
      - condition: state
        entity_id: input_boolean.claude_awaiting_approval
        state: "on"
    action:
      - choose:
          - conditions:
              - "{{ trigger.event.data.direction == 'clockwise' }}"
            sequence:
              - service: mqtt.publish
                data:
                  topic: claude/approval-response
                  payload: '{"approved": true}'
          - conditions:
              - "{{ trigger.event.data.direction == 'anticlockwise' }}"
            sequence:
              - service: mqtt.publish
                data:
                  topic: claude/approval-response
                  payload: '{"approved": false}'
```

## Alternative: Color-Only Mode (No ESPHome Changes)

If ESPHome modification is too complex, use solid colors:

| State | RGB Color | Description |
|-------|-----------|-------------|
| thinking | 24, 187, 242 | Cyan |
| waiting | 255, 165, 0 | Amber |
| approve | 0, 255, 0 | Green |
| reject | 255, 0, 0 | Red |

This works via `light.turn_on` service without firmware changes.
