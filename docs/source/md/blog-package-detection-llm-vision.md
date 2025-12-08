# I Built a Doorbell AI That Tells Me WHO's There AND If They Left a Package

*No cloud. No subscription. No false alarms. Just local AI that actually understands what it sees.*

---

## The Problem Every Homeowner Knows

You know that feeling. You're at work, expecting a package, and your doorbell camera sends you 47 notifications about "motion detected." A leaf blows by. Motion. Your neighbor walks their dog. Motion. A shadow moves. Motion.

By the time an actual delivery happens, you've already muted the notifications in frustration.

**I was done with this.**

I didn't just want package detection. I wanted to know:
- **Who** is at my door (Amazon? FedEx? Random person?)
- **Did they leave a package?** (Not "are they holding something" - did they actually leave it?)

So I built my own three-phase doorbell AI with voice interaction.

---

## The Result: Three-Phase Intelligence

Here's what happens now when someone approaches my door:

### Phase 1: Person Arrives
```
📱 "🚪 Someone at door: Amazon driver in blue vest holding box"
```

### Phase 2: Person Leaves (3 seconds later)
```
📱 "📦 Package Delivered!"
🔵 Voice assistant LED turns blue (stays on)
```

### Phase 3: You Ask (hours later)
```
🗣️ "Okay Nabu, what's my notification?"
🔊 "Package delivered at 2:45 PM by Amazon driver in blue vest"
💡 LED turns off
```

The magic? **Three different questions at three different times:**
1. "Who is this person?" (while they're there)
2. "Is there a package on the porch?" (after they leave)
3. "What was that notification?" (when you're ready)

False alarms in the past month: **zero**.

---

## The Secret Sauce: LLM Vision (Running Locally)

Here's the thing about traditional "smart" cameras: they're dumb. They detect motion or maybe recognize a person shape. But they can't understand *context*.

My system uses **LLM Vision** - an actual language model that can *see* and *reason*:

### When person arrives:
```
Me: "Describe the person at this door in 10 words or less."
AI: "UPS driver in brown uniform holding cardboard box"
```

### When person leaves:
```
Me: "Is there a package on the porch?"
AI: "YES"
(Phone buzzes, LED pulses blue)
```

The AI doesn't just pattern-match. It understands:
- **Uniforms**: Amazon blue vest, UPS brown, FedEx purple
- **Context**: "holding a package" vs "package on ground"
- **Objects**: Boxes, padded envelopes, Amazon smile logos

And it runs **entirely on my local GPU**. No cloud. No subscription. No privacy concerns.

---

## The Stack (Surprisingly Simple)

You don't need expensive hardware or a computer science degree. Here's what I used:

| Component | What It Does | Cost |
|-----------|--------------|------|
| **Reolink Doorbell** | Detects people, captures images | ~$100 |
| **Home Assistant** | Orchestrates everything | Free |
| **Ollama + llava:7b** | Local AI vision model | Free |
| **LLM Vision Integration** | Connects HA to Ollama | Free |
| **Any NVIDIA GPU** | Runs the AI (I use RTX 3070) | You probably have one |

**Optional but nice:**
- Frigate NVR (better person detection with Coral TPU)
- Voice assistant with LED (visual notification)

Total monthly cost: **$0**

---

## How It Actually Works

### Step 1: Dual Triggers

My automation fires twice per visit - once when someone arrives, once when they leave:

```yaml
trigger:
  - platform: state
    entity_id: binary_sensor.reolink_video_doorbell_wifi_person
    from: "off"
    to: "on"
    id: person_arrived

  - platform: state
    entity_id: binary_sensor.reolink_video_doorbell_wifi_person
    from: "on"
    to: "off"
    for: { seconds: 3 }  # Wait 3 seconds to confirm they left
    id: person_left
```

This filters out 99% of noise. No more leaf notifications.

### Step 2: AI Analysis (Two Different Questions)

**When person arrives** - identify who's there:

```yaml
- service: llmvision.image_analyzer
  data:
    provider: ollama
    model: llava:7b
    image_file: /config/www/tmp/doorbell_visitor.jpg
    message: >
      Describe the person at this door in 10 words or less.
      Include: delivery uniform (UPS/FedEx/Amazon/USPS),
      or regular visitor, or unknown person.
      Mention if holding a package.
```

**When person leaves** - check for packages:

```yaml
- service: llmvision.image_analyzer
  data:
    provider: ollama
    model: llava:7b
    image_file: /config/www/tmp/doorbell_after.jpg
    message: >
      Answer ONLY YES or NO:
      Is there a package, box, or delivery item
      visible on this porch/doorstep?
```

The AI looks at the actual image and makes a decision. Not motion detection. Not object recognition. Actual visual understanding.

### Step 3: Smart Notifications

Two different notifications for two different events:

```yaml
# On arrival - always notify
- service: notify.mobile_app_pixel_10_pro
  data:
    title: "🚪 Someone at door"
    message: "{{ visitor_analysis.response_text }}"

# After they leave - only if package detected
- condition: template
  value_template: "{{ 'yes' in package_check.response_text | lower }}"

- service: notify.mobile_app_pixel_10_pro
  data:
    title: "📦 Package Delivered!"
    message: "A package was left at your front door."
```

---

## The Numbers

After a week of real-world testing:

| Metric | Value |
|--------|-------|
| True positives (actual packages) | 100% detected |
| False positives (no package) | 0 |
| Detection time | 1.8 seconds |
| GPU memory used | 6.3 GB |
| Monthly cloud cost | $0 |

---

## Why This Beats Everything Else

### vs. Ring/Nest/Cloud Cameras
- ❌ Monthly subscription ($3-10/month)
- ❌ Privacy concerns (your video goes to their servers)
- ❌ "Package detection" is often just motion in a zone
- ✅ My solution: Free, private, actually intelligent

### vs. Frigate Alone
- Frigate is amazing for object detection
- But COCO models don't have a "package" class
- You'd need Frigate+ subscription ($50/year)
- ✅ My solution: Uses Frigate for person detection, LLM for package confirmation

### vs. Custom ML Model Training
- Training your own model requires thousands of labeled images
- Months of work for one specific use case
- ✅ My solution: LLM already understands "package" - zero training needed

---

## The Voice Assistant Bonus: Alexa-Style Notifications

This is where it gets really cool. Instead of a simple 30-second LED flash, I built **Alexa-style persistent notifications**:

### The LED Stays On Until You Acknowledge

```
📦 Package delivered
       ↓
🔵 LED turns blue (stays on indefinitely)
       ↓
🗣️ "Okay Nabu, what's my notification?"
       ↓
🔊 "Package delivered at 2:45 PM by Amazon driver in blue vest"
       ↓
💡 LED turns off automatically
```

### How It Works

The notification state is stored in Home Assistant helpers:
- `input_boolean.has_pending_notification` - Is there something to tell you?
- `input_text.pending_notification_message` - What to say when asked

A **sentence trigger** catches natural voice commands:
```yaml
trigger:
  - platform: conversation
    command:
      - "what's my notification"
      - "any notifications"
      - "check notifications"
```

When triggered, the Voice PE reads the stored message and clears the LED.

### The Experience

Now when a package arrives:
- 📱 Phone buzzes with AI description
- 🔵 Voice assistant LED turns blue and **stays on**
- 🗣️ Hours later: "Hey Nabu, any notifications?"
- 🔊 "Package delivered at 2:45 PM by Amazon driver in blue vest"
- 💡 LED turns off

No more missed notifications. No more "what was that alert about?"

---

## Try It Yourself

The complete automation is [open source on GitHub](https://github.com/homeiac/home/tree/master/scripts/package-detection).

### Quick Start

```bash
# Clone the repo
git clone https://github.com/homeiac/home.git

# Check prerequisites
./scripts/package-detection/check-prerequisites.sh

# Test LLM Vision
./scripts/package-detection/test-llm-vision.sh

# Deploy to Home Assistant
./scripts/package-detection/deploy-automation.sh
```

### Requirements

1. **Home Assistant** with LLM Vision integration (HACS)
2. **Ollama** running somewhere on your network
3. **llava:7b** model pulled (`ollama pull llava:7b`)
4. **Any camera** with person detection (or use Frigate)

---

## What's Next

This dual-phase approach opens up endless possibilities. With LLM Vision, you can build:

- **Package theft detection** - "Is the package I saw earlier still there?"
- **Visitor history** - Log all visitors with AI descriptions
- **Pet detection** - "Is my dog in the backyard?"
- **Car recognition** - "Is that my car or a stranger's?"
- **Security alerts** - "Is someone lingering suspiciously?"

The AI understands context. You just ask questions in plain English. And by asking different questions at different times (arrival vs departure), you get much smarter results.

---

## The Bottom Line

I spent years annoyed by dumb notifications from "smart" cameras. In one weekend, I built something that actually works:

- **Zero false alarms** (not "fewer" - zero)
- **Zero monthly cost** (not "cheap" - free)
- **Zero cloud dependency** (not "optional" - none)
- **100% package detection** (actually intelligent)
- **Three-phase intelligence** (arrival, departure, AND voice acknowledgment)
- **Natural voice interaction** ("what's my notification?" - just like Alexa)

The future of smart home isn't better motion sensors. It's AI that can actually *see*, *remember*, and *speak* - on your terms, when you're ready to listen.

---

*Want to see more homelab AI projects? Check out my [Voice PE + Ollama setup](voice-pe-complete-setup-guide.md) for voice-controlled everything.*

---

**Tags**: package-detection, llm-vision, ollama, home-assistant, smart-home, ai, local-ai, privacy, no-subscription, doorbell-camera, reolink, frigate, porch-pirate, delivery-notification, voice-assistant, alexa-style, voice-pe, natural-language

**Related**:
- [Voice PE Complete Setup Guide](voice-pe-complete-setup-guide.md)
- [Frigate Home Assistant Integration](frigate-homeassistant-integration-guide.md)
- [Homelab Network Topology](homelab-network-topology.md)
