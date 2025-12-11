# The Silent Bug: How Home Assistant's Automation Mode Killed My Package Notifications

*A tale of debugging smart home automations with AI assistance and bringing OpenTelemetry-style observability to Home Assistant*

---

## The Setup

I built what I thought was a clever package detection system for my smart home. The architecture was straightforward:

1. Reolink doorbell detects a person
2. LLM Vision (Ollama + llava:7b) analyzes the camera snapshot
3. When the person leaves, check if they left a package
4. If yes: turn on a blue LED on my Home Assistant Voice PE device and send a notification

The system had two triggers working in harmony:
- `person_arrived`: Capture who's at the door, describe them via LLM
- `person_left`: Check if a package was left behind

Simple, right?

## The Problem

**The blue LED never turned on.** Not once. Despite many package deliveries.

The strange part? The *old* automation (a blueprint-based one) was still sending notifications with the correct detection. So the camera worked. The LLM worked. Detection worked. But my custom automation with the LED notification? Silent.

## The Investigation

Working with Claude Code, we started debugging systematically.

### First Hypothesis: Wrong Entities

I noticed there were two sets of camera entities:
- `camera.reolink_video_doorbell_wifi_fluent` (direct Reolink integration)
- `camera.reolink_doorbell` (Frigate integration)

Similarly, two person sensors existed. Maybe I was using the wrong one?

We tested the camera:

```bash
# Take a snapshot and analyze it
curl -X POST "$HA_URL/api/services/camera/snapshot" \
  -d '{"entity_id": "camera.reolink_video_doorbell_wifi_fluent", ...}'

# Ask LLM to describe what it sees
curl -X POST "$HA_URL/api/services/llmvision/image_analyzer?return_response" \
  -d '{"image_file": "/config/www/tmp/test_snapshot.jpg", ...}'
```

Response: *"The image shows a residential scene with a focus on a front porch area. There is a wooden archway leading to the porch..."*

The camera worked perfectly. Dead end.

### Second Hypothesis: LLM Not Detecting Packages

We checked the current notification state:

```json
{
  "pending_notification_message": "Visitor at 02:15 PM: Unknown person, no package visible.",
  "pending_notification_type": "visitor"
}
```

The notification type was "visitor", not "package". The `person_arrived` branch was executing, but the `person_left` branch (which checks for packages and turns on the LED) apparently wasn't.

### The Eureka Moment

Looking at the automation configuration:

```yaml
mode: single  # <-- THE CULPRIT

triggers:
  - platform: state
    entity_id: binary_sensor.reolink_video_doorbell_wifi_person
    from: "off"
    to: "on"
    id: person_arrived

  - platform: state
    entity_id: binary_sensor.reolink_video_doorbell_wifi_person
    from: "on"
    to: "off"
    for:
      seconds: 3
    id: person_left
```

**`mode: single`** means only ONE instance of the automation can run at a time.

Here's what was happening:

```
Timeline:
0s    - Person arrives → triggers person_arrived
0s    - Automation starts running (mode: single = locked)
2s    - Delay in automation
3s    - Taking snapshot...
5s    - Calling LLM... (takes 5-15 seconds)
10s   - Person leaves → person_left trigger FIRES
        BUT automation is still running!
        mode: single = trigger is BLOCKED
15s   - Automation finishes person_arrived branch
        person_left event is gone, never processed
```

The `person_arrived` branch took ~15-20 seconds (2s delay + snapshot + LLM call + notifications). During that time, the delivery person left (typically 7-25 seconds on the porch). The `person_left` trigger fired, but was silently discarded because `mode: single` only allows one execution at a time.

**The package check never ran. The LED never turned on.**

## The Fix

Change one line:

```yaml
mode: queued  # Allow triggers to queue up
```

With `mode: queued`, when `person_left` fires while `person_arrived` is still running, it queues up and executes after.

## But Wait, There's More: Observability

Debugging this took way too long. The real problem wasn't just the bug—it was the lack of visibility. Home Assistant's logbook is basic. There's no way to trace a single automation execution through its steps.

So we added OpenTelemetry-style tracing.

### The Tracing Pattern

Every automation execution now generates a unique trace ID and logs structured events:

```yaml
actions:
  # Generate trace context
  - variables:
      trace_id: "{{ now().strftime('%H%M%S') }}-{{ range(1000,9999) | random }}"
      trigger_name: "{{ trigger.id }}"
      start_time: "{{ now().isoformat() }}"

  # TRACE START
  - action: logbook.log
    data:
      name: "Package Detection"
      message: "[PKG-{{ trace_id }}] TRACE_START | trigger={{ trigger_name }}"

  # ... automation logic with EVENT logs ...

  # TRACE END with duration
  - action: logbook.log
    data:
      name: "Package Detection"
      message: "[PKG-{{ trace_id }}] TRACE_END | duration={{ (now() - as_datetime(start_time)).total_seconds() | round(1) }}s"
```

### What the Logs Look Like Now

```
[PKG-143052-7842] TRACE_START | trigger=person_arrived | time=2025-12-11T14:30:52
[PKG-143052-7842] SPAN_START:visitor_analysis | Waiting 2s for person to settle
[PKG-143052-7842] EVENT:snapshot | file=doorbell_visitor.jpg
[PKG-143052-7842] EVENT:llm_call | model=llava:7b | prompt=describe_visitor
[PKG-143052-7842] EVENT:llm_response | result=Amazon delivery person holding package
[PKG-143052-7842] SPAN_END:visitor_analysis | status=complete
[PKG-143052-7842] TRACE_END | trigger=person_arrived | duration=12.3s

[PKG-143105-2341] TRACE_START | trigger=person_left | time=2025-12-11T14:31:05
[PKG-143105-2341] SPAN_START:package_check | Person left, checking for packages
[PKG-143105-2341] EVENT:snapshot | file=doorbell_after.jpg
[PKG-143105-2341] EVENT:llm_call | model=llava:7b | prompt=package_check
[PKG-143105-2341] EVENT:llm_response | result=YES | package_detected=True
[PKG-143105-2341] EVENT:package_confirmed | Activating LED and notifications
[PKG-143105-2341] EVENT:led_on | entity=voice_pe_led | color=blue
[PKG-143105-2341] SPAN_END:package_check | status=PACKAGE_DETECTED | led=ON
[PKG-143105-2341] TRACE_END | trigger=person_left | duration=8.7s
```

Now I can:
- **Correlate events** by trace ID
- **See timing** for each span
- **Track decisions** (package_detected=True/False)
- **Debug failures** by finding where the trace stops

## Lessons Learned

### 1. Automation Mode Matters

Home Assistant automation modes:

| Mode | Behavior |
|------|----------|
| `single` | Only one instance runs. New triggers are **dropped**. |
| `restart` | New trigger **kills** current execution and starts fresh. |
| `queued` | New triggers **wait** for current execution to finish. |
| `parallel` | Multiple instances run **simultaneously**. |

For automations with multiple triggers that should ALL execute, use `queued` or `parallel`.

### 2. Silent Failures Are the Worst

The automation wasn't failing—it was succeeding at the wrong thing. `mode: single` with `max_exceeded: silent` meant triggers were being dropped with no indication whatsoever.

If I had logs showing "person_left trigger received but blocked by running instance", I would have found this in minutes, not hours.

### 3. Observability Isn't Just for Production Systems

We obsess over observability in cloud systems but ignore it in smart homes. Yet smart home automations are:
- Event-driven (like microservices)
- Asynchronous (triggers can overlap)
- Stateful (entities have state that changes)
- Hard to reproduce (can't easily simulate a delivery person)

They deserve the same observability patterns.

### 4. AI Assistants Excel at Systematic Debugging

Working with Claude Code, the debugging followed a clear pattern:
1. Check entity states
2. Test individual components (camera, LLM, LED)
3. Trace the execution path
4. Find the gap

The AI didn't magically know the answer—it systematically eliminated possibilities until the root cause emerged.

## The Code

The full automation with tracing is available in my homelab repo:
- `automation-package-detection-v2.yaml` - Full automation with OpenTelemetry-style logging
- `deploy-automation-v2.sh` - Deployment script via Home Assistant API

Key sections:

```yaml
# Generate trace context at start
- variables:
    trace_id: "{{ now().strftime('%H%M%S') }}-{{ range(1000,9999) | random }}"

# Log spans for major operations
- action: logbook.log
  data:
    name: "Package Detection"
    message: "[PKG-{{ trace_id }}] SPAN_START:package_check"

# Log events for important actions
- action: logbook.log
  data:
    name: "Package Detection"
    message: "[PKG-{{ trace_id }}] EVENT:led_on | entity=voice_pe_led | color=blue"
```

## Conclusion

A one-word fix (`single` → `queued`) solved the immediate problem. But the real win was adding observability that will make future debugging trivial.

The next time my smart home misbehaves, I won't be guessing. I'll grep the logs for `[PKG-` and follow the trace.

---

*This debugging session was conducted with Claude Code, Anthropic's AI coding assistant. The automation runs on Home Assistant with Ollama for local LLM inference and a Reolink doorbell for video capture.*
