# The UPS That Wasn't: A Homelab Lesson

**Date**: 2026-02-15
**Tags**: ups, homelab, power, lessons-learned, infrastructure, nut

## The 15-Minute Morning Scramble

It's 9 AM. Power was out overnight. My Mac's USB Ethernet adapter shows `169.254.185.72` - a link-local address. No DHCP. No homelab access.

Time to play network detective instead of drinking coffee.

## The Recovery Dance

Here's what a power outage recovery looks like when your DHCP server (MAAS) is down:

1. **Find the USB adapter** - It's `en10`, not `en4`. Always forget this.
2. **Assign a static IP** - `sudo ifconfig en10 192.168.4.250`
3. **Ping the Proxmox host** - Timeout. Wait. Try again. Success.
4. **Check MAAS VM** - Already running (auto-start configured correctly!)
5. **Wait for MAAS services** - DHCP takes a minute to come up
6. **Release static, get DHCP** - `sudo ipconfig set en10 DHCP`
7. **Verify everything** - Ping the fleet. All hosts responding.

Ten minutes of my morning, gone. But here's the kicker.

## The Plot Twist

```bash
ssh root@pve "uptime"
09:25:18 up 3 min, 0 users
```

Three minutes. My main Proxmox host had been up for *three minutes*.

The UPS sitting under my desk? The CyberPower CP1500 I bought specifically for situations like this? It was there the whole time. But pve was plugged into a surge-only outlet, not the battery-backed outlets.

The UPS did its job perfectly. I just never gave it the right job.

## How UPS Outlets Work (TIL)

Most consumer UPS units have two types of outlets:

```
┌─────────────────────────────────────────┐
│  CyberPower CP1500                      │
│                                         │
│  BATTERY + SURGE    │    SURGE ONLY     │
│  ┌───┐ ┌───┐ ┌───┐ │ ┌───┐ ┌───┐ ┌───┐ │
│  │ 1 │ │ 2 │ │ 3 │ │ │ 4 │ │ 5 │ │ 6 │ │
│  └───┘ └───┘ └───┘ │ └───┘ └───┘ └───┘ │
│  ▲                 │                    │
│  └── pve goes HERE │                    │
└─────────────────────────────────────────┘
```

**Battery + Surge**: Power continues during outage. Your server keeps running.

**Surge Only**: Protection from power spikes, but goes dark when power does.

I had pve in a surge-only outlet. Maximum irony.

## The Fix

Physical: Moved pve's power cable to a battery-backed outlet.

But that's only half the story.

## The USB Cable You Forgot About

A UPS without a USB connection to your server is just a dumb battery. It can't tell your server "Hey, power's out, maybe shut down gracefully before I run dry."

```
Without USB:
  Power fails → UPS powers server → Battery depletes → Hard crash

With USB (NUT configured):
  Power fails → UPS tells server → Server shuts down VMs gracefully → Safe
```

The CyberPower came with a USB cable. It was still in the box.

## NUT: Network UPS Tools

Once the USB cable connects UPS to pve, you need software to interpret the signals:

```bash
apt install nut

# Configure driver
cat >> /etc/nut/ups.conf << 'EOF'
[ups]
    driver = usbhid-ups
    port = auto
    desc = "CyberPower CP1500"
EOF

# Configure monitoring
echo 'MONITOR ups@localhost 1 admin secret master' >> /etc/nut/upsmon.conf
echo 'SHUTDOWNCMD "/sbin/shutdown -h +0"' >> /etc/nut/upsmon.conf
```

Now when battery hits critical level, pve shuts down gracefully. VMs get proper ACPI shutdown signals. No corruption. No fsck party at next boot.

## BIOS: Restore on AC Power Loss

There's one more piece: what happens when power comes back?

Most BIOS defaults to "Power Off" - after a power loss, the machine stays off until you press the power button. Useless for headless servers.

Set this to "Last State" (sometimes called "Restore" or "Previous"):

```
BIOS → Power Management → Restore on AC Power Loss → Last State
```

**"Last State"** means:
- If the server was ON when power died → auto-power-on when power returns
- If it was OFF → stay off

This should be standard for every homelab machine: pve, still-fawn, chief-horse, pumped-piglet - all of them. No more manually power-cycling servers after an outage.

## The Math

**Brief outage (< 15 minutes)**:
- Without proper UPS: 10-minute recovery scramble
- With proper UPS: Zero downtime, zero scramble

**Extended outage (> battery life)**:
- Without NUT: Hard shutdown, potential corruption, longer recovery
- With NUT: Graceful shutdown, clean boot when power returns

## Lessons

1. **Having a UPS isn't enough** - Plug critical hosts into battery outlets
2. **Connect the USB cable** - Enables graceful shutdown
3. **Configure NUT** - Software turns dumb battery into smart power management
4. **Set BIOS to "Last State"** - Servers should auto-power on when AC returns
5. **Document your recovery** - Next time it's a runbook, not an adventure

## The Real Cost

The UPS cost $150. The USB cable was free (included). NUT is free (open source).

The 15-minute scramble this morning? Priceless frustration that was entirely preventable.

Next power outage, I'll be drinking coffee while my homelab rides it out. Or gracefully shuts down and waits for power to return. Either way, no more `169.254.x.x` debugging sessions.

---

*Related: [MAAS Power-Cut Recovery Runbook](../runbooks/maas-power-cut-recovery.md)*
