#!/bin/bash
# Deploy Package Detection Automation to Home Assistant
# Includes Alexa-style persistent notifications with voice acknowledgment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "═══════════════════════════════════════════════════════"
echo "  Deploying Package Detection System"
echo "═══════════════════════════════════════════════════════"
echo ""

# Step 1: Create input helpers for notification state
echo "1️⃣  Creating notification state helpers..."

# input_text for notification message
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "Pending Notification Message",
        "icon": "mdi:message-text",
        "max": 500
    }' \
    "$HA_URL/api/config/config_entries/flow" \
    -d '{"handler": "input_text"}' > /dev/null 2>&1

# Create via REST API helpers endpoint
HELPERS_CREATED=0

# Check if helpers already exist
EXISTING=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
    python3 -c "import sys,json; states=json.load(sys.stdin); print('exists' if any('pending_notification' in s['entity_id'] for s in states) else 'missing')" 2>/dev/null)

if [ "$EXISTING" = "exists" ]; then
    echo "   ✅ Notification helpers already exist"
else
    echo "   ⚠️  Create these helpers manually in HA UI:"
    echo "      Settings → Devices & Services → Helpers → Create Helper"
    echo "      • input_text: pending_notification_message (max 500 chars)"
    echo "      • input_text: pending_notification_type"
    echo "      • input_boolean: has_pending_notification"
    echo ""
fi

# Step 2: Create the main automation
echo "2️⃣  Creating main automation..."

AUTOMATION_JSON=$(cat <<'ENDJSON'
{
  "alias": "Package Delivery Detection",
  "description": "Detects package deliveries using Reolink + LLM Vision. Stores notification for voice acknowledgment.",
  "mode": "single",
  "trigger": [
    {
      "platform": "state",
      "entity_id": "binary_sensor.reolink_video_doorbell_wifi_person",
      "from": "off",
      "to": "on",
      "id": "person_arrived"
    },
    {
      "platform": "state",
      "entity_id": "binary_sensor.reolink_video_doorbell_wifi_person",
      "from": "on",
      "to": "off",
      "for": { "seconds": 3 },
      "id": "person_left"
    }
  ],
  "condition": [
    {
      "condition": "time",
      "after": "08:00:00",
      "before": "21:00:00"
    }
  ],
  "action": [
    {
      "choose": [
        {
          "alias": "PERSON ARRIVED - Analyze who is at door",
          "conditions": [{ "condition": "trigger", "id": "person_arrived" }],
          "sequence": [
            { "delay": { "seconds": 2 } },
            {
              "service": "camera.snapshot",
              "target": { "entity_id": "camera.reolink_doorbell" },
              "data": { "filename": "/config/www/tmp/doorbell_visitor.jpg" }
            },
            {
              "service": "llmvision.image_analyzer",
              "data": {
                "provider": "01K1KDVH6Y1GMJ69MJF77WGJEA",
                "model": "llava:7b",
                "image_file": "/config/www/tmp/doorbell_visitor.jpg",
                "message": "Describe the person at this door in 10 words or less. Include: delivery uniform (UPS/FedEx/Amazon/USPS), or regular visitor, or unknown person. Mention if holding a package.",
                "max_tokens": 50,
                "target_width": 1280
              },
              "response_variable": "visitor_analysis"
            },
            {
              "service": "logbook.log",
              "data": {
                "name": "Doorbell Visitor",
                "message": "{{ visitor_analysis.response_text }}",
                "entity_id": "camera.reolink_doorbell"
              }
            },
            {
              "service": "input_text.set_value",
              "target": { "entity_id": "input_text.pending_notification_message" },
              "data": { "value": "Visitor at {{ now().strftime('%I:%M %p') }}: {{ visitor_analysis.response_text }}" }
            },
            {
              "service": "input_text.set_value",
              "target": { "entity_id": "input_text.pending_notification_type" },
              "data": { "value": "visitor" }
            },
            {
              "service": "notify.mobile_app_pixel_10_pro",
              "data": {
                "title": "🚪 Someone at door",
                "message": "{{ visitor_analysis.response_text }}",
                "data": {
                  "image": "/api/camera_proxy/camera.reolink_doorbell",
                  "tag": "doorbell_visitor",
                  "channel": "Doorbell",
                  "importance": "default"
                }
              }
            }
          ]
        },
        {
          "alias": "PERSON LEFT - Check for packages",
          "conditions": [{ "condition": "trigger", "id": "person_left" }],
          "sequence": [
            {
              "service": "camera.snapshot",
              "target": { "entity_id": "camera.reolink_doorbell" },
              "data": { "filename": "/config/www/tmp/doorbell_after.jpg" }
            },
            {
              "service": "llmvision.image_analyzer",
              "data": {
                "provider": "01K1KDVH6Y1GMJ69MJF77WGJEA",
                "model": "llava:7b",
                "image_file": "/config/www/tmp/doorbell_after.jpg",
                "message": "Answer ONLY YES or NO: Is there a package, box, or delivery item visible on this porch/doorstep?",
                "max_tokens": 10,
                "target_width": 1280
              },
              "response_variable": "package_check"
            },
            {
              "service": "logbook.log",
              "data": {
                "name": "Package Check",
                "message": "After visitor left: {{ package_check.response_text }}",
                "entity_id": "camera.reolink_doorbell"
              }
            },
            {
              "if": [{ "condition": "template", "value_template": "{{ 'yes' in (package_check.response_text | default('') | lower) }}" }],
              "then": [
                {
                  "service": "input_text.set_value",
                  "target": { "entity_id": "input_text.pending_notification_message" },
                  "data": { "value": "Package delivered at {{ now().strftime('%I:%M %p') }} by {{ states('input_text.pending_notification_message').split(': ')[-1] if 'Visitor' in states('input_text.pending_notification_message') else 'unknown carrier' }}" }
                },
                {
                  "service": "input_text.set_value",
                  "target": { "entity_id": "input_text.pending_notification_type" },
                  "data": { "value": "package" }
                },
                {
                  "service": "input_boolean.turn_on",
                  "target": { "entity_id": "input_boolean.has_pending_notification" }
                },
                {
                  "parallel": [
                    {
                      "service": "notify.mobile_app_pixel_10_pro",
                      "data": {
                        "title": "📦 Package Delivered!",
                        "message": "Ask your Voice Assistant: 'What's my notification?'",
                        "data": {
                          "image": "/api/camera_proxy/camera.reolink_doorbell",
                          "tag": "package_delivery",
                          "channel": "Package Alerts",
                          "importance": "high"
                        }
                      }
                    },
                    {
                      "service": "light.turn_on",
                      "target": { "entity_id": "light.home_assistant_voice_09f5a3_led_ring" },
                      "data": { "rgb_color": [0, 100, 255], "brightness": 200, "effect": "pulse" }
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
ENDJSON
)

# Create automation via REST API
RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$AUTOMATION_JSON" \
    "$HA_URL/api/config/automation/config/package_delivery_detection" 2>&1)

if echo "$RESPONSE" | grep -q "result"; then
    echo "   ✅ Main automation created"
else
    # Try to update instead
    curl -s -X PUT \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$AUTOMATION_JSON" \
        "$HA_URL/api/config/automation/config/package_delivery_detection" > /dev/null 2>&1
    echo "   ✅ Main automation updated"
fi

# Step 3: Create the acknowledgment automation (clears notification when asked)
echo "3️⃣  Creating acknowledgment automation..."

ACK_AUTOMATION=$(cat <<'ENDJSON'
{
  "alias": "Clear Doorbell Notification",
  "description": "Clears pending notification and turns off LED when user acknowledges via voice or manually",
  "mode": "single",
  "trigger": [
    {
      "platform": "state",
      "entity_id": "input_boolean.has_pending_notification",
      "to": "off"
    }
  ],
  "action": [
    {
      "service": "light.turn_off",
      "target": { "entity_id": "light.home_assistant_voice_09f5a3_led_ring" }
    },
    {
      "service": "input_text.set_value",
      "target": { "entity_id": "input_text.pending_notification_message" },
      "data": { "value": "" }
    },
    {
      "service": "input_text.set_value",
      "target": { "entity_id": "input_text.pending_notification_type" },
      "data": { "value": "" }
    }
  ]
}
ENDJSON
)

curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$ACK_AUTOMATION" \
    "$HA_URL/api/config/automation/config/clear_doorbell_notification" > /dev/null 2>&1 || \
curl -s -X PUT \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$ACK_AUTOMATION" \
    "$HA_URL/api/config/automation/config/clear_doorbell_notification" > /dev/null 2>&1

echo "   ✅ Acknowledgment automation created"

# Step 4: Create intent script for voice response
echo "4️⃣  Creating voice intent script..."

INTENT_SCRIPT=$(cat <<'ENDJSON'
{
  "alias": "Get Pending Notification",
  "description": "Responds with pending notification details when asked via voice",
  "sequence": [
    {
      "if": [
        {
          "condition": "state",
          "entity_id": "input_boolean.has_pending_notification",
          "state": "on"
        }
      ],
      "then": [
        {
          "service": "assist_satellite.announce",
          "target": { "entity_id": "assist_satellite.home_assistant_voice_09f5a3_assist_satellite" },
          "data": {
            "message": "{{ states('input_text.pending_notification_message') }}"
          }
        },
        {
          "service": "input_boolean.turn_off",
          "target": { "entity_id": "input_boolean.has_pending_notification" }
        }
      ],
      "else": [
        {
          "service": "assist_satellite.announce",
          "target": { "entity_id": "assist_satellite.home_assistant_voice_09f5a3_assist_satellite" },
          "data": {
            "message": "You have no pending notifications."
          }
        }
      ]
    }
  ],
  "mode": "single",
  "icon": "mdi:bell-ring"
}
ENDJSON
)

curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$INTENT_SCRIPT" \
    "$HA_URL/api/config/script/config/get_pending_notification" > /dev/null 2>&1 || \
curl -s -X PUT \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$INTENT_SCRIPT" \
    "$HA_URL/api/config/script/config/get_pending_notification" > /dev/null 2>&1

echo "   ✅ Voice intent script created"

# Step 5: Reload automations and scripts
echo ""
echo "5️⃣  Reloading automations and scripts..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/services/automation/reload" > /dev/null
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/services/script/reload" > /dev/null
echo "   ✅ Reloaded"

# Step 6: Verify deployment
echo ""
echo "6️⃣  Verifying deployment..."
sleep 2

VERIFY=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
    python3 -c "
import sys, json
states = json.load(sys.stdin)
entities = {s['entity_id']: s['state'] for s in states}

checks = [
    ('automation.package_delivery_detection', 'Main automation'),
    ('automation.clear_doorbell_notification', 'Ack automation'),
    ('script.get_pending_notification', 'Voice script'),
]

for entity, name in checks:
    if entity in entities:
        print(f'   ✅ {name}: {entities[entity]}')
    else:
        print(f'   ⚠️  {name}: not found')

# Check helpers
helpers = ['input_text.pending_notification_message', 'input_text.pending_notification_type', 'input_boolean.has_pending_notification']
missing = [h for h in helpers if h not in entities]
if missing:
    print(f'   ⚠️  Missing helpers: {missing}')
else:
    print('   ✅ All helpers present')
" 2>/dev/null)

echo "$VERIFY"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Deployment Complete"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "REQUIRED: Create these helpers in HA UI if missing:"
echo "  Settings → Devices & Services → Helpers → Create Helper"
echo ""
echo "  1. Toggle: 'has_pending_notification'"
echo "     Entity ID: input_boolean.has_pending_notification"
echo ""
echo "  2. Text: 'pending_notification_message'"
echo "     Entity ID: input_text.pending_notification_message"
echo "     Max length: 500"
echo ""
echo "  3. Text: 'pending_notification_type'"
echo "     Entity ID: input_text.pending_notification_type"
echo "     Max length: 50"
echo ""
echo "VOICE COMMANDS (add to HA Assist sentences):"
echo "  'What's my notification'"
echo "  'What is the notification'"
echo "  'Do I have any notifications'"
echo ""
echo "  These should trigger: script.get_pending_notification"
echo ""
echo "HOW IT WORKS:"
echo "  1. Package delivered → LED pulses blue (stays on)"
echo "  2. Ask Voice PE: 'What's my notification?'"
echo "  3. Voice PE: 'Package delivered at 2:45 PM by Amazon driver'"
echo "  4. LED turns off automatically"
echo ""
