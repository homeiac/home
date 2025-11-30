# ESP32 Status Puck - Design Document

## Hardware Feature Inventory

Based on [Elecrow CrowPanel 1.28" specifications](https://www.elecrow.com/crowpanel-1-28inch-hmi-esp32-rotary-display-240-240-ips-round-touch-knob-screen.html) and [Elecrow Wiki](https://www.elecrow.com/wiki/CrowPanel_1.28inch-HMI_ESP32_Rotary_Display.html):

| Feature | Specification | GPIO/Interface |
|---------|---------------|----------------|
| **MCU** | ESP32-S3R8 dual-core 240MHz | - |
| **Memory** | 8MB PSRAM + 16MB Flash | - |
| **Display** | 1.28" IPS 240x240, 65K colors | SPI |
| **Touch** | Capacitive, multi-point | I2C |
| **Rotary Encoder** | Incremental, CW/CCW | GPIO 18, 19 |
| **Encoder Button** | Integrated push switch | GPIO 8 |
| **Side Button** | Additional pushbutton | GPIO 1 |
| **RGB LEDs** | 5× WS2812 NeoPixel | GPIO TBD |
| **Buzzer** | Passive piezo | GPIO 3 |
| **Vibration Motor** | Haptic feedback | I2C (0x43) |
| **RTC** | BM8563 | I2C |
| **WiFi** | 802.11 b/g/n 2.4GHz | Built-in |
| **Bluetooth** | BLE 5.0 | Built-in |
| **Power** | 5V/1A USB-C | - |

---

## Feature-to-UX Mapping

### 1. RGB LEDs (5× WS2812 Ring)

**Primary Use: Status Severity Indicator**

The LED ring around the device provides ambient awareness without looking directly at the screen.

| LED Pattern | Meaning |
|-------------|---------|
| All OFF | Device idle/dimmed |
| Breathing white | Connecting/loading |
| Solid green ring | All systems healthy |
| 1-2 amber LEDs | Minor issues (1-2 dirty repos) |
| 3+ amber LEDs | Attention needed (multiple issues) |
| Pulsing red | Critical alert (cluster down, high temp) |
| Rainbow chase | Settings mode |
| Blue pulse | Bluetooth pairing mode |

**Device-Specific Colors:**
```
Device 1 (home): Cool blue accent
Device 2 (work): Warm orange accent
Device 3+: Purple, cyan, etc.
```

When rotating between devices, the LED ring briefly shows the device's accent color.

### 2. Rotary Encoder

**Primary Use: Navigation**

| Action | Context | Result |
|--------|---------|--------|
| Rotate CW | Claude Code view | Next device |
| Rotate CCW | Claude Code view | Previous device |
| Rotate CW | HA view | Next entity/gauge |
| Rotate CCW | HA view | Previous entity |
| Rotate | Settings | Adjust value |
| Rotate | Any | Wake from dim |

**Detent Feedback:**
- Each detent = one step
- 4 encoder pulses per detent (handled in firmware)
- Buzzer click on each detent for audio confirmation

### 3. Encoder Button (Press)

| Action | Result |
|--------|--------|
| Short press (<1s) | Refresh current status |
| Long press (3s) | Enter/exit settings |
| Double tap | Toggle HA entity (when in HA view) |

### 4. Side Button (GPIO 1)

Dedicated secondary button for quick actions:

| Action | Result |
|--------|--------|
| Short press | Cycle view (Claude → HA → Claude) |
| Long press | WiFi setup mode |
| Triple press | Factory reset (with confirmation) |

### 5. Vibration Motor

Haptic feedback for:
- Alert notifications (3 short pulses)
- Long press confirmation (single strong pulse)
- Error acknowledgment (double pulse)
- Settings changes saved (gentle pulse)

### 6. Buzzer

Audio feedback layered with vibration:

| Sound | Event |
|-------|-------|
| Click (1000Hz, 10ms) | Encoder detent |
| Beep up (1000→2000Hz) | Success/connected |
| Beep down (2000→1000Hz) | Disconnected/error |
| Double beep | Alert received |
| Long tone | Long press detected |

### 7. Touch Screen

The round touch screen supports:

| Gesture | Result |
|---------|--------|
| Tap center | Same as encoder press (refresh) |
| Tap entity | Toggle (HA switch entities) |
| Swipe left | Next device/view |
| Swipe right | Previous device/view |
| Long tap | Show full text (truncated items) |

### 8. RTC (Real-Time Clock)

- Maintains time during power loss
- Shows time on idle/screensaver
- Timestamps for "last updated X minutes ago"
- Automatic NTP sync when WiFi connected

---

## Display UI Specifications

### Claude Code View

```
         ┌────────────────────────────────┐
        ╱     ●  ●  ●  ●  ●               ╲    ← LED ring (5 LEDs)
       │       ╭───────────╮               │
      │      ╱    HOME      ╲               │   ← Device name (arc text)
      │     │                 │              │
     │      │    ┌─────┐      │              │
     │      │    │  2  │      │              │   ← Session count (large)
     │      │    │ ▶▶  │      │              │   ← Agents running indicator
     │      │    └─────┘      │              │
     │      │                 │              │
      │     │   ┌──┐  ┌──┐   │              │
      │      │  │✓ │  │+3│   │             │   ← Git status icons
       │      ╲ └──┘  └──┘  ╱              │
        ╲      ╰───────────╯              ╱
         │    Fixed auth bug...           │    ← Last task (scrolling)
          ╲         12:34                ╱     ← Last update time
           └────────────────────────────┘
```

**Visual Elements:**

| Element | Size | Position |
|---------|------|----------|
| Device name | 16px, arc | Top |
| Session count | 48px, bold | Center |
| Agent indicator | 24px icon | Below count |
| Git status | 24×24 icons | Left-center |
| Changed files | 16px | Next to git icon |
| Last task | 14px, 1 line | Bottom third |
| Update time | 12px | Bottom |

### Home Assistant View

```
         ┌────────────────────────────────┐
        ╱                                  ╲
       │      ╭───────────────────╮         │
      │     ╱    HOMELAB           ╲        │   ← HA location name
      │    │    ╱───────────╲       │       │
     │     │   │   ┌───┐     │      │       │
     │     │   │   │ ✓ │     │      │       │   ← K8s health (center)
     │     │   │   │K8S│     │      │       │
     │     │   │   └───┘     │      │       │
     │     │    ╲───────────╱       │       │
      │    │                        │       │
      │     │   65°C    72%        │       │   ← CPU temp, Memory
       │     ╲    ⚠ 0 alerts      ╱        │   ← Alert count
        ╲      ╰─────────────────╯         ╱
         │         💡 OFF                  │    ← Toggle entity
          └────────────────────────────────┘
```

**Gauge Arcs:**
- Temperature: Arc from blue (cold) to red (hot)
- Memory: Arc from green to yellow to red
- Position around the circular display edge

### Settings View

```
         ┌────────────────────────────────┐
        ╱   🌈 (rainbow LED chase)         ╲
       │      ╭───────────────────╮         │
      │     ╱     SETTINGS         ╲        │
      │    │                        │       │
     │     │   ☀️ Brightness        │       │
     │     │   ████████░░  80%     │       │   ← Adjustable slider
     │     │                        │       │
     │     │   🔊 Sound: ON         │       │
      │    │   📶 WiFi: Connected  │       │
      │     │   📱 Devices: 2       │       │
       │     ╲                     ╱        │
        ╲      ╰─────────────────╯         ╱
         │     Long press to exit          │
          └────────────────────────────────┘
```

### WiFi Setup View

```
         ┌────────────────────────────────┐
        ╱   🔵 (blue pulsing LEDs)         ╲
       │      ╭───────────────────╮         │
      │     ╱     WIFI SETUP       ╲        │
      │    │                        │       │
     │     │     ┌─────────┐        │       │
     │     │     │ QR CODE │        │       │   ← Connect to AP
     │     │     │         │        │       │
     │     │     └─────────┘        │       │
      │    │                        │       │
      │     │  Connect to:          │       │
       │     ╲ "StatusPuck-XXXX"   ╱        │
        ╲      ╰─────────────────╯         ╱
         │    Then open 192.168.4.1        │
          └────────────────────────────────┘
```

---

## Interaction State Machine

```
                              ┌─────────────────┐
                              │     BOOT        │
                              └────────┬────────┘
                                       │
               ┌───────────────────────┼───────────────────────┐
               │                       │                       │
               ▼                       ▼                       ▼
      ┌────────────────┐      ┌────────────────┐      ┌────────────────┐
      │  WIFI_SETUP    │      │   CONNECTING   │      │   CONNECTED    │
      │                │      │                │      │                │
      │ • Blue LED     │      │ • White breath │      │ • Green flash  │
      │ • Show QR      │      │ • "Connecting" │      │ • Beep up      │
      │ • AP mode      │      │                │      │ • Go to IDLE   │
      └────────┬───────┘      └────────────────┘      └────────┬───────┘
               │                                               │
               │ Config saved                                  │
               └───────────────────────────────────────────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │      IDLE       │
                              │                 │
                              │ • Auto-refresh  │
                              │ • Dim after 60s │
                              │ • LED = status  │
                              └────────┬────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         │                             │                             │
    Rotate/Touch                  Side Button                   Long Press
         │                             │                             │
         ▼                             ▼                             ▼
┌────────────────┐            ┌────────────────┐            ┌────────────────┐
│ CLAUDE_VIEW    │◄──────────►│   HA_VIEW      │            │   SETTINGS     │
│                │  Cycle     │                │            │                │
│ • Device name  │            │ • Gauges       │            │ • Rainbow LED  │
│ • Sessions     │            │ • Alerts       │            │ • Adjust vals  │
│ • Git status   │            │ • Entities     │            │                │
│ • Device LED   │            │                │            │                │
└────────────────┘            └────────────────┘            └────────────────┘
         │                             │                             │
         │◄────────────────────────────┴─────────────────────────────┘
         │                                              Long Press exits
         ▼
┌────────────────┐
│   REFRESHING   │
│                │
│ • Spin anim    │
│ • White LED    │
│ • HTTP request │
└────────────────┘
         │
         ▼
┌────────────────┐
│   UPDATED      │
│                │
│ • Flash green  │
│ • Quick vibrate│
│ • Update UI    │
└────────────────┘
```

---

## Alert Priority System

Alerts from both Claude Code and Home Assistant are prioritized:

| Priority | Source | Trigger | LED | Vibration |
|----------|--------|---------|-----|-----------|
| P1 Critical | HA | K8s cluster down | Red pulse | 3× strong |
| P1 Critical | HA | CPU >90°C | Red pulse | 3× strong |
| P2 High | HA | >3 active alerts | Amber pulse | 2× medium |
| P2 High | Claude | >5 dirty repos | Amber pulse | 2× medium |
| P3 Medium | Claude | Running agents >3 | Amber static | 1× light |
| P4 Low | HA | Notifications | Blue flash | None |

---

## Configuration Schema

```yaml
# Stored in ESP32 NVS (Non-Volatile Storage)
wifi:
  ssid: "HomeNetwork"
  password: "encrypted"

devices:
  - name: "home"
    url: "http://192.168.1.100:3000"
    color: "#4A90D9"  # Device accent color for LEDs
    token: ""
  - name: "work"
    url: "http://192.168.1.101:3000"
    color: "#D97B4A"
    token: ""

home_assistant:
  enabled: true
  url: "http://homeassistant.local:8123"
  token: "long-lived-token"
  entities:
    - "sensor.server_cpu_temp"
    - "sensor.server_memory_used"
    - "binary_sensor.k8s_cluster_healthy"
    - "sensor.active_alerts"
    - "switch.office_lights"

display:
  brightness: 180
  dim_after_seconds: 60
  dim_level: 50

sound:
  enabled: true
  click_volume: 50
  alert_volume: 100

haptics:
  enabled: true
  click_strength: 30
  alert_strength: 100
```

---

## Development Phases

### Phase 1: Core Hardware (Week 1)
- [ ] Verify all GPIO mappings on actual hardware
- [ ] Test encoder with debouncing
- [ ] Test WS2812 LED control
- [ ] Test buzzer tones
- [ ] Test vibration motor via I2C
- [ ] Basic display output with LovyanGFX

### Phase 2: Display UI (Week 2)
- [ ] LVGL setup and configuration
- [ ] Claude Code view implementation
- [ ] Home Assistant view implementation
- [ ] Settings view implementation
- [ ] Smooth transitions and animations

### Phase 3: Networking (Week 3)
- [ ] WiFi connection management
- [ ] WiFi setup AP mode with captive portal
- [ ] HTTP client for API calls
- [ ] JSON parsing with ArduinoJson
- [ ] Auto-refresh scheduling

### Phase 4: Integration (Week 4)
- [ ] Full state machine implementation
- [ ] Alert system with LED/vibration
- [ ] NVS configuration persistence
- [ ] OTA update support
- [ ] Final polish and edge cases

---

## Open Questions

1. **LED GPIO Pin**: Wiki doesn't specify WS2812 data pin - need to verify on hardware
2. **Touch Controller**: Which I2C address? CST816S or similar?
3. **Multiple ClaudeCodeUI instances**: How to handle when one is unreachable?
4. **Battery backup**: Is there value in adding a small LiPo for RTC?
5. **ESPHome vs Custom Firmware**: ESPHome would simplify HA integration but limit Claude Code features

---

## References

- [Elecrow Product Page](https://www.elecrow.com/crowpanel-1-28inch-hmi-esp32-rotary-display-240-240-ips-round-touch-knob-screen.html)
- [Elecrow Wiki Tutorial](https://www.elecrow.com/wiki/CrowPanel_1.28inch-HMI_ESP32_Rotary_Display.html)
- [XDA Review](https://www.xda-developers.com/esp32-powered-display-clock-rotary-display-elecrow/)
- [CNX Software Announcement](https://www.cnx-software.com/2025/09/19/elecrow-esp32-s3-rotary-displays-combine-round-ips-touchscreen-knob-and-press-input/)
- [ESP32-S3 Rotary LCD Examples (GitHub)](https://github.com/ljgonzalez1/esp32-s3-rotary-lcd-examples)
- [ClaudeCodeUI (GitHub)](https://github.com/siteboon/claudecodeui)
