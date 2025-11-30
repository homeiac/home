# ESP32 Status Puck - Architecture

## Overview

A physical rotary display device ("puck") that provides at-a-glance monitoring of Claude Code sessions and Home Assistant status across multiple environments.

## System Context

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User's Desk                                  │
│                                                                       │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐         │
│  │  Home Mac    │     │  Work Mac    │     │   Homelab    │         │
│  │              │     │              │     │   Servers    │         │
│  │ ClaudeCodeUI │     │ ClaudeCodeUI │     │              │         │
│  │  :3000       │     │  :3000       │     │ Home Asst    │         │
│  └──────┬───────┘     └──────┬───────┘     │  :8123       │         │
│         │                    │             └──────┬───────┘         │
│         │                    │                    │                  │
│         └────────────┬───────┴────────────────────┘                  │
│                      │                                                │
│                      ▼                                                │
│              ┌───────────────┐                                       │
│              │   WiFi LAN    │                                       │
│              └───────┬───────┘                                       │
│                      │                                                │
│                      ▼                                                │
│              ┌───────────────┐                                       │
│              │  Status Puck  │  ◄── Physical device on desk         │
│              │  (ESP32-S3)   │                                       │
│              └───────────────┘                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Hardware Block Diagram

```
                    Elecrow CrowPanel 1.28" ESP32-S3
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│  ┌─────────────┐    ┌─────────────────────────────────────────┐ │
│  │   Rotary    │    │              ESP32-S3-N16R8              │ │
│  │  Encoder    │───►│  ┌─────────┐  ┌──────────┐  ┌────────┐ │ │
│  │  (A/B/SW)   │    │  │ Dual    │  │  8MB     │  │ 16MB   │ │ │
│  │  GPIO 18,19,8    │  │ Core    │  │  PSRAM   │  │ Flash  │ │ │
│  └─────────────┘    │  │ 240MHz  │  │          │  │        │ │ │
│                      │  └─────────┘  └──────────┘  └────────┘ │ │
│  ┌─────────────┐    │                                          │ │
│  │  1.28" IPS  │◄───│  ┌─────────────────────────────────────┐ │ │
│  │  240x240    │    │  │         WiFi 2.4GHz                 │ │ │
│  │  Round LCD  │    │  │         Bluetooth 5.0               │ │ │
│  │  + Touch    │    │  └─────────────────────────────────────┘ │ │
│  └─────────────┘    │                                          │ │
│                      │  GPIO Connections:                       │ │
│  ┌─────────────┐    │  • Encoder A: GPIO 19                   │ │
│  │   Buzzer    │◄───│  • Encoder B: GPIO 18                   │ │
│  │   GPIO 3    │    │  • Encoder SW: GPIO 8                   │ │
│  └─────────────┘    │  • I2C SDA: GPIO 4                      │ │
│                      │  • I2C SCL: GPIO 5                      │ │
│  ┌─────────────┐    │  • Buzzer: GPIO 3                       │ │
│  │   USB-C     │◄───│  • Button: GPIO 1                       │ │
│  │  (Power +   │    │                                          │ │
│  │   Program)  │    └─────────────────────────────────────────┘ │
│  └─────────────┘                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Software Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Application Layer                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Main Application                       │   │
│  │  • State Machine (views, navigation)                     │   │
│  │  • Event Loop (encoder, touch, timers)                   │   │
│  │  • Status Refresh Scheduler                              │   │
│  └──────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                       Service Layer                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │   Claude    │  │    Home     │  │     Configuration       │ │
│  │   Code      │  │  Assistant  │  │       Manager           │ │
│  │   Client    │  │   Client    │  │   (NVS storage)         │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                         UI Layer                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    LVGL UI Manager                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │   │
│  │  │  Claude  │  │   HA     │  │ Settings │  │  WiFi    │ │   │
│  │  │   View   │  │   View   │  │   View   │  │  Setup   │ │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│               Hardware Abstraction Layer (HAL)                   │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────┐ │
│  │ Encoder │  │ Display │  │  Touch  │  │ Network │  │Buzzer│ │
│  │ Driver  │  │ Driver  │  │ Driver  │  │  Stack  │  │Driver│ │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └──────┘ │
├─────────────────────────────────────────────────────────────────┤
│                      Platform Layer                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  ESP-IDF / Arduino   │   LovyanGFX   │   LVGL 8.3        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## State Machine

```
                         ┌─────────────┐
                         │   STARTUP   │
                         └──────┬──────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
            ┌───────────────┐       ┌───────────────┐
            │  WIFI_SETUP   │       │  CLAUDE_CODE  │◄──────┐
            │               │       │     VIEW      │       │
            │ • Show AP QR  │       │               │       │
            │ • Config form │       │ • Device name │       │
            └───────┬───────┘       │ • Sessions    │       │
                    │               │ • Git status  │       │
                    │               │ • Last task   │       │
            WiFi OK │               └───────┬───────┘       │
                    │                       │               │
                    │              Rotate   │   Rotate      │
                    │              past     │   between     │
                    │              devices  │   devices     │
                    │                       ▼               │
                    │               ┌───────────────┐       │
                    └──────────────►│ HOME_ASST     │───────┘
                                    │    VIEW       │ Rotate
                                    │               │ back
                                    │ • CPU temp    │
                                    │ • K8s status  │
                                    │ • Alerts      │
                                    └───────┬───────┘
                                            │
                                   Long     │
                                   Press    ▼
                                    ┌───────────────┐
                                    │   SETTINGS    │
                                    │               │
                                    │ • Brightness  │
                                    │ • Devices     │
                                    │ • WiFi reset  │
                                    └───────────────┘
```

## Data Flow

```
┌────────────────────────────────────────────────────────────────────┐
│                        Periodic Refresh (30s)                       │
└────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────┐
│  HTTP GET /api/status                                               │
│  ┌─────────────────┐      ┌────────────────────────────────────┐   │
│  │  ClaudeCodeUI   │ ───► │ {"sessions": 2, "gitDirty": 1, ... }│   │
│  │  :3000          │      └────────────────────────────────────┘   │
│  └─────────────────┘                        │                       │
│                                             ▼                       │
│                               ┌─────────────────────────────┐      │
│                               │      JSON Parser            │      │
│                               │  (ArduinoJson)              │      │
│                               └──────────────┬──────────────┘      │
│                                              │                      │
│                                              ▼                      │
│                               ┌─────────────────────────────┐      │
│                               │   ClaudeCodeStatus struct   │      │
│                               │  • active_sessions: 2       │      │
│                               │  • git_status: DIRTY        │      │
│                               │  • git_changed_files: 1     │      │
│                               └──────────────┬──────────────┘      │
│                                              │                      │
│                                              ▼                      │
│                               ┌─────────────────────────────┐      │
│                               │    LVGL UI Update           │      │
│                               │  • Redraw indicators        │      │
│                               │  • Update text labels       │      │
│                               │  • Animate changes          │      │
│                               └─────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────┘
```

## UI Layout (240x240 Round Display)

```
              ┌──────────────────────────────┐
             ╱              HOME              ╲
            │        (device name arc)         │
           ╱                                    ╲
          │    ┌────────────────────────┐       │
          │    │                        │       │
         │     │         ●              │        │
         │     │     Sessions: 2        │        │
         │     │                        │        │
         │     │    ┌────┐  ┌────┐     │        │
          │    │    │ ✓  │  │ +3 │     │       │
          │    │    │git │  │mod │     │       │
           ╲   │    └────┘  └────┘     │      ╱
            │  │                        │     │
             ╲ │  "Fixed auth bug..."   │    ╱
              ╲│  (last task truncated) │   ╱
               └────────────────────────┘
                     (touch anywhere
                      to see full task)
```

## Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **main.cpp** | Event loop, state machine, coordination |
| **state_manager.cpp** | Navigation state, device cycling, view transitions |
| **status_parser.cpp** | JSON parsing for API responses |
| **hardware_abstraction.h** | Interface definitions for HAL |
| **hardware_esp32.cpp** | Real ESP32 hardware implementations |
| **hardware_mock.cpp** | Mock implementations for native testing |
| **ui_manager.cpp** | LVGL screen setup and updates |
| **config_manager.cpp** | NVS persistence, WiFi credentials |

## Development Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Write BDD Feature Spec (Gherkin)                            │
│     features/new-feature.feature                                │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Write Unit Tests (Unity)                                    │
│     test/test_new_feature.cpp                                   │
│     Run: pio test -e native                                     │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. Implement with Mocked Backends                              │
│     Start: cd mocks/claude-code-api && npm start                │
│     Build: pio run -e esp32s3                                   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. Integration Test on Hardware                                │
│     Upload: pio run -t upload                                   │
│     Monitor: pio device monitor                                 │
└─────────────────────────────────────────────────────────────────┘
```

## API Contracts

### ClaudeCodeUI Status Endpoint

```
GET /api/status
Response:
{
  "sessions": number,      // Active Claude Code sessions
  "agents": number,        // Running subagents
  "lastTask": string|null, // Most recent task summary (max 64 chars)
  "lastTaskTime": string,  // ISO 8601 timestamp
  "gitDirty": number,      // Count of projects with uncommitted changes
  "timestamp": string      // Response timestamp
}
```

### Home Assistant Puck Endpoint (Custom)

```
GET /api/puck/status
Headers: Authorization: Bearer <long-lived-token>
Response:
{
  "cpu_temp": number,      // Server CPU temp in Celsius
  "memory_pct": number,    // Memory usage 0-100
  "k8s_healthy": boolean,  // Kubernetes cluster health
  "alerts": number,        // Active alert count
  "notifications": number, // Unread notification count
  "office_lights": boolean,// Example toggle entity state
  "timestamp": string
}
```

## Memory Budget

| Component | Estimated RAM |
|-----------|---------------|
| LVGL frame buffer (240x240x16bit) | ~115 KB |
| LVGL widgets/objects | ~20 KB |
| HTTP response buffers | ~4 KB |
| State structures | ~2 KB |
| Stack/heap overhead | ~50 KB |
| **Available PSRAM** | **8 MB** |

The device has ample memory. Frame buffer can be allocated in PSRAM.

## Power Considerations

- USB-C powered (5V/1A)
- Display always on (no battery)
- WiFi maintains connection
- Consider display dimming after inactivity timeout
