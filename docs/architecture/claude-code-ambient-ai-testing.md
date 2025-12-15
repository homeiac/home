# Claude Code Ambient AI - Testing Strategy

**Version:** 1.1
**Status:** Draft
**Last Updated:** 2025-12-14

---

## Web UI Under Test: claudecodeui (homeiac fork)

Our fork of [siteboon/claudecodeui](https://github.com/siteboon/claudecodeui) adds MQTT integration.
See [claude-code-ambient-ai.md](./claude-code-ambient-ai.md) for architecture details.

### Components to Test

| Component | Type | Test Approach |
|-----------|------|---------------|
| MqttBridge.js | Node.js module | Jest unit tests |
| WebSocket → MQTT hooks | Integration | Mock MQTT broker |
| `/api/status` endpoint | REST API | Supertest |
| Device firmware | C++ | PlatformIO native tests |
| End-to-end flow | Full stack | Real MQTT + simulators |

---

## Principles

1. **If it's not automated, it's not a test.**
2. **Specs before code.** Write BDD features first, then implement.
3. **Synthetic data drives everything.** No "manual verify" - data proves it works.

---

## Testing Pyramid

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

## Layer 0: Contract Testing (Schema Validation)

### JSON Schema for MQTT Topics

All MQTT messages must conform to JSON schemas. Schema validation runs on every publish.

**Location:** `schemas/`

```json
// schemas/claude-status.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["server", "online", "sessions", "git_dirty"],
  "properties": {
    "server": { "enum": ["home", "work"] },
    "online": { "type": "boolean" },
    "sessions": { "type": "integer", "minimum": 0 },
    "git_dirty": { "type": "integer", "minimum": 0 },
    "active_task": { "type": ["string", "null"] },
    "last_activity": { "type": "string", "format": "date-time" }
  },
  "additionalProperties": false
}
```

### Schema Validator

```bash
# scripts/mqtt-validator.py
# Subscribes to all topics, validates against schema, FAILS LOUD
python3 scripts/mqtt-validator.py --schema-dir schemas/ --broker mqtt.homelab
# Exit code 1 on ANY schema violation
```

**CI Gate:** No merge without schema validation passing.

---

## Layer 1: Unit Tests

### Puck Firmware Unit Tests

**Location:** `esp32-status-puck/firmware/test/`

```cpp
// test_mqtt_parser.cpp

void test_parse_valid_status() {
    const char* json = R"({"server":"home","online":true,"sessions":2,"git_dirty":1})";
    ClaudeStatus status;
    bool result = parse_claude_status(json, &status);

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_EQUAL_STRING("home", status.server);
    TEST_ASSERT_EQUAL(2, status.sessions);
}

void test_parse_malformed_json() {
    const char* json = R"({"server":"home", broken)";
    ClaudeStatus status;
    bool result = parse_claude_status(json, &status);

    TEST_ASSERT_FALSE(result);  // Must not crash!
}

void test_parse_missing_required_field() {
    const char* json = R"({"server":"home","online":true})";  // missing sessions
    ClaudeStatus status;
    bool result = parse_claude_status(json, &status);

    TEST_ASSERT_FALSE(result);
}

void test_parse_unknown_server() {
    const char* json = R"({"server":"unknown","online":true,"sessions":0,"git_dirty":0})";
    ClaudeStatus status;
    bool result = parse_claude_status(json, &status);

    TEST_ASSERT_FALSE(result);  // Reject unknown servers
}

void test_led_color_for_status() {
    TEST_ASSERT_EQUAL(LED_GREEN, get_led_color(0, 0, false));   // healthy
    TEST_ASSERT_EQUAL(LED_AMBER, get_led_color(2, 0, false));   // dirty repos
    TEST_ASSERT_EQUAL(LED_RED, get_led_color(0, 0, true));      // critical alert
}

void test_display_truncation() {
    char buffer[20];
    truncate_task_name("This is a very long task name that won't fit", buffer, 20);
    TEST_ASSERT_EQUAL_STRING("This is a very lo...", buffer);
}
```

**Run:** `cd esp32-status-puck/firmware && pio test -e native`

### Bruce/Cardputer Unit Tests

**Location:** `bruce-claude/test/`

```cpp
// test_claude_module.cpp

void test_command_serialization() {
    ClaudeCommand cmd = {
        .source = "cardputer",
        .server = "home",
        .type = CMD_CHAT,
        .message = "git status"
    };
    char buffer[256];
    serialize_command(&cmd, buffer, sizeof(buffer));

    TEST_ASSERT_EQUAL_STRING(
        R"({"source":"cardputer","server":"home","type":"chat","message":"git status"})",
        buffer
    );
}

void test_keyboard_to_command() {
    const char* input = "what is the git status?\n";
    ClaudeCommand cmd;
    bool result = keyboard_input_to_command(input, &cmd);

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_EQUAL(CMD_CHAT, cmd.type);
    TEST_ASSERT_EQUAL_STRING("what is the git status?", cmd.message);
}
```

### claudecodeui Backend Tests (Jest)

**Location:** `claudecodeui/server/__tests__/`

```javascript
// mqtt-bridge.test.js

const MqttBridge = require('../mqtt-bridge');
const mqtt = require('mqtt');

jest.mock('mqtt');

describe('MqttBridge', () => {
  let bridge;
  let mockClient;

  beforeEach(() => {
    mockClient = {
      on: jest.fn(),
      publish: jest.fn(),
      subscribe: jest.fn(),
    };
    mqtt.connect.mockReturnValue(mockClient);
    bridge = new MqttBridge({ broker: 'mqtt://test', serverName: 'home' });
  });

  describe('publishStatus', () => {
    it('publishes status with correct topic and retain flag', () => {
      bridge.client = mockClient;
      bridge.publishStatus({ sessions: 2, git_dirty: 1 });

      expect(mockClient.publish).toHaveBeenCalledWith(
        'claude/home/status',
        expect.stringContaining('"server":"home"'),
        { retain: true, qos: 1 }
      );
    });

    it('includes ISO timestamp in last_activity', () => {
      bridge.client = mockClient;
      bridge.publishStatus({});

      const call = mockClient.publish.mock.calls[0];
      const payload = JSON.parse(call[1]);
      expect(payload.last_activity).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    });
  });

  describe('publishTaskEvent', () => {
    it('publishes task event with task_id in topic', () => {
      bridge.client = mockClient;
      bridge.publishTaskEvent('completed', 'task_123', 'pytest passed', { duration_ms: 5000 });

      expect(mockClient.publish).toHaveBeenCalledWith(
        'claude/home/task/task_123',
        expect.stringContaining('"event":"completed"'),
        { qos: 1 }
      );
    });
  });

  describe('handleCommand', () => {
    it('emits command event for chat type', () => {
      const listener = jest.fn();
      bridge.on('command', listener);

      bridge.handleCommand({
        source: 'voice_pe',
        server: 'home',
        type: 'chat',
        message: 'git status'
      });

      expect(listener).toHaveBeenCalledWith(expect.objectContaining({
        type: 'chat',
        message: 'git status'
      }));
    });
  });
});
```

**Run:** `cd claudecodeui && npm test`

### claudecodeui API Tests (Supertest)

```javascript
// api.test.js

const request = require('supertest');
const app = require('../app');

describe('GET /api/status', () => {
  it('returns current server status', async () => {
    const res = await request(app).get('/api/status');

    expect(res.statusCode).toBe(200);
    expect(res.body).toHaveProperty('server');
    expect(res.body).toHaveProperty('sessions');
    expect(res.body).toHaveProperty('git_dirty');
  });

  it('includes online flag', async () => {
    const res = await request(app).get('/api/status');

    expect(res.body.online).toBe(true);
  });
});

describe('POST /api/command', () => {
  it('accepts chat command and returns task_id', async () => {
    const res = await request(app)
      .post('/api/command')
      .send({ type: 'chat', message: 'git status' });

    expect(res.statusCode).toBe(202);
    expect(res.body).toHaveProperty('task_id');
  });
});
```

---

## Layer 2: MQTT Failure Mode Tests

**Location:** `tests/test_mqtt_resilience.py`

```python
import pytest
import paho.mqtt.client as mqtt
import subprocess
import time

class TestMQTTResilience:

    def test_reconnect_after_broker_restart(self, device_simulator):
        """Device must reconnect and resubscribe after broker restarts"""
        device_simulator.connect()
        assert device_simulator.is_connected()

        # Kill broker
        subprocess.run(["docker", "restart", "mosquitto"])
        time.sleep(2)

        # Device should reconnect within 10s
        time.sleep(10)
        assert device_simulator.is_connected()

        # Verify resubscribed
        test_msg = {"sessions": 99, "git_dirty": 0, "server": "home", "online": True}
        publish("claude/home/status", test_msg)
        assert device_simulator.received_status(timeout=5)

    def test_retained_message_on_reconnect(self, device_simulator):
        """Device must receive retained message immediately on connect"""
        publish("claude/home/status", VALID_STATUS, retain=True)
        device_simulator.connect()

        msg = device_simulator.wait_for_message("claude/home/status", timeout=1)
        assert msg is not None

    def test_handles_stale_retained_message(self, device_simulator):
        """Device must handle retained message with old timestamp"""
        old_status = {**VALID_STATUS, "last_activity": "2020-01-01T00:00:00Z"}
        publish("claude/home/status", old_status, retain=True)

        device_simulator.connect()
        time.sleep(2)

        assert device_simulator.display_shows("stale") or device_simulator.display_shows("?")

    def test_qos1_delivery_guarantee(self, device_simulator):
        """Critical notifications must use QoS 1"""
        device_simulator.connect()
        device_simulator.add_latency(500)

        publish("claude/home/notification", {"priority": "critical", "title": "Test"}, qos=1)

        msg = device_simulator.wait_for_message("claude/home/notification", timeout=5)
        assert msg is not None

    def test_handles_message_flood(self, device_simulator):
        """Device must not crash under message flood"""
        device_simulator.connect()

        for i in range(100):
            publish(f"claude/home/task/flood_{i}", {"event": "started"})

        time.sleep(2)
        assert device_simulator.is_connected()
        assert device_simulator.responds_to_ping()
```

---

## Layer 3: Device Simulators

### Puck Simulator

**Location:** `tests/simulators/puck_simulator.py`

```python
class PuckSimulator:
    """Simulates Puck firmware behavior for testing"""

    def __init__(self):
        self.display_content = ""
        self.led_color = None
        self.mqtt_client = mqtt.Client()

    def connect(self, broker="mqtt.homelab"):
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.connect(broker)
        self.mqtt_client.subscribe([
            ("claude/+/status", 1),
            ("claude/+/task/+", 0),
            ("claude/+/notification", 1),
        ])
        self.mqtt_client.loop_start()

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
            if "status" in msg.topic:
                self._handle_status(payload)
            elif "notification" in msg.topic:
                self._handle_notification(payload)
        except json.JSONDecodeError:
            self.display_content = "JSON ERROR"

    def _handle_status(self, status):
        self.display_content = f"{status['sessions']} sessions, {status['git_dirty']} dirty"
        if status.get('git_dirty', 0) == 0:
            self.led_color = "green"
        elif status.get('git_dirty', 0) < 3:
            self.led_color = "amber"
        else:
            self.led_color = "red"

    def simulate_button_press(self):
        self.mqtt_client.publish("claude/command", json.dumps({
            "source": "puck", "type": "refresh"
        }))

    def display_shows(self, text):
        return text in self.display_content

    def led_is(self, color):
        return self.led_color == color
```

**Run:** `pytest tests/test_puck_behavior.py -v`

---

## Layer 4: E2E Tests with Real Devices

### Device Test Harness

**Location:** `tests/e2e/test_harness.py`

```python
class DeviceTestHarness:
    """Controls real devices via serial + monitors MQTT"""

    def __init__(self, device_port="/dev/ttyUSB0"):
        self.serial = serial.Serial(device_port, 115200)
        self.mqtt = mqtt.Client()

    def send_command(self, cmd):
        self.serial.write(f"TEST:{cmd}\n".encode())

    def verify_led_color(self):
        self.send_command("GET_LED")
        return self.wait_for_output("LED:")

    def verify_display_content(self):
        self.send_command("GET_DISPLAY")
        return self.wait_for_output("DISPLAY:")
```

### Firmware Test Mode

```cpp
// In firmware: test interface over serial
void handle_test_command(const char* cmd) {
    if (strcmp(cmd, "GET_LED") == 0) {
        Serial.printf("LED:%s\n", led_color_to_string(current_led_color));
    }
    else if (strcmp(cmd, "GET_DISPLAY") == 0) {
        Serial.printf("DISPLAY:%s\n", current_display_text);
    }
    else if (strcmp(cmd, "SIMULATE_BUTTON") == 0) {
        handle_button_press();
    }
}
```

### E2E Test Example

```python
def test_status_updates_display(device_harness, mqtt_client):
    mqtt_client.publish("claude/home/status", json.dumps({
        "server": "home", "online": True, "sessions": 5, "git_dirty": 2
    }), retain=True)

    time.sleep(1)

    display = device_harness.verify_display_content()
    assert "5 sessions" in display
    assert "2 dirty" in display

    led = device_harness.verify_led_color()
    assert led == "amber"
```

---

## Layer 5: Chaos Testing

**Location:** `tests/chaos/test_chaos.py`

```python
def test_broker_dies_mid_conversation(all_devices, mqtt_broker):
    """System recovers when broker dies during active use"""
    all_devices.connect()
    publish_status({"sessions": 1})
    time.sleep(1)

    mqtt_broker.kill()
    time.sleep(5)
    mqtt_broker.start()
    time.sleep(10)

    for device in all_devices:
        assert device.is_connected()

    publish_status({"sessions": 2})
    time.sleep(2)
    for device in all_devices:
        assert device.received_latest_status()

def test_wifi_flap(puck_device):
    """Device handles WiFi disconnect/reconnect"""
    puck_device.connect()
    puck_device.send_command("WIFI_DISCONNECT")
    time.sleep(2)
    puck_device.send_command("WIFI_RECONNECT")
    time.sleep(10)

    assert puck_device.mqtt_connected()

    publish_status({"sessions": 99})
    time.sleep(2)
    assert puck_device.display_shows("99 sessions")
```

---

## BDD Feature Files

### Location: `features/`

```
features/
├── p0_ask_claude.feature
├── p0_task_notifications.feature
├── p1_proactive_briefing.feature
├── p2_unknown_person.feature
└── failure_handling.feature
```

### Example: P0-1 Ask Claude

```gherkin
# features/p0_ask_claude.feature

Feature: Ask Claude from anywhere
  As a user away from my laptop
  I want to ask Claude questions via voice or text
  So that I can get information without opening my computer

  Background:
    Given the MQTT broker is running
    And claude-code-webui is connected

  @voice_pe @p0
  Scenario: Ask git status via Voice PE
    Given Voice PE is connected to Home Assistant
    When I say "Hey Claude, what is the git status?"
    Then a command should be published to "claude/command" with:
      | source  | voice_pe |
      | type    | chat     |
    And within 5 seconds, Voice PE should speak the response

  @puck @p0
  Scenario: Refresh status via Puck button press
    Given Puck is displaying home server status
    When I press the encoder button
    Then a command should be published with type "refresh"
    And the LED ring should show breathing white
    And within 2 seconds, the display should update
```

### Example: Failure Handling

```gherkin
# features/failure_handling.feature

Feature: Graceful failure handling

  @resilience
  Scenario: Device handles malformed JSON
    Given Puck is connected
    When a malformed JSON message is published
    Then Puck should NOT crash
    And Puck should display "⚠ Parse error"
    And Puck should continue processing valid messages

  @resilience
  Scenario: Device reconnects after broker restart
    Given Puck is connected
    When the MQTT broker restarts
    Then Puck should reconnect within 10 seconds
    And Puck should receive retained messages again
```

### Running BDD Tests

```bash
# Run all features
behave features/

# Run specific priority
behave features/ --tags=@p0

# Generate HTML report
behave features/ --format=html --outfile=reports/bdd-report.html
```

---

## Synthetic Data Generation

### Location: `scripts/test-data/generate.py`

See full implementation in the main architecture document.

### Usage

```bash
# Generate all use case data as JSON
python scripts/test-data/generate.py --usecase all

# Publish directly to MQTT broker
python scripts/test-data/generate.py --usecase p0_1_ask_claude --output mqtt --broker mqtt.homelab
```

### Available Use Cases

| Use Case | Description |
|----------|-------------|
| `p0_1_ask_claude` | Voice command → response |
| `p0_2_task_complete` | Task started → completed |
| `p1_3_proactive_briefing` | Presence → briefing |
| `p1_5_glanceable_status` | Home healthy + work offline |
| `p2_6_unknown_person` | Unknown face → alert |
| `p3_8_cardputer_text` | Keyboard → command |
| `failure_malformed_json` | Broken JSON payload |
| `failure_stale_data` | 48-hour old message |
| `failure_work_offline` | Server unavailable |

---

## CI/CD Pipeline

**Location:** `.github/workflows/firmware-test.yml`

```yaml
name: Firmware Tests

on: [push, pull_request]

jobs:
  schema-validation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate MQTT schemas
        run: |
          pip install jsonschema
          python scripts/validate-schemas.py schemas/

  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install PlatformIO
        run: pip install platformio
      - name: Run Puck unit tests
        run: cd esp32-status-puck/firmware && pio test -e native
      - name: Run Bruce module tests
        run: cd bruce-claude && pio test -e native

  simulator-tests:
    runs-on: ubuntu-latest
    services:
      mosquitto:
        image: eclipse-mosquitto:2
        ports:
          - 1883:1883
    steps:
      - uses: actions/checkout@v4
      - name: Run simulator tests
        run: |
          pip install pytest paho-mqtt
          pytest tests/test_*_simulator.py -v

  e2e-tests:
    runs-on: self-hosted  # Has devices connected via USB
    needs: [unit-tests, simulator-tests]
    steps:
      - uses: actions/checkout@v4
      - name: Flash firmware
        run: cd esp32-status-puck/firmware && pio run -t upload
      - name: Run E2E tests
        run: pytest tests/e2e/ -v --device-port=/dev/ttyUSB0
```

---

## Test Coverage Requirements

| Layer | Coverage | Gate |
|-------|----------|------|
| Schema validation | 100% of topics | PR blocked if missing |
| Unit tests | 80% line coverage | PR blocked if < 80% |
| Simulator tests | All happy paths + error paths | PR blocked |
| E2E tests | Critical user journeys | Nightly, blocks release |
| Chaos tests | Weekly | Blocks release |

---

## TDD Workflow

```
1. WRITE FEATURE FILE (Gherkin spec)
   features/p0_ask_claude.feature

2. GENERATE SYNTHETIC DATA
   python scripts/test-data/generate.py --usecase p0_1_ask_claude

3. RUN TESTS (they fail - RED)
   behave features/p0_ask_claude.feature
   # Expected: "Step not implemented"

4. IMPLEMENT STEP DEFINITIONS
   tests/steps/mqtt_steps.py

5. IMPLEMENT FIRMWARE/CODE
   esp32-status-puck/firmware/src/mqtt_handler.cpp

6. RUN TESTS (they pass - GREEN)
   behave features/p0_ask_claude.feature

7. REFACTOR
   Clean up code while keeping tests green

8. REPEAT for next use case
```

---

## Tags

testing, bdd, tdd, mqtt, firmware, esp32, shift-left, synthetic-data, chaos-testing, ci-cd
