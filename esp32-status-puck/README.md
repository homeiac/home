# ESP32 Status Puck

A physical rotary display device ("smart knob") for monitoring Claude Code sessions and Home Assistant status across multiple environments. Rotate to switch devices, press to refresh, glance at the LED ring for instant system health.

## Hardware Target

**[Elecrow CrowPanel 1.28" ESP32-S3 Rotary Display](https://www.elecrow.com/crowpanel-1-28inch-hmi-esp32-rotary-display-240-240-ips-round-touch-knob-screen.html)** ($29)

| Feature | Specification |
|---------|---------------|
| Display | 1.28" round IPS, 240×240, capacitive touch |
| Processor | ESP32-S3 dual-core @ 240MHz |
| Memory | 8MB PSRAM + 16MB Flash |
| Connectivity | WiFi 2.4GHz + Bluetooth 5.0 |
| Input | Rotary encoder + push button + side button + touch |
| Feedback | 5× RGB LEDs (WS2812) + buzzer + vibration motor |
| Extras | RTC (BM8563), I2C expansion |

## Concept

```
     ┌─────────────────────────┐
    ╱  ● ● ● ● ●   ← LED ring  ╲
   │     ╭─────────────╮        │
   │    ╱     HOME      ╲       │    ← Rotate: switch devices
   │   │    Sessions: 2  │      │    ← Press: refresh
   │   │     ✓ git  +3   │      │    ← Glance: LED = health
   │    ╲  "Fixed bug..."╱      │
   │     ╰─────────────╯        │
    ╲                          ╱
     └─────────────────────────┘
            ▲
            │ Rotate knob
            ▼
        home → work → HA → home...
```

## Project Structure

```
esp32-status-puck/
├── docs/                   # Architecture and design documents
│   ├── architecture.md     # System diagrams, data flow
│   └── design.md           # Full hardware/UX feature mapping
├── features/               # BDD specifications (Gherkin)
│   ├── rotary-navigation.feature
│   ├── status-display.feature
│   ├── home-assistant-integration.feature
│   ├── led-feedback.feature
│   ├── haptic-audio-feedback.feature
│   └── touch-gestures.feature
├── firmware/               # PlatformIO ESP32 project
│   ├── src/                # Application source
│   ├── include/            # Headers (HAL, config, models)
│   ├── test/               # Native unit tests (Unity)
│   └── platformio.ini      # Build configuration
└── mocks/                  # Development mock servers
    ├── claude-code-api/    # Simulates ClaudeCodeUI backend
    └── home-assistant-api/ # Simulates HA REST API
```

## Development Approach

### BDD-Driven
1. **Features First**: Define behavior in Gherkin (`features/*.feature`)
2. **Unit Tests**: Test logic with mocked hardware (`pio test -e native`)
3. **Mock Backends**: Develop against simulated APIs
4. **Hardware Integration**: Final validation on real device

### Hardware Abstraction
All hardware interactions go through `hardware_abstraction.h`:
- `MOCK_HARDWARE=1` → Mock implementations for desktop testing
- `MOCK_HARDWARE=0` → Real ESP32 hardware drivers

## Quick Start

### 1. Start Mock Backends
```bash
cd mocks/claude-code-api && npm install && npm start &
cd mocks/home-assistant-api && npm install && npm start &
```

### 2. Run Native Tests (no hardware)
```bash
cd firmware
pio test -e native
```

### 3. Build & Upload to Device
```bash
cd firmware
pio run -e esp32s3 -t upload
pio device monitor
```

## Feature Summary

### LED Ring (5× WS2812)
| Pattern | Meaning |
|---------|---------|
| Solid green | All healthy |
| Amber LEDs (1-3) | Issues proportional to count |
| Pulsing red | Critical alert |
| Breathing white | Loading |
| Rainbow chase | Settings mode |
| Device color flash | Switched to that device |

### Controls
| Input | Action |
|-------|--------|
| Rotate CW/CCW | Navigate devices/views |
| Short press | Refresh status |
| Long press (3s) | Enter/exit settings |
| Side button | Quick view toggle |
| Touch tap | Refresh / toggle entity |
| Swipe | Navigate |

### Haptic & Audio
- Click on each encoder detent
- Vibration pulse on alerts
- Configurable volumes and enable/disable

## API Integration

### ClaudeCodeUI
```
GET /api/status
→ { "sessions": 2, "gitDirty": 1, "lastTask": "..." }
```

### Home Assistant
```
GET /api/puck/status  (custom endpoint)
→ { "cpu_temp": 65, "k8s_healthy": true, ... }
```

## Documentation

- **[Architecture](docs/architecture.md)** - System diagrams, data flow, memory budget
- **[Design](docs/design.md)** - Complete hardware→UX mapping, state machine, phases

## References

- [Elecrow Product Page](https://www.elecrow.com/crowpanel-1-28inch-hmi-esp32-rotary-display-240-240-ips-round-touch-knob-screen.html)
- [Elecrow Wiki Tutorial](https://www.elecrow.com/wiki/CrowPanel_1.28inch-HMI_ESP32_Rotary_Display.html)
- [ESP32-S3 Rotary LCD Examples](https://github.com/ljgonzalez1/esp32-s3-rotary-lcd-examples)
- [ClaudeCodeUI](https://github.com/siteboon/claudecodeui)
- [LVGL Graphics Library](https://lvgl.io/)
- [LovyanGFX Display Driver](https://github.com/lovyan03/LovyanGFX)

## Status

**Phase: Design Complete, Implementation Pending**

- [x] Hardware research and feature inventory
- [x] Architecture and design documentation
- [x] BDD feature specifications (6 feature files)
- [x] Mock backend servers
- [x] PlatformIO project scaffold
- [x] Hardware abstraction layer design
- [ ] Verify GPIO mappings on actual hardware
- [ ] Implement LVGL UI
- [ ] Implement networking layer
- [ ] Integration testing
