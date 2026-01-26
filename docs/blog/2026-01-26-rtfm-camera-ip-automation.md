# RTFM: How Reading the Manual Would Have Saved Hours of Automation Work

**Date**: January 26, 2026
**Author**: Claude + Human collaboration
**Tags**: rtfm, automation, dhcp, home-assistant, frigate, lessons-learned

---

## The Problem I Thought I Had

Every Sunday morning, my Reolink cameras reboot for scheduled maintenance. DHCP assigns them new IPs. Frigate loses the feeds. I wake up to dead cameras.

"The AT&T router doesn't support persistent DHCP reservations," I told myself. "I've set them up before and they disappeared after a router reboot."

So I built a solution.

## The Over-Engineered Solution

Over several hours, I created:

1. **A Python script** that runs nmap scans to discover cameras by MAC address
2. **A Home Assistant sensor** that polls the script every 5 minutes
3. **A state-based automation** that detects IP changes
4. **A Kubernetes webhook** (Flask app) that patches Frigate's ConfigMap
5. **A GitHub Action** to build and push the webhook container
6. **Traefik IngressRoute** to expose the webhook
7. **Reloader** to auto-restart Frigate when the ConfigMap changes

```
Camera reboot → DHCP assigns new IP → nmap detects → HA sensor updates →
automation triggers → REST call to webhook → ConfigMap patched →
Reloader restarts Frigate → streams reconnect
```

Beautiful. Elegant. Completely unnecessary.

## The Actual Solution

After all that work, I went back to the AT&T router to document the "limitation" for future reference. That's when I actually read the help text:

> **Help**
>
> The IP Allocation table lists DHCP clients and IP Allocated clients. You may want to create an IP Allocated client so that it will always get the same IP address.
>
> To create an IP Allocated client select the Allocate button next to the client. **The IP Allocation Entry section appears.** Choose a Fixed address for the client and click "Save".

The IP Allocation Entry section appears. **Below the fold. Where I never scrolled.**

For months, I had been clicking "Allocate," seeing nothing happen (because the form appeared below my viewport), and concluding the feature was broken.

The fix took 30 seconds per device:
1. Click "Allocate"
2. **Scroll down**
3. Select "Private fixed:192.168.1.xxx"
4. Click "Save"

## What I Actually Built vs What I Needed

| What I Built | Time Spent | What I Needed |
|--------------|------------|---------------|
| Python nmap scanner | 30 min | Nothing |
| HA command_line sensor | 20 min | Nothing |
| State change automation | 15 min | Nothing |
| K8s webhook (Flask) | 45 min | Nothing |
| GitHub Action for container | 15 min | Nothing |
| Traefik IngressRoute | 10 min | Nothing |
| Reloader deployment | 20 min | Nothing |
| Testing & debugging | 60 min | Nothing |
| **Total** | **~4 hours** | **2 minutes** |

## The Layers of Failure

1. **Didn't scroll** - The form appeared below the viewport
2. **Assumed it was broken** - "AT&T routers are garbage" confirmation bias
3. **Didn't re-read the docs** - I "knew" how it worked
4. **Built around the "limitation"** - Classic engineering instinct
5. **Didn't question the premise** - Why would enterprise routers not support DHCP reservations?

## The Silver Linings

The automation work wasn't entirely wasted:

- **Reloader** is genuinely useful - any ConfigMap change now auto-restarts affected pods
- **The nmap discovery script** could be useful for inventory/monitoring
- **The blog post** I wrote documents a real pattern for dynamic IP handling
- **I learned** more about HA state triggers vs attribute triggers

And the auto-sync system is now a backup. If the router allocations ever fail, the automation will catch it.

## Lessons Learned

### 1. Scroll the Entire Page
Enterprise UIs from 2005 love putting forms below the fold with no visual indication.

### 2. Re-Read the Docs When Stuck
"I already tried that" often means "I tried something similar once and made assumptions."

### 3. Question Your Premises
"The router doesn't support X" should prompt: "Are you sure? Did you actually verify this?"

### 4. Simple Solutions First
Before building a distributed system to work around a limitation, verify the limitation exists.

### 5. Document Anyway
Even though I didn't need the automation, the IP assignments are now documented with MAC addresses for when I replace the router.

## The Final State

```
AT&T Router IP Allocation:
├── 192.168.1.107 - TPLINK-WEBCAM (Fixed)
├── 192.168.1.137 - Hall camera (Fixed)
├── 192.168.1.138 - Living camera (Fixed)
├── 192.168.1.124 - homeassistant (Fixed)
├── 192.168.1.131 - OPNsense (Fixed)
└── 192.168.1.110 - cloudflared (Fixed)

Automation status: Still deployed, hopefully never triggers
```

## Conclusion

RTFM isn't just for others. It's for me. It's for you. It's for everyone who "already knows" how something works.

The most dangerous phrase in engineering isn't "I don't know how to do this." It's "I already tried that."

---

*Time spent writing this blog post: 15 minutes*
*Time I would have saved by scrolling down: 4 hours*
