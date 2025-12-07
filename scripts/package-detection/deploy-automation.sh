#!/bin/bash
# Deploy Package Detection Automation to Home Assistant

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "═══════════════════════════════════════════════════════"
echo "  Deploying Package Detection Automation"
echo "═══════════════════════════════════════════════════════"
echo ""

# Step 1: Create tmp directory for snapshots
echo "1️⃣  Creating snapshot directory..."
# Note: This requires SSH access to HA or using a shell command add-on
# For now, we'll create via the API using a shell_command

# Step 2: Create the automation via API
echo "2️⃣  Creating automation..."

AUTOMATION_JSON=$(cat <<'ENDJSON'
{
  "alias": "Package Delivery Detection",
  "description": "Detects package deliveries using Reolink + LLM Vision. Notifies via phone push and pulses Voice PE LED.",
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
                  "parallel": [
                    {
                      "service": "notify.mobile_app_pixel_10_pro",
                      "data": {
                        "title": "📦 Package Delivered!",
                        "message": "A package was left at your front door.",
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
                      "data": { "rgb_color": [0, 100, 255], "brightness": 200 }
                    }
                  ]
                },
                { "delay": { "seconds": 30 } },
                {
                  "service": "light.turn_off",
                  "target": { "entity_id": "light.home_assistant_voice_09f5a3_led_ring" }
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
    echo "   ✅ Automation created successfully"
elif echo "$RESPONSE" | grep -q "already exists"; then
    echo "   ⚠️  Automation already exists, updating..."
    # Try to update instead
    RESPONSE=$(curl -s -X PUT \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$AUTOMATION_JSON" \
        "$HA_URL/api/config/automation/config/package_delivery_detection" 2>&1)
    echo "   ✅ Automation updated"
else
    echo "   Response: $RESPONSE"
fi

# Step 3: Reload automations
echo ""
echo "3️⃣  Reloading automations..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/services/automation/reload" > /dev/null

echo "   ✅ Automations reloaded"

# Step 4: Verify automation exists
echo ""
echo "4️⃣  Verifying deployment..."
sleep 2

VERIFY=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/states/automation.package_delivery_detection" 2>/dev/null)

if echo "$VERIFY" | grep -q "package_delivery_detection"; then
    STATE=$(echo "$VERIFY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state','unknown'))" 2>/dev/null)
    echo "   ✅ Automation deployed: state=$STATE"
else
    echo "   ⚠️  Could not verify - check HA UI"
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Deployment Complete"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Check HA → Settings → Automations → Package Delivery Detection"
echo "  2. Test by walking in front of doorbell"
echo "  3. Monitor: Developer Tools → Logs → filter 'llmvision'"
echo ""
