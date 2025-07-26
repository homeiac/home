# Home Assistant + Frigate Integration Guide

## Overview
This guide documents integrating a Frigate NVR VM with Home Assistant VM running on the same Proxmox cluster.

## Environment
- **Proxmox Cluster**: 192.168.4.x network
- **Home Assistant VM**: 192.168.4.253:8123 (Home Assistant OS)
- **Frigate LXC Container**: 192.168.4.240:5000 (Installed via Proxmox VE Helper Scripts)
- **Cameras**: 4 devices (Reolink Doorbell, Old IP Camera, Trendnet IP 572W, Frigate system)

## Prerequisites
- Home Assistant OS VM running
- Frigate NVR running in LXC container (via Proxmox VE Helper Scripts)
- Both containers on same network with connectivity
- GitHub account for HACS authentication

## Step-by-Step Integration

### 1. Install HACS (Home Assistant Community Store)
HACS is required to install the Frigate integration.

**Install HACS Add-on:**
1. Use the official HACS installation link: https://hacs.xyz/docs/use/
2. Follow the automatic installation process
3. Install and start the HACS add-on
4. Restart Home Assistant

**Configure HACS Integration:**
1. Go to Settings > Devices & Services
2. Add HACS integration
3. Authenticate with GitHub account
4. HACS will appear in sidebar

### 2. Install Frigate Integration via HACS
1. Click HACS in sidebar
2. Go to Integrations tab  
3. Click "Explore & Download Repositories"
4. Search for "frigate"
5. Download Frigate integration
6. Restart Home Assistant

### 3. Install and Configure MQTT Broker
MQTT is required for Frigate sensors and automation features.

**Install Mosquitto Broker:**
- Use direct link: `http://[HA-IP]:8123/_my_redirect/config_flow_start?domain=mqtt`
- This automatically installs and configures MQTT integration

**Create MQTT User for Frigate:**
1. Go to Settings > People > Users
2. Add new user: `frigate`
3. Set strong password
4. Enable "Can only be used with local network"
5. Save credentials

### 4. Configure Frigate for MQTT
Update Frigate configuration file:

```yaml
mqtt:
  enabled: true
  host: 192.168.4.253  # Home Assistant IP
  port: 1883
  user: frigate         # User created above
  password: [password]  # Password from above
```

Restart Frigate LXC container after configuration change.

### 5. Add Frigate Integration to Home Assistant
1. Go to Settings > Devices & Services
2. Click "Add Integration" 
3. Search for "frigate"
4. Configure with Frigate URL: `http://192.168.4.240:5000`
5. Complete integration setup

### 6. Verify Integration
Check that integration shows:
- 4 devices detected
- 83+ entities created
- All camera entities available (no "Unavailable" status)
- Live camera feeds working

### 7. Add Camera Cards to Dashboard
**Install Frigate Camera Card (Recommended):**
- Follow guide: https://card.camera/#/README
- Provides advanced camera controls and features

**Basic Picture Entity Cards:**
1. Edit dashboard
2. Add Picture Entity Card
3. Select camera entity
4. Set Camera View to "Live"
5. Repeat for additional cameras

## Network Architecture
```
Proxmox Host (192.168.4.x)
├── Home Assistant VM (192.168.4.253:8123)
│   ├── MQTT Broker (Mosquitto)
│   ├── HACS
│   └── Frigate Integration
└── Frigate LXC Container (192.168.4.240:5000)
    ├── Camera Processing
    ├── MQTT Client
    └── RTSP Streams (port 8554)
```

## Data Flow
1. **Camera Feeds**: Cameras → Frigate (RTSP) → Home Assistant (direct RTSP)
2. **Motion Detection**: Frigate → MQTT → Home Assistant sensors
3. **Controls**: Home Assistant → MQTT → Frigate
4. **Recordings**: Frigate storage → Home Assistant Media Browser

## Troubleshooting

### MQTT Connection Issues
- **Error**: "MQTT Not authorized"
- **Solution**: Verify Frigate MQTT credentials match Home Assistant user
- **Check**: Frigate logs and MQTT integration status

### Entities Show "Unavailable"
- **Cause**: MQTT connection not fully established
- **Solution**: Reload Frigate integration or restart Home Assistant
- **Verify**: Check MQTT topics in Developer Tools

### Camera Feeds Not Working
- **Check**: Network connectivity between VM and LXC container
- **Verify**: Frigate RTSP port 8554 accessible
- **Test**: Direct access to Frigate web interface

### Coral TPU USB Mapping Issues After Reboot
- **Problem**: Frigate container fails to start after Proxmox host reboot due to USB device mapping changes
- **Cause**: Coral TPU USB device appears on different bus/device numbers after reboot
- **Solution**: Automated via systemd service (see Coral TPU Automation section)
- **Manual Fix**: 
  1. Run Python script to initialize Coral: `cd ~/code && python3 coral/pycoral/examples/classify_image.py --model test_data/mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite --labels test_data/inat_bird_labels.txt --input test_data/parrot.jpg`
  2. Check device: `lsusb | grep -i google`
  3. Update LXC config: `vim /etc/pve/lxc/113.conf` (change dev0 line)
  4. Start container: `pct start 113`

## Key Features Enabled
- Live camera streaming in Home Assistant
- Motion detection sensors per camera
- Object detection events
- Recording access via Media Browser
- Automation triggers for camera events
- Mobile app notifications (with additional setup)

## Security Notes
- MQTT user restricted to local network only
- No external exposure of MQTT broker
- Frigate accessible only within local network
- Camera streams remain on local network

## Performance Considerations
- Camera processing handled by Frigate LXC container
- Home Assistant only displays processed streams
- MQTT provides lightweight sensor data
- No GPU required for Home Assistant (handled by Frigate)
- LXC containers provide better resource efficiency than VMs

## Coral TPU Automation

### Automated USB Mapping Fix
The Frigate container uses a Google Coral TPU for hardware acceleration. After Proxmox host reboots, the USB device mapping can change, causing the container to fail to start. This is now automated via a systemd service.

### Installation
1. **Copy script to Proxmox host**:
   ```bash
   scp proxmox/scripts/coral-usb-fix.sh root@fun-bedbug.maas:/usr/local/bin/
   chmod +x /usr/local/bin/coral-usb-fix.sh
   ```

2. **Install systemd service**:
   ```bash
   scp proxmox/systemd/coral-usb-fix.service root@fun-bedbug.maas:/etc/systemd/system/
   systemctl enable coral-usb-fix.service
   ```

### How It Works
- **On Boot**: Service runs automatically before Frigate container starts
- **Device Check**: Looks for Google Coral TPU in `lsusb` output
- **Initialization**: If missing, runs Python script to initialize Coral TPU
- **USB Mapping**: Updates `/etc/pve/lxc/113.conf` with correct device path
- **Logging**: All operations logged to `/var/log/coral-usb-fix.log`

### Manual Operation
```bash
# Run manually (for testing)
/usr/local/bin/coral-usb-fix.sh

# Check service status
systemctl status coral-usb-fix.service

# View logs
journalctl -u coral-usb-fix.service
cat /var/log/coral-usb-fix.log
```

## Next Steps
- Configure motion detection automations
- Set up event notifications
- Explore recording retention policies
- Add object detection zones
- Integrate with other Home Assistant devices