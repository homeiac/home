# Claude Code Ambient AI - Architecture & Design

**Version:** 1.1
**Status:** Draft
**Last Updated:** 2025-12-14

---

## Web UI Selection: claudecodeui

After evaluating multiple options, we chose **[siteboon/claudecodeui](https://github.com/siteboon/claudecodeui)** as the base for our fork.

### Comparison

| Repo | Stars | Claude Code Specific | Backend | Extensibility |
|------|-------|---------------------|---------|---------------|
| [sugyan/claude-code-webui](https://github.com/sugyan/claude-code-webui) | 742 | Yes | Deno/Node.js | Limited |
| [**siteboon/claudecodeui**](https://github.com/siteboon/claudecodeui) | **5,000** | **Yes** | **Express.js + WebSocket** | **Good** |
| [open-webui](https://github.com/open-webui/open-webui) | 118k | No (general LLM) | Python/FastAPI | Excellent |
| [LibreChat](https://github.com/danny-avila/LibreChat) | 32.4k | No (general LLM) | Node.js | MCP support |

### Why claudecodeui

- **7x more stars** than sugyan (5k vs 742)
- **Built specifically for Claude Code CLI** - spawns it directly, reads `~/.claude/projects/`
- **Express.js + WebSocket backend** - easy to add MQTT hooks
- **Rich feature set**: File explorer, Git integration, CodeMirror editor, session management
- **Actively maintained** - v1.12.0 (Nov 2025)
- **GPL-3.0 license** - allows forking

### Fork: homeiac/claudecodeui

Our fork adds:
1. **MQTT client** in Express backend (using `mqtt` npm package)
2. **WebSocket event hooks** → MQTT publish on task start/complete/fail
3. **Status endpoint** `/api/status` for device polling (backup)
4. **MQTT subscription** for incoming commands from devices
5. **Configurable broker** via environment variables

### MQTT Integration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    claudecodeui (homeiac fork)                   │
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────┐│
│  │  React       │     │  Express.js  │     │  Claude CLI      ││
│  │  Frontend    │◄────│  Backend     │◄────│  Process         ││
│  │  (unchanged) │ WS  │  + MQTT hooks│     │  (spawned)       ││
│  └──────────────┘     └──────┬───────┘     └──────────────────┘│
│                              │                                  │
│                    ┌─────────▼─────────┐                       │
│                    │  MqttBridge.js    │                       │
│                    │  (NEW)            │                       │
│                    └─────────┬─────────┘                       │
└──────────────────────────────┼──────────────────────────────────┘
                               │
                     MQTT pub/sub
                               │
                    ┌──────────▼──────────┐
                    │  Mosquitto Broker   │
                    │  mqtt.homelab:1883  │
                    └─────────────────────┘
```

### Key Code Changes (Express Backend)

```javascript
// server/mqtt-bridge.js (NEW FILE)

const mqtt = require('mqtt');

class MqttBridge {
  constructor(options = {}) {
    this.broker = options.broker || process.env.MQTT_BROKER || 'mqtt://mqtt.homelab';
    this.serverName = options.serverName || process.env.SERVER_NAME || 'home';
    this.client = null;
  }

  connect() {
    this.client = mqtt.connect(this.broker);

    this.client.on('connect', () => {
      console.log(`MQTT connected to ${this.broker}`);
      // Subscribe to commands
      this.client.subscribe('claude/command');
      // Publish online status
      this.publishStatus({ online: true });
    });

    this.client.on('message', (topic, message) => {
      if (topic === 'claude/command') {
        this.handleCommand(JSON.parse(message.toString()));
      }
    });
  }

  publishStatus(status) {
    const payload = {
      server: this.serverName,
      online: status.online ?? true,
      sessions: status.sessions ?? 0,
      git_dirty: status.git_dirty ?? 0,
      active_task: status.active_task ?? null,
      last_activity: new Date().toISOString()
    };
    this.client.publish(
      `claude/${this.serverName}/status`,
      JSON.stringify(payload),
      { retain: true, qos: 1 }
    );
  }

  publishTaskEvent(event, taskId, description, extra = {}) {
    const payload = {
      event,
      task_id: taskId,
      description,
      ...extra
    };
    this.client.publish(
      `claude/${this.serverName}/task/${taskId}`,
      JSON.stringify(payload),
      { qos: 1 }
    );
  }

  publishNotification(priority, title, message, actions = ['dismiss']) {
    const payload = { priority, title, message, actions };
    this.client.publish(
      `claude/${this.serverName}/notification`,
      JSON.stringify(payload),
      { retain: true, qos: 1 }
    );
  }

  handleCommand(command) {
    // Emit to WebSocket for UI to handle
    this.emit('command', command);
  }
}

module.exports = MqttBridge;
```

### Environment Variables

```bash
# .env for claudecodeui
MQTT_BROKER=mqtt://mqtt.homelab:1883
SERVER_NAME=home              # or "work" for work server
MQTT_ENABLED=true
STATUS_INTERVAL=30000         # Publish status every 30s
```

---

## Vision

**"Ambient AI presence that sees, listens, and proactively helps"**

Interact with Claude Code through multiple physical interfaces (voice, text, vision, display) without being at a computer. Two servers: Home (always-on) and Work (on-demand).

---

## Table of Contents

1. [Use Cases](#use-cases)
2. [Device Inventory](#device-inventory)
3. [System Architecture](#system-architecture)
4. [MQTT Topic Schema](#mqtt-topic-schema)
5. [Data Flows](#data-flows)
6. [Firmware Strategy](#firmware-strategy)
7. [Testing Strategy](#testing-strategy)
8. [Implementation Phases](#implementation-phases)

---

## Use Cases

### P0 - Foundation (Must Have)

| ID | Use Case | Description | Devices |
|----|----------|-------------|---------|
| P0-1 | Ask Claude from anywhere | Voice/text command → Claude responds | Voice PE, Cardputer, AtomS3R |
| P0-2 | Know when Claude is done | Push notification on task complete/fail | All devices |

### P1 - Ambient Intelligence

| ID | Use Case | Description | Devices |
|----|----------|-------------|---------|
| P1-3 | Proactive briefing on entry | Walk in room → "Prod cluster down, check it" | AtomS3R, Voice PE |
| P1-4 | Context-aware alerts | Knows what matters to YOU right now | All devices |
| P1-5 | Glanceable status | Puck shows session/git at a glance | Puck |

### P2 - Security/Awareness

| ID | Use Case | Description | Devices |
|----|----------|-------------|---------|
| P2-6 | Unknown person alert | Unfamiliar face when family away → alert | AtomS3R + Frigate |
| P2-7 | Who's home | Track family presence via face recognition | AtomS3R + Frigate |

### P3 - Enhanced Interaction

| ID | Use Case | Description | Devices |
|----|----------|-------------|---------|
| P3-8 | Quick text pager | Cardputer for typing without laptop | Cardputer |
| P3-9 | Show Claude something | Camera → "What's this error?" | AtomS3R |
| P3-10 | Multi-room voice | Voice PE office, AtomS3R living room | Voice PE, AtomS3R |

### P4 - Future (Minority Report)

| ID | Use Case | Description |
|----|----------|-------------|
| P4-11 | Gesture control | Wave to dismiss, point to select |
| P4-12 | Predictive alerts | "Based on patterns, deploy might fail" |
| P4-13 | Spatial awareness | Different info based on where you're standing |

---

## Device Inventory

| Device | Location | Role | I/O | Firmware |
|--------|----------|------|-----|----------|
| **Module-LLM** | With AtomS3R | Edge AI brain | NPU + LLM + ASR + TTS | StackFlow |
| **AtomS3R-CAM** | Living room | Ambient AI presence | Camera + Mic + Speaker + IMU | Custom PlatformIO |
| **Voice PE** | Office/Kitchen | HA voice satellite | Mic + Speaker + LED ring | HA Native |
| **Status Puck** | Desk | Glanceable control surface | Display + Rotary + Touch + LEDs | Custom PlatformIO |
| **Cardputer** | Portable | Text pager | Keyboard + Display | Bruce fork |
| Google/Alexa | Various | Secondary voice | Voice | Native |

### Device Specifications

#### M5Stack Module-LLM (AX630C) - Edge AI Brain
- **SoC:** AX630C with 3.2 TOPS (INT8) / 12.8 TOPS (INT4) NPU
- **Memory:** 4GB LPDDR4 (1GB user, 3GB NPU-dedicated)
- **Storage:** 32GB eMMC
- **Power:** ~1.5W operating
- **Price:** $49.90
- **Built-in AI Models:**
  - **KWS:** Wake word detection
  - **ASR:** Whisper (tiny/base) for speech-to-text
  - **LLM:** Qwen2.5-0.5B/1.5B, Llama-3.2-1B, DeepSeek-R1-distill
  - **TTS:** MeloTTS for text-to-speech
  - **Vision:** YOLO11, InternVL2, CLIP
- **Framework:** StackFlow (Arduino/UiFlow compatible)
- **Reference:** https://docs.m5stack.com/en/module/Module-LLM

**Use with AtomS3R:** Module-LLM provides the AI brain while AtomS3R provides camera, mic, and speaker. Combined, they create a fully offline ambient AI device capable of:
- Local wake word → Whisper STT → LLM response → TTS output
- Visual recognition without cloud dependency
- ~2W total power consumption

#### M5Stack AtomS3R-CAM AI Chatbot Kit
- **Processor:** ESP32-S3 @ 240MHz
- **Memory:** 8MB Flash + 8MB PSRAM
- **Camera:** GC0308 0.3MP
- **Mic:** MSM381A3729H9BPC (≥65dB SNR)
- **Speaker:** 1W @ 8Ω (ES8311 codec)
- **Extras:** 9-axis IMU (BMI270), IR emitter
- **Reference:** https://shop.m5stack.com/products/atoms3r-cam-ai-chatbot-kit-8mb-psram

#### M5Stack Cardputer
- **Processor:** ESP32-S3 @ 240MHz
- **Memory:** 8MB Flash + 8MB PSRAM
- **Display:** 1.14" TFT
- **Input:** 56-key keyboard
- **Audio:** Mic + Speaker
- **Reference:** https://shop.m5stack.com/products/m5stack-cardputer-kit-w-m5stamps3

#### Elecrow CrowPanel Status Puck
- **Processor:** ESP32-S3 dual-core @ 240MHz
- **Memory:** 8MB PSRAM + 16MB Flash
- **Display:** 1.28" round IPS, 240×240, capacitive touch
- **Input:** Rotary encoder + push button + side button + touch
- **Feedback:** 5× RGB LEDs (WS2812) + buzzer + vibration motor
- **Extras:** RTC (BM8563)
- **Reference:** esp32-status-puck/README.md

#### Home Assistant Voice PE
- **Platform:** Home Assistant native
- **Wake word:** Always-on, low power
- **LED ring:** Visual feedback
- **Integration:** Native Assist pipeline
- **Reference:** https://www.home-assistant.io/voice-pe/

---

## Edge vs Cloud AI Strategy

The Module-LLM enables a **hybrid edge/cloud architecture** where simple queries stay local and complex tasks go to Claude.

### Processing Tiers

| Tier | Processor | Latency | Use Cases |
|------|-----------|---------|-----------|
| **Edge (Module-LLM)** | Qwen2.5-1.5B | <500ms | Wake word, simple Q&A, status queries, TTS |
| **Local (Ollama)** | Llama 3.2 7B | 1-3s | Complex reasoning, code review |
| **Cloud (Claude)** | Claude Opus/Sonnet | 2-5s | Code generation, multi-file edits, planning |

### Query Routing Logic

```
User speaks → Module-LLM (wake word + Whisper STT)
    ↓
"Hey Claude, what time is it?"
    ↓
Module-LLM Qwen: Simple query → Local response → TTS
    (No network needed, <1s total)

"Hey Claude, fix the auth bug in login.py"
    ↓
Module-LLM: Complex query → MQTT → claudecodeui → Claude API
    (Cloud processing, 3-5s total)
```

### Benefits

- **Privacy:** Voice never leaves device for simple queries
- **Speed:** Sub-second response for common questions
- **Reliability:** Works during internet outages
- **Cost:** Reduces Claude API calls by ~60% (estimated)

### Module-LLM + AtomS3R Stack

```
┌─────────────────────────────────────────┐
│           AtomS3R-CAM                   │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ │
│  │ Camera  │ │   Mic   │ │ Speaker  │ │
│  │ GC0308  │ │ MSM381A │ │  ES8311  │ │
│  └────┬────┘ └────┬────┘ └────┬─────┘ │
│       │          │           │        │
│       └──────────┼───────────┘        │
│                  │ I2S/I2C            │
│       ┌──────────▼───────────┐        │
│       │      ESP32-S3        │        │
│       │   (coordinator)      │        │
│       └──────────┬───────────┘        │
└──────────────────┼────────────────────┘
                   │ UART/SPI
┌──────────────────▼────────────────────┐
│           Module-LLM                   │
│  ┌─────────────────────────────────┐  │
│  │         AX630C SoC              │  │
│  │  ┌─────┐ ┌─────┐ ┌─────┐       │  │
│  │  │ KWS │ │ ASR │ │ LLM │       │  │
│  │  │     │ │Whisper│Qwen │       │  │
│  │  └─────┘ └─────┘ └─────┘       │  │
│  │  ┌─────┐ ┌─────┐ ┌─────┐       │  │
│  │  │ TTS │ │Vision│ │ NPU │       │  │
│  │  │Melo │ │YOLO │ │3.2T │       │  │
│  │  └─────┘ └─────┘ └─────┘       │  │
│  └─────────────────────────────────┘  │
│           ~1.5W total                  │
└────────────────────────────────────────┘
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLOUD / REMOTE                                  │
│  ┌─────────────────┐                           ┌─────────────────┐          │
│  │   Claude API    │                           │   Work Mac      │          │
│  │   (Anthropic)   │                           │ claude-code-webui          │
│  └────────┬────────┘                           │   :3000 (on/off)│          │
│           │                                    └────────┬────────┘          │
└───────────┼────────────────────────────────────────────┼────────────────────┘
            │ API calls                                  │ Tailscale
            │                                            │
┌───────────┼────────────────────────────────────────────┼────────────────────┐
│           │              HOME NETWORK                  │                    │
│           │                                            │                    │
│  ┌────────▼────────┐                          ┌───────▼────────┐           │
│  │  K8s Pod        │                          │   Tailscale    │           │
│  │ claudecodeui     │                          │   (VPN mesh)   │           │
│  │  :3000 (always on)                         └────────────────┘           │
│  │ claude.app.homelab                                                       │
│  │ (homeiac fork)   │                                                       │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           │ PUBLISH status/events                                           │
│           ▼                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      MQTT BROKER (Mosquitto)                          │  │
│  │                        mqtt.homelab:1883                              │  │
│  │                                                                        │  │
│  │  Topics:                                                               │  │
│  │  ├─ claude/home/status        ← Server status (sessions, git, etc.)   │  │
│  │  ├─ claude/home/task/+        ← Task start/complete/fail events       │  │
│  │  ├─ claude/home/notification  ← Alerts requiring attention            │  │
│  │  ├─ claude/work/status        ← Work server status (when online)      │  │
│  │  ├─ claude/work/task/+        ← Work task events                      │  │
│  │  ├─ claude/command            ← Commands TO Claude (from devices)     │  │
│  │  ├─ frigate/events            ← Person/face detection (existing)      │  │
│  │  └─ homeassistant/+           ← HA state changes (existing)           │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│           │                                                                 │
│           │ SUBSCRIBE (real-time push)                                      │
│           ▼                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                     HOME ASSISTANT (Orchestrator)                     │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │  │
│  │  │ Claude Code │  │   Frigate   │  │   Ollama    │  │  Presence   │ │  │
│  │  │ Integration │  │ Face Detect │  │  Local LLM  │  │  Detection  │ │  │
│  │  │ (MQTT sub)  │  │ (MQTT pub)  │  │             │  │             │ │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│           │                                                                 │
│           │ MQTT (lightweight, real-time)                                   │
│           ▼                                                                 │
│  ┌────────────────┐ ┌──────────────┐ ┌────────────────┐ ┌──────────────┐  │
│  │   Voice PE     │ │   AtomS3R    │ │  Status Puck   │ │  Cardputer   │  │
│  │ ────────────── │ │ ──────────── │ │ ────────────── │ │ ──────────── │  │
│  │ SUB:           │ │ SUB:         │ │ SUB:           │ │ SUB:         │  │
│  │ • notification │ │ • status     │ │ • status       │ │ • status     │  │
│  │ • task/done    │ │ • task/+     │ │ • task/+       │ │ • task/+     │  │
│  │                │ │ • frigate    │ │ • notification │ │ • notif      │  │
│  │ PUB:           │ │ PUB:         │ │ PUB:           │ │ PUB:         │  │
│  │ • command      │ │ • command    │ │ • command      │ │ • command    │  │
│  │ (via HA)       │ │ • presence   │ │ • ack          │ │              │  │
│  └────────────────┘ └──────────────┘ └────────────────┘ └──────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Two Server Model

#### Home Server (Always On)
- **Location:** K8s pod on pumped-piglet-gpu
- **URL:** `claude.app.homelab` (Traefik ingress)
- **Purpose:** Primary Claude Code interface for home projects
- **Availability:** 24/7
- **Workdir:** `/home/code` (home repo mounted)

#### Work Server (On-Demand)
- **Location:** Work Mac (local)
- **URL:** `localhost:3000` or via Tailscale
- **Purpose:** Work projects (separate context)
- **Availability:** When Mac is on and logged in
- **Connection:** Tailscale mesh VPN

#### Server Discovery Configuration
```yaml
servers:
  - name: "home"
    url: "http://claude.app.homelab"
    icon: "🏠"
    always_on: true

  - name: "work"
    url: "http://100.x.x.x:3000"  # Tailscale IP
    icon: "💼"
    always_on: false
    fallback_message: "Work Mac is offline"
```

---

## MQTT Topic Schema

### Status Messages

```yaml
# claude/{server}/status - Published every 30s + on change (retained)
topic: claude/home/status
qos: 1
retain: true
payload:
  server: "home"           # enum: home, work
  online: true             # boolean
  sessions: 2              # integer >= 0
  git_dirty: 1             # integer >= 0
  active_task: "Running pytest"  # string | null
  last_activity: "2025-12-14T10:30:00Z"  # ISO 8601
```

### Task Events

```yaml
# claude/{server}/task/{task_id} - Published on state change
topic: claude/home/task/abc123
qos: 1
retain: false
payload:
  event: "completed"       # enum: started, completed, failed, waiting
  task_id: "abc123"        # string
  description: "pytest tests/"  # string
  duration_ms: 45000       # integer (on complete)
  error: null              # string | null (on fail)
```

### Notifications

```yaml
# claude/{server}/notification - High priority alerts
topic: claude/home/notification
qos: 1
retain: true
payload:
  priority: "critical"     # enum: critical, warning, info
  title: "Deploy failed"   # string
  message: "K8s rollout timed out"  # string
  actions: ["retry", "rollback", "dismiss"]  # array<string>
```

### Commands

```yaml
# claude/command - Commands TO Claude (from devices)
topic: claude/command
qos: 1
retain: false
payload:
  source: "voice_pe"       # enum: voice_pe, atoms3r, puck, cardputer
  server: "home"           # enum: home, work
  type: "chat"             # enum: chat, action, ack, refresh
  message: "What's the git status?"  # string (for chat)
  action: null             # string (for action)
  task_id: null            # string (for ack)
```

### Presence Events

```yaml
# presence/atoms3r/detected - Face/person detection
topic: presence/atoms3r/detected
qos: 0
retain: false
payload:
  person: "G"              # string: name or "unknown"
  confidence: 0.95         # float 0-1
  camera: "living_room"    # string
  timestamp: "2025-12-14T10:30:00Z"  # ISO 8601
```

---

## Data Flows

### Use Case P0-1: Ask Claude from anywhere (Voice PE)

```
Voice PE → "Hey Claude, what's the git status?"
    ↓
Home Assistant (Assist pipeline)
    ↓
HA publishes → MQTT: claude/command
    { source: "voice_pe", server: "home", type: "chat", message: "git status" }
    ↓
claudecodeui (subscribed) → Claude CLI → Claude API
    ↓
claudecodeui publishes → MQTT: claude/home/response
    { response: "3 uncommitted files", tts: true }
    ↓
HA (subscribed) → TTS → Voice PE speaks response
```

### Use Case P1-3: Proactive briefing on entry (AtomS3R)

```
AtomS3R Camera → Local face detection OR
Frigate → MQTT: frigate/events → "G detected in living_room"
    ↓
Home Assistant Automation triggers (MQTT subscription)
    ↓
HA checks retained MQTT topics:
  - claude/home/status → { git_dirty: 2 }
  - claude/home/notification → { priority: "warning", title: "K8s alert" }
    ↓
HA publishes → MQTT: atoms3r/speak
    { message: "Welcome back. 2 uncommitted files, and K8s has a warning." }
    ↓
AtomS3R (subscribed) → speaks message
```

### Use Case P1-5: Glanceable status (Puck)

```
Puck boots → Subscribes to MQTT topics:
  - claude/home/status (retained)
  - claude/work/status (retained)
  - claude/+/task/+
  - claude/+/notification
    ↓
Instant update on any publish (no polling!)
    ↓
Display: Session count, git dirty count, last task
LED ring: Green (healthy) / Amber (issues) / Red (critical)
    ↓
User rotates → Switch view between Home/Work
User taps → Publish MQTT: claude/command { type: "refresh" }
User long-press → Publish MQTT: claude/command { type: "ack", ... }
```

### Use Case P0-2: Know when Claude is done (All devices)

```
claudecodeui → Task completes (WebSocket event)
    ↓
Publishes → MQTT: claude/home/task/abc123
    { event: "completed", description: "pytest passed", duration_ms: 45000 }
    ↓
ALL subscribed devices receive instantly:
  - Puck: LED flash green, display "✓ pytest (45s)"
  - Voice PE: "Claude finished pytest, all tests passed"
  - AtomS3R: Speaks if user present
  - Cardputer: Buzz + display notification
```

---

## Firmware Strategy

| Device | Firmware Approach | Rationale |
|--------|-------------------|-----------|
| **Status Puck** | Custom PlatformIO | Existing codebase in `esp32-status-puck/firmware/` |
| **AtomS3R-CAM** | Custom PlatformIO | Need camera + audio + MQTT integration |
| **Cardputer** | **Fork Bruce** (MVP) | Already has keyboard, WiFi, UI - add MQTT module |
| **Voice PE** | HA Native | Already works with Home Assistant Assist |

### Cardputer: Bruce Fork Strategy

**Why Bruce for MVP:**
- ✅ Keyboard input already working
- ✅ WiFi stack ready
- ✅ Display/UI framework
- ✅ Menu system
- ✅ M5Stack library integration

**What to add:**
```cpp
// Add to Bruce as a new module: src/modules/claude/claude_mqtt.cpp

class ClaudeMQTT {
  void connect(const char* broker);
  void subscribe(const char* topic);
  void publish(const char* topic, const char* payload);
  void onMessage(char* topic, byte* payload);
};

// New menu item: "Claude Code"
// - View status (subscribe claude/+/status)
// - Send command (keyboard → publish claude/command)
// - View notifications
```

**MVP Steps:**
1. Fork Bruce: `github.com/homeiac/bruce-claude`
2. Add PubSubClient library for MQTT
3. Create `src/modules/claude/` module
4. Add "Claude Code" to main menu
5. Test: Send text command, receive status

**Reference:** https://github.com/pr3y/Bruce

### AtomS3R: Custom Firmware

**Why custom (not Bruce):**
- Need tight camera + audio integration
- Presence detection logic
- Different UI (no keyboard)
- Proactive behavior (not menu-driven)

**Stack:**
```
PlatformIO + Arduino
├── ESP32-S3 camera driver
├── Audio codec (ES8311)
├── PubSubClient (MQTT)
├── ArduinoJson
└── TFT_eSPI (if using display)
```

### Puck: Existing Custom Firmware

**Already have:**
- `esp32-status-puck/firmware/` - PlatformIO project
- Display driver (LovyanGFX)
- Encoder handling
- LED control

**Add:**
- PubSubClient for MQTT
- Replace HTTP polling with MQTT subscriptions
- Add command publishing on button press

---

## Testing Strategy

See [claude-code-ambient-ai-testing.md](./claude-code-ambient-ai-testing.md) for full testing documentation including:

- JSON Schema validation
- Unit tests (PlatformIO native)
- Device simulators
- MQTT failure mode tests
- E2E tests with real hardware
- Chaos testing
- BDD feature files
- Synthetic data generation

### Testing Pyramid

```
                    ┌───────────┐
                    │  Chaos    │  Weekly, blocks release
                   ┌┴───────────┴┐
                   │  E2E Real   │  Nightly, real devices
                  ┌┴─────────────┴┐
                  │  Simulators   │  Every PR, no hardware
                 ┌┴───────────────┴┐
                 │   Unit Tests    │  Every commit, < 1 min
                ┌┴─────────────────┴┐
                │  Schema Validation │  Every commit, instant
                └───────────────────┘
```

---

## Implementation Phases

### Phase 1: Foundation (P0)

1. **Fork and deploy claudecodeui to K8s**
   - Fork `siteboon/claudecodeui` → `homeiac/claudecodeui`
   - Add MQTT client to Express backend (`mqtt` npm package)
   - Hook WebSocket events → MQTT publish (task start/complete/fail)
   - Add `/api/status` REST endpoint for device polling
   - Subscribe to `claude/command` for incoming device commands
   - Dockerfile with Claude CLI + our MQTT additions
   - Traefik ingress at `claude.app.homelab`
   - PVC for session persistence (`~/.claude/projects/`)

2. **Create HA integration for Claude Code**
   - MQTT subscription for status/notifications
   - Custom conversation intent for voice commands
   - Automation for TTS responses

3. **Voice PE integration**
   - "Ask Claude" intent
   - Response via TTS

### Phase 2: Status Display (P1)

4. **Update Status Puck firmware**
   - Add MQTT client (PubSubClient)
   - Subscribe to claude/+/status, claude/+/task/+
   - Multi-server support (home/work)
   - LED status mapping

5. **Work server connectivity**
   - Tailscale setup on Work Mac
   - Run claudecodeui fork locally with MQTT publishing
   - Server health check in Puck

### Phase 3: Ambient Intelligence (P1)

6. **AtomS3R firmware**
   - MQTT client
   - Wake word detection (optional)
   - Claude Code voice commands
   - Proactive briefing on presence

7. **Presence-triggered automations**
   - Frigate face detection → HA automation
   - Context-aware alert prioritization

### Phase 4: Enhanced Features (P2-P3)

8. **Cardputer text interface**
   - Fork Bruce, add Claude module
   - MQTT publish/subscribe

9. **Camera vision input (AtomS3R)**
   - Capture image on command
   - Send to Claude via multimodal API

10. **Unknown person alerts**
    - Frigate unknown face → critical notification

11. **Cross-device handoff**
    - Context sync between devices

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Voice command response time | < 5 seconds |
| Status update latency | < 1 second (MQTT) |
| Device reconnection time | < 10 seconds after broker restart |
| Battery life (Cardputer) | > 4 hours active use |
| Face detection accuracy | > 90% for registered family |

### Testable Acceptance Criteria

| Test | Method | Expected |
|------|--------|----------|
| MQTT broker up | `mosquitto_pub/sub` | Messages flow |
| Puck receives status | Publish to `claude/home/status` | Display updates in < 1s |
| Puck handles offline | Publish `{"online":false}` | Shows "offline" gracefully |
| Voice PE speaks | Publish to response topic | TTS output |
| AtomS3R presence | Walk in front | MQTT message published |
| E2E voice command | Say command | Response spoken in < 5s |

---

## Related Documentation

- [ESP32 Status Puck Architecture](../../esp32-status-puck/docs/architecture.md)
- [ESP32 Status Puck Design](../../esp32-status-puck/docs/design.md)
- [AI-First Homelab Architecture](../../AI_FIRST_HOMELAB_ARCHITECTURE.md)
- [Homelab Service Inventory](../reference/homelab-service-inventory.md)

---

## Tags

claude-code, ambient-ai, mqtt, esp32, voice-assistant, atoms3r, cardputer, status-puck, voice-pe, home-assistant, frigate, presence-detection, proactive-alerts
