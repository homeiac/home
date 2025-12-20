#!/bin/bash

# Voice PE Factory Reset Instructions
# Provides step-by-step USB recovery procedure

DEVICE_NAME="home_assistant_voice_09f5a3"
FIRMWARE_URL="https://github.com/esphome/firmware/releases"

cat <<'EOF'
=== Voice PE Factory Reset Instructions ===

⚠️  WARNING: Factory reset will erase all custom configuration!
    Always backup first: ./00-backup-voice-pe-config.sh

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OPTION 1: USB Recovery Mode (Hardware Reset)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Required:
  • USB-C cable
  • Chrome/Edge browser (Web Serial API required)
  • Boot button access (inside Voice PE case)

Steps:

1. Download Factory Firmware
   → Visit: https://github.com/esphome/firmware/releases
   → Find: "voice-assistant-esp32-s3-box-3-*.bin"
   → Download latest stable release

2. Enter Bootloader Mode
   a. Locate BOOT button (small button near USB-C port)
   b. Press and HOLD BOOT button
   c. Connect USB-C cable to computer (while holding BOOT)
   d. Continue holding for 5 seconds
   e. Release BOOT button

   Device should now be in bootloader mode (no LED activity)

3. Flash Factory Firmware
   → Visit: https://web.esphome.io/
   → Click "Connect"
   → Select COM/USB port for Voice PE
   → Click "Install"
   → Choose "Manual flash" if prompted
   → Select downloaded .bin file
   → Wait for flash to complete (~2-3 minutes)

4. Initial Setup
   → Device will reboot with factory config
   → Connect to WiFi AP: "esphome-web-XXXXXX"
   → Configure WiFi credentials
   → Add to Home Assistant

5. Restore Custom Config (if needed)
   → Run: ./98-restore-voice-pe-backup.sh
   → Follow manual restore instructions

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OPTION 2: Soft Reset via ESPHome Dashboard
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If device is still responsive in ESPHome:

1. Open ESPHome dashboard:
   http://homeassistant.maas:6052

2. Find device: home_assistant_voice_09f5a3

3. Click "Edit"

4. Replace YAML with factory config from:
   https://github.com/esphome/firmware/tree/main/voice-assistant

5. Click "Save" → "Install" → "Wirelessly"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Troubleshooting
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Device not detected in bootloader mode:
  • Try different USB cable (must support data, not just power)
  • Use USB 2.0 port (USB 3.0 sometimes problematic)
  • Install CH340/CP210x drivers if needed
  • Try USB hub if direct connection fails

Flash fails partway through:
  • Ensure good USB connection (avoid hubs)
  • Close other applications using serial ports
  • Try erasing flash first (option in web.esphome.io)

Device boots but won't connect to WiFi:
  • Check 2.4GHz WiFi band (5GHz not supported)
  • Verify WiFi credentials (case-sensitive)
  • Move closer to router (weak signal during setup)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Related Scripts
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ./00-backup-voice-pe-config.sh   - Backup current config
  ./98-restore-voice-pe-backup.sh  - Restore from backup
  ./01-check-voice-pe-status.sh    - Verify device status

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Official Resources:
  • ESPHome Firmware: https://github.com/esphome/firmware
  • Web Flasher: https://web.esphome.io/
  • ESPHome Docs: https://esphome.io/components/esp32.html
  • HA Voice Docs: https://www.home-assistant.io/voice_control/

EOF
