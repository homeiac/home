# DNS Is Still Broken

**Date**: 2026-01-18
**Tags**: dns, homelab, rant, lessons-learned

## The Pattern

Every few weeks, something breaks. The symptom is always the same:

```
lookup reolink-vdb.homelab: no such host
```

Or:
```
connection refused to frigate.homelab
```

Or:
```
cannot resolve homeassistant.maas
```

## The DNS Chain From Hell

```
┌─────────────────────────────────────────────────────────────────┐
│  K3s Pod                                                        │
│    └─→ CoreDNS                                                  │
│          └─→ MAAS DNS (192.168.4.53)                           │
│                └─→ ??? (doesn't know .homelab)                  │
│                                                                 │
│  OPNsense Unbound (has .homelab records)                       │
│    └─→ NOT in the chain for K3s!                               │
└─────────────────────────────────────────────────────────────────┘
```

MAAS DNS doesn't know about `.homelab` domains. OPNsense Unbound has them, but K3s pods don't query Unbound.

## Time Spent on DNS

| Incident | Hours Wasted | Root Cause |
|----------|--------------|------------|
| Frigate can't reach cameras | 3 | Used hostname instead of IP |
| HA can't reach Frigate | 2 | `.homelab` not resolvable from HAOS |
| Reolink doorbell errors | 4 | `reolink-vdb.homelab` → no such host |
| Ollama not responding | 2 | DNS timeout to `ollama.homelab` |
| **Total** | **11+ hours** | |

## The "Solutions" That Don't Last

1. **Add forward zone to MAAS** → Works until MAAS restarts
2. **Use FQDN** (`.home.panderosystems.com`) → Works sometimes, not from all contexts
3. **Add to /etc/hosts** → Doesn't persist in containers/VMs
4. **ExternalDNS** → Complex, another thing to break

## The Only Thing That Works

**IP addresses.**

```yaml
# BAD - will break randomly
reolink_doorbell: "rtsp://user:pass@reolink-vdb.homelab:554/stream"

# BAD - works sometimes
reolink_doorbell: "rtsp://user:pass@reolink-vdb.home.panderosystems.com:554/stream"

# GOOD - always works
reolink_doorbell: "rtsp://user:pass@192.168.1.10:554/stream"
```

## Current Policy

For anything that needs to be reliable:

| Use Case | Use IP | Use DNS |
|----------|--------|---------|
| Camera RTSP streams | ✅ | ❌ |
| Service-to-service in K3s | ❌ | ✅ (K8s DNS works) |
| Cross-network (K3s → LAN device) | ✅ | ❌ |
| Browser access | ❌ | ✅ (Traefik ingress) |
| Automations calling external devices | ✅ | ❌ |

## Lessons Learned

1. **DNS adds complexity without benefit** for static LAN devices
2. **K8s internal DNS works fine** - it's cross-network resolution that breaks
3. **IP addresses don't lie** - if the device is reachable, IP works
4. **Document the IPs** - keep `proxmox/homelab/.env` updated with all device IPs
5. **Don't trust "it worked yesterday"** - DNS caches expire, services restart

## The Camera IP Reference

Since I'll forget:

| Device | IP | Notes |
|--------|-----|-------|
| Reolink doorbell | 192.168.1.10 | RTSP + ONVIF |
| Living room camera | 192.168.1.140 | RTSP + ONVIF |
| Trendnet office cam | 192.168.1.107 | RTSP only |
| Old MJPEG camera | 192.168.1.220 | HTTP MJPEG |

## Conclusion

DNS is great for:
- Human-readable URLs in browsers
- Service discovery within a single cluster

DNS is terrible for:
- Cross-network device communication
- Anything that needs to "just work" at 3 AM

When in doubt, use the IP.
