# Out-of-Band SMS Notifications for Homelab Disaster Recovery

**The Problem**: When your homelab loses power, your router dies first. No internet means no push notifications, no email alerts, no Slack messages. You're blind to what's happening to your infrastructure.

**The Solution**: A $30/year cellular SMS gateway that works when everything else is down.

## The Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    NORMAL OPERATION                                      │
│                                                                          │
│   UPS Event → pve → ntfy.sh/email → Phone                               │
│                     (via internet)                                       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                    POWER OUTAGE (Router Dead)                            │
│                                                                          │
│   UPS Event → pve ──WiFi──→ Pixel 7 ──Cellular──→ SMS → Phone           │
│                   (hotspot)  (Helium Mobile)                             │
└─────────────────────────────────────────────────────────────────────────┘
```

When power fails:
1. Router/modem lose power immediately (no UPS)
2. pve server (on UPS) loses internet connectivity
3. pve's WiFi (iwd) auto-connects to Pixel 7 hotspot
4. UPS monitoring triggers notification script
5. SMS sent via Pixel 7's cellular connection
6. You get an SMS even with no internet

## Cost Breakdown

| Component | Cost | Notes |
|-----------|------|-------|
| Pixel 7 (used) | $150-200 | Any Android phone works |
| Helium Mobile Zero | ~$30/year | Free plan + taxes (~$2.50/mo) |
| USB WiFi adapter | $15 | If server lacks WiFi |
| **Total Year 1** | **~$195** | |
| **Recurring** | **~$30/year** | Just the cellular plan |

### Why Helium Mobile?

We evaluated several options:

| Carrier | Monthly | Annual | Type | Notes |
|---------|---------|--------|------|-------|
| Helium Mobile Zero | $0 + tax | ~$30 | Real carrier | 300 SMS/mo, T-Mobile network |
| TextNow | $0 | $0 | VoIP | Number may be recycled if inactive |
| Tello | $5 | $60 | Real carrier | Cheapest traditional MVNO |
| SpeedTalk Pay-Go | $0.02/SMS | ~$100/yr | Real carrier | 365-day expiry |

Helium Mobile Zero won because:
- Real carrier number (not VoIP - more reliable SMS delivery)
- Lowest cost for occasional use
- No activity requirements
- T-Mobile network coverage

## Hardware Setup

### The Dedicated SMS Phone

We used a Pixel 7 because:
- Native eSIM support (instant activation)
- Android hotspot + WiFi simultaneously (key feature!)
- Reliable, well-supported device
- Can sit plugged in 24/7

**Critical Discovery**: Most Android phones can run WiFi and hotspot at the same time. The phone stays on your home WiFi normally, but the hotspot is always available as a backup path. When your router dies, the hotspot automatically falls back to cellular.

### Server WiFi

Our Proxmox server (pve) has a USB WiFi adapter. It normally connects to our main WiFi (wiremore2) but has the Pixel 7 hotspot configured as a known network.

When the main WiFi disappears (router dead), iwd automatically connects to the Pixel 7 hotspot.

## Software Stack

### 1. Traccar SMS Gateway (Android App)

[Traccar SMS Gateway](https://www.traccar.org/sms-gateway/) is a free, open-source Android app that exposes an HTTP API for sending SMS.

**Setup:**
1. Install from Play Store (search "Traccar SMS Gateway")
2. Set as default SMS app (required for send permissions)
3. Enable "HTTP server" in settings
4. Note the authorization token

**API Format:**
```bash
curl -X POST "http://<phone-ip>:8082/" \
  -H "Authorization: <token>" \
  -H "Content-Type: application/json" \
  -d '{"to": "+1234567890", "message": "Test message"}'
```

### 2. iwd WiFi Management (Linux)

Proxmox uses iwd (iNet Wireless Daemon) for WiFi. Adding a fallback network is simple:

```bash
# /var/lib/iwd/Pixel_7_Hotspot.psk
[Security]
Passphrase=your-hotspot-password
```

iwd automatically connects to known networks. When the primary network disappears, it switches to the next available one.

### 3. NUT UPS Monitoring

Network UPS Tools (NUT) monitors the UPS and triggers notifications via `NOTIFYCMD` in `upsmon.conf`:

```conf
NOTIFYCMD /root/nut-notify.sh
NOTIFYFLAG ONBATT SYSLOG+WALL+EXEC
NOTIFYFLAG LOWBATT SYSLOG+WALL+EXEC
NOTIFYFLAG ONLINE SYSLOG+WALL+EXEC
```

### 4. The Notification Script

The key insight: Android hotspot gateway IPs are dynamic. The script tries multiple IPs:

```bash
send_sms() {
    local message="$1"

    # Get wlan0 gateway (works regardless of which network we're on)
    local gateway_ip
    gateway_ip=$(ip route show dev wlan0 | grep default | awk '{print $3}')

    # Try configured IP first, then gateway
    for ip in "${SMS_GATEWAY_IP}" "${gateway_ip}"; do
        [[ -z "$ip" ]] && continue
        if curl -s -X POST "http://${ip}:${SMS_GATEWAY_PORT}/" \
            -H "Authorization: ${SMS_GATEWAY_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{\"to\": \"${SMS_RECIPIENT}\", \"message\": \"${message}\"}" \
            --connect-timeout 5 --max-time 10; then
            return 0
        fi
    done
}
```

## GitOps Deployment

We manage everything via Flux GitOps. The configuration lives in:

```
gitops/clusters/homelab/infrastructure/nut-pve/
├── configmap-nut-scripts.yaml      # nut-notify.sh with SMS function
├── configmap-deploy-script.yaml    # Deploys configs to pve via SSH
├── cronjob-nut-deploy.yaml         # Hourly sync
├── cronjob-disaster-drill.yaml     # Monthly test
└── secrets/
    └── sms-gateway-creds.sops.yaml # Encrypted credentials
```

### Credentials Management (SOPS)

Sensitive values are encrypted with SOPS/age:

```bash
./scripts/sops/add-secret.sh \
  --name sms-gateway-creds \
  --namespace monitoring \
  SMS_GATEWAY_TOKEN="your-token" \
  SMS_GATEWAY_IP="192.168.x.x" \
  SMS_RECIPIENT="+1234567890" \
  HOTSPOT_SSID="Your_Hotspot" \
  HOTSPOT_PASSWORD="password"
```

The deploy job injects these as environment variables, then writes them to pve:

```bash
{
  echo "export SMS_GATEWAY_IP=\"${SMS_GATEWAY_IP}\""
  echo "export SMS_GATEWAY_TOKEN=\"${SMS_GATEWAY_TOKEN}\""
  # ...
} | ssh root@pve "cat > /root/.sms-gateway-env"
```

### Monthly Disaster Drill

Trust but verify. A cronjob runs on the first Saturday of each month:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nut-disaster-drill
spec:
  schedule: "0 10 1-7 * 6"  # First Saturday, 10 AM
```

It SSHs to pve and sends a test SMS. If you don't receive it, something's broken.

## Testing the Setup

### 1. Basic Connectivity Test

```bash
# From your Mac/laptop on same network as phone
curl -X POST "http://<phone-ip>:8082/" \
  -H "Authorization: <token>" \
  -H "Content-Type: application/json" \
  -d '{"to": "+1234567890", "message": "Test from Mac"}'
```

### 2. Hotspot Path Test

```bash
# Connect Mac to phone's hotspot
# Phone IP changes - check SMS Gateway app for new IP
curl -X POST "http://<hotspot-ip>:8082/" \
  -H "Authorization: <token>" \
  -H "Content-Type: application/json" \
  -d '{"to": "+1234567890", "message": "Test via hotspot"}'
```

### 3. Full Integration Test

```bash
# On pve, switch to hotspot
iwctl station wlan0 disconnect
iwctl station wlan0 connect Your_Hotspot

# Get gateway IP
ip route show dev wlan0 | grep default

# Send test SMS
curl -X POST "http://<gateway-ip>:8082/" \
  -H "Authorization: <token>" \
  -H "Content-Type: application/json" \
  -d '{"to": "+1234567890", "message": "Test from pve via hotspot"}'

# Reconnect to main WiFi
iwctl station wlan0 connect your-main-wifi
```

### 4. Simulate Power Outage

The real test: unplug your router.

1. Server loses main WiFi
2. iwd connects to phone hotspot
3. Manually trigger UPS event: `NOTIFYTYPE=ONBATT /root/nut-notify.sh`
4. Receive SMS

## Lessons Learned

### 1. Android Hotspot IPs Are Dynamic

We initially hardcoded the SMS gateway IP. Bad idea. Android assigns different IPs to the hotspot interface depending on... reasons. The solution: detect the gateway IP dynamically from the routing table.

### 2. WiFi + Hotspot Works Simultaneously

This was a pleasant surprise. The Pixel 7 can be connected to home WiFi AND run a hotspot. The hotspot uses cellular as backhaul only when WiFi is unavailable. This means:
- Phone stays online via WiFi normally
- Hotspot is always available
- Automatic cellular fallback when needed

### 3. iwd Just Works

No complex failover scripts needed. iwd automatically connects to known networks by signal strength and availability. When one disappears, it tries the next.

### 4. Test Monthly

SMS is not something you use daily. Things break silently:
- Phone OS update disables SMS Gateway
- Cellular plan expires
- Token gets invalidated

The monthly drill catches these before a real emergency.

## Alternative Approaches Considered

### Twilio/Cloud SMS
- **Pro**: No hardware needed
- **Con**: Requires internet (defeats the purpose)

### Cellular Modem on Server
- **Pro**: Direct cellular, no phone needed
- **Con**: $100+ hardware, monthly SIM plan, complex setup

### Satellite (Starlink Mini)
- **Pro**: True independence from terrestrial infrastructure
- **Con**: $300 hardware + $50/month, overkill for notifications

### Dedicated SMS Gateway Hardware
- **Pro**: Purpose-built, reliable
- **Con**: $200+ devices, still need SIM plan

The "old Android phone + cheap MVNO" approach hits the sweet spot of cost, simplicity, and reliability.

## Conclusion

For ~$30/year ongoing cost, you get SMS notifications that work even when your entire network infrastructure is down. The setup takes an afternoon, and the peace of mind is worth it.

The key insight: you probably have an old Android phone in a drawer. That phone + the cheapest cellular plan available = robust out-of-band notifications.

**Total setup:**
1. Old Android phone + charger
2. Helium Mobile Zero eSIM (~$30/year)
3. Traccar SMS Gateway app (free)
4. WiFi adapter on server (if needed)
5. A few config files

When the next power outage hits at 3 AM, you'll get an SMS telling you exactly what's happening to your homelab.

---

*Tags: homelab, disaster-recovery, UPS, SMS, out-of-band, notifications, NUT, Proxmox, GitOps, Helium-Mobile, Android, hotspot, iwd*
