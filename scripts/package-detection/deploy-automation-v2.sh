#!/bin/bash
# Deploy Package Detection Automation v2.0
#
# This script updates the automation via Home Assistant API
# Key changes in v2.0:
# - mode: queued (fixes person_left being blocked)
# - OpenTelemetry-style tracing with trace_id
# - Structured logging for easy debugging

set -e

# Load environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
fi

HA_URL="${HA_URL:-http://homeassistant.maas:8123}"
HA_TOKEN="${HA_TOKEN:-}"

if [ -z "$HA_TOKEN" ]; then
    echo "Error: HA_TOKEN not set. Create .env file or export HA_TOKEN"
    exit 1
fi

echo "=== Deploying Package Detection Automation v2.0 ==="
echo "Target: $HA_URL"
echo ""

# The automation config as JSON
AUTOMATION_JSON=$(cat <<'ENDJSON'
{
  "id": "package_delivery_detection",
  "alias": "Package Delivery Detection",
  "description": "Detects package deliveries using Reolink + LLM Vision. v2.0: Fixed mode blocking, added OpenTelemetry-style tracing.",
  "mode": "queued",
  "triggers": [
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
      "for": {"seconds": 3},
      "id": "person_left"
    }
  ],
  "conditions": [
    {
      "condition": "time",
      "after": "08:00:00",
      "before": "21:00:00"
    }
  ],
  "actions": [
    {
      "variables": {
        "trace_id": "{{ now().strftime('%H%M%S') }}-{{ range(1000,9999) | random }}",
        "trigger_name": "{{ trigger.id }}",
        "start_time": "{{ now().isoformat() }}"
      }
    },
    {
      "action": "logbook.log",
      "data": {
        "name": "Package Detection",
        "message": "[PKG-{{ trace_id }}] TRACE_START | trigger={{ trigger_name }} | time={{ start_time }}",
        "entity_id": "automation.package_delivery_detection"
      }
    },
    {
      "choose": [
        {
          "alias": "PERSON ARRIVED - Analyze visitor",
          "conditions": [{"condition": "trigger", "id": "person_arrived"}],
          "sequence": [
            {
              "action": "logbook.log",
              "data": {
                "name": "Package Detection",
                "message": "[PKG-{{ trace_id }}] SPAN_START:visitor_analysis | Waiting 2s for person to settle",
                "entity_id": "automation.package_delivery_detection"
              }
            },
            {"delay": {"seconds": 2}},
            {
              "action": "logbook.log",
              "data": {
                "name": "Package Detection",
                "message": "[PKG-{{ trace_id }}] EVENT:snapshot | file=doorbell_visitor.jpg",
                "entity_id": "camera.reolink_video_doorbell_wifi_fluent"
              }
            },
            {
              "action": "camera.snapshot",
              "target": {"entity_id": "camera.reolink_video_doorbell_wifi_fluent"},
              "data": {"filename": "/config/www/tmp/doorbell_visitor.jpg"}
            },
            {
              "action": "logbook.log",
              "data": {
                "name": "Package Detection",
                "message": "[PKG-{{ trace_id }}] EVENT:llm_call | model=llava:7b | prompt=describe_visitor",
                "entity_id": "automation.package_delivery_detection"
              }
            },
            {
              "action": "llmvision.image_analyzer",
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
              "action": "logbook.log",
              "data": {
                "name": "Package Detection",
                "message": "[PKG-{{ trace_id }}] EVENT:llm_response | result={{ visitor_analysis.response_text }}",
                "entity_id": "automation.package_delivery_detection"
              }
            },
            {
              "action": "input_text.set_value",
              "target": {"entity_id": "input_text.pending_notification_message"},
              "data": {"value": "Visitor at {{ now().strftime('%I:%M %p') }}: {{ visitor_analysis.response_text }}"}
            },
            {
              "action": "input_text.set_value",
              "target": {"entity_id": "input_text.pending_notification_type"},
              "data": {"value": "visitor"}
            },
            {
              "action": "logbook.log",
              "data": {
                "name": "Package Detection",
                "message": "[PKG-{{ trace_id }}] EVENT:notify | type=mobile | title=Someone at door",
                "entity_id": "automation.package_delivery_detection"
              }
            },
            {
              "action": "notify.mobile_app_pixel_10_pro",
              "data": {
                "title": "Someone at door",
                "message": "{{ visitor_analysis.response_text }}",
                "data": {
                  "image": "/api/camera_proxy/camera.reolink_video_doorbell_wifi_fluent",
                  "tag": "doorbell_visitor",
                  "channel": "Doorbell",
                  "importance": "default"
                }
              }
            },
            {
              "action": "logbook.log",
              "data": {
                "name": "Package Detection",
                "message": "[PKG-{{ trace_id }}] SPAN_END:visitor_analysis | status=complete",
                "entity_id": "automation.package_delivery_detection"
              }
            }
          ]
        },
        {
          "alias": "PERSON LEFT - Check for packages",
          "conditions": [{"condition": "trigger", "id": "person_left"}],
          "sequence": [
            {
              "action": "logbook.log",
              "data": {
                "name": "Package Detection",
                "message": "[PKG-{{ trace_id }}] SPAN_START:package_check | Person left, checking for packages",
                "entity_id": "automation.package_delivery_detection"
              }
            },
            {
              "action": "logbook.log",
              "data": {
                "name": "Package Detection",
                "message": "[PKG-{{ trace_id }}] EVENT:snapshot | file=doorbell_after.jpg",
                "entity_id": "camera.reolink_video_doorbell_wifi_fluent"
              }
            },
            {
              "action": "camera.snapshot",
              "target": {"entity_id": "camera.reolink_video_doorbell_wifi_fluent"},
              "data": {"filename": "/config/www/tmp/doorbell_after.jpg"}
            },
            {
              "action": "logbook.log",
              "data": {
                "name": "Package Detection",
                "message": "[PKG-{{ trace_id }}] EVENT:llm_call | model=llava:7b | prompt=package_check",
                "entity_id": "automation.package_delivery_detection"
              }
            },
            {
              "action": "llmvision.image_analyzer",
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
              "variables": {
                "package_detected": "{{ 'yes' in (package_check.response_text | default('') | lower) }}"
              }
            },
            {
              "action": "logbook.log",
              "data": {
                "name": "Package Detection",
                "message": "[PKG-{{ trace_id }}] EVENT:llm_response | result={{ package_check.response_text }} | package_detected={{ package_detected }}",
                "entity_id": "automation.package_delivery_detection"
              }
            },
            {
              "if": [
                {
                  "condition": "template",
                  "value_template": "{{ package_detected }}"
                }
              ],
              "then": [
                {
                  "action": "logbook.log",
                  "data": {
                    "name": "Package Detection",
                    "message": "[PKG-{{ trace_id }}] EVENT:package_confirmed | Activating LED and notifications",
                    "entity_id": "automation.package_delivery_detection"
                  }
                },
                {
                  "action": "input_text.set_value",
                  "target": {"entity_id": "input_text.pending_notification_message"},
                  "data": {"value": "Package delivered at {{ now().strftime('%I:%M %p') }} by {{ states('input_text.pending_notification_message').split(': ')[-1] if 'Visitor' in states('input_text.pending_notification_message') else 'unknown carrier' }}"}
                },
                {
                  "action": "input_text.set_value",
                  "target": {"entity_id": "input_text.pending_notification_type"},
                  "data": {"value": "package"}
                },
                {
                  "action": "input_boolean.turn_on",
                  "target": {"entity_id": "input_boolean.has_pending_notification"}
                },
                {
                  "parallel": [
                    {
                      "action": "notify.mobile_app_pixel_10_pro",
                      "data": {
                        "title": "Package Delivered!",
                        "message": "Ask your Voice Assistant: 'What's my notification?'",
                        "data": {
                          "image": "/api/camera_proxy/camera.reolink_video_doorbell_wifi_fluent",
                          "tag": "package_delivery",
                          "channel": "Package Alerts",
                          "importance": "high"
                        }
                      }
                    },
                    {
                      "sequence": [
                        {
                          "action": "logbook.log",
                          "data": {
                            "name": "Package Detection",
                            "message": "[PKG-{{ trace_id }}] EVENT:led_on | entity=voice_pe_led | color=blue",
                            "entity_id": "light.home_assistant_voice_09f5a3_led_ring"
                          }
                        },
                        {
                          "action": "light.turn_on",
                          "target": {"entity_id": "light.home_assistant_voice_09f5a3_led_ring"},
                          "data": {"rgb_color": [0, 100, 255], "brightness": 200}
                        }
                      ]
                    }
                  ]
                },
                {
                  "action": "logbook.log",
                  "data": {
                    "name": "Package Detection",
                    "message": "[PKG-{{ trace_id }}] SPAN_END:package_check | status=PACKAGE_DETECTED | led=ON",
                    "entity_id": "automation.package_delivery_detection"
                  }
                }
              ],
              "else": [
                {
                  "action": "logbook.log",
                  "data": {
                    "name": "Package Detection",
                    "message": "[PKG-{{ trace_id }}] SPAN_END:package_check | status=NO_PACKAGE",
                    "entity_id": "automation.package_delivery_detection"
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "action": "logbook.log",
      "data": {
        "name": "Package Detection",
        "message": "[PKG-{{ trace_id }}] TRACE_END | trigger={{ trigger_name }} | duration={{ (now() - as_datetime(start_time)).total_seconds() | round(1) }}s",
        "entity_id": "automation.package_delivery_detection"
      }
    }
  ]
}
ENDJSON
)

echo "[1/3] Updating automation configuration..."
RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$AUTOMATION_JSON" \
    "$HA_URL/api/config/automation/config/package_delivery_detection")

if echo "$RESPONSE" | grep -q "result"; then
    echo "      Automation config updated"
else
    echo "      Response: $RESPONSE"
fi

echo "[2/3] Reloading automations..."
curl -s -X POST \
    -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/services/automation/reload" > /dev/null

sleep 2
echo "      Automations reloaded"

echo "[3/3] Verifying deployment..."
MODE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" \
    "$HA_URL/api/config/automation/config/package_delivery_detection" | jq -r '.mode')

if [ "$MODE" = "queued" ]; then
    echo "      SUCCESS: mode is now 'queued'"
else
    echo "      WARNING: mode is '$MODE' (expected 'queued')"
fi

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Trace format in logbook:"
echo "  [PKG-HHMMSS-XXXX] TRACE_START | trigger=person_arrived"
echo "  [PKG-HHMMSS-XXXX] SPAN_START:visitor_analysis"
echo "  [PKG-HHMMSS-XXXX] EVENT:snapshot | file=..."
echo "  [PKG-HHMMSS-XXXX] EVENT:llm_call | model=..."
echo "  [PKG-HHMMSS-XXXX] EVENT:llm_response | result=..."
echo "  [PKG-HHMMSS-XXXX] SPAN_END:visitor_analysis | status=complete"
echo "  [PKG-HHMMSS-XXXX] TRACE_END | trigger=... | duration=Xs"
echo ""
echo "To view logs: Filter logbook by 'Package Detection'"
