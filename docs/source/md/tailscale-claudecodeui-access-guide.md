# Plan: Access Claude Code Web UI via Tailscale

## TL;DR - Everything is Already Set Up!

Your infrastructure is fully configured. This is purely a verification/setup task:

| Scenario | Network | Action Needed |
|----------|---------|---------------|
| Mac at Office | Any | Connect Tailscale, access `claude.app.homelab` |
| Phone on Google WiFi | 192.168.86.X | Install Tailscale, enable subnet routes |
| Phone on AT&T | 192.168.1.X | Install Tailscale, enable subnet routes |

---

## Current State (Already Configured)

| Component | Configuration | Status |
|-----------|---------------|--------|
| Claude Code UI | `claude.app.homelab` → Traefik (192.168.4.80) → ClusterIP:3001 | Deployed |
| Blue variant | `claude-blue.app.homelab` → port 3001 (MQTT-enabled) | Deployed |
| Tailscale Subnet Router | Pod `ts-homelab-router` advertising 192.168.4.0/24 | Running |
| Split DNS | `homelab` → 192.168.4.1 (OPNsense) with "Use with exit node" | Configured |

Reference docs:
- `docs/source/md/blog-tailscale-split-dns-homelab.md`
- `docs/source/md/tailscale-k3s-setup-guide.md`

---

## Scenario 1: Mac at Office

**This should already work.** Split DNS is configured per your docs.

### Verification Steps

```bash
# 1. Ensure Tailscale is connected
tailscale status

# 2. Verify subnet router is visible
tailscale status | grep ts-homelab-router
# Expected: 100.x.x.x  ts-homelab-router  tagged-devices  linux  idle; offers exit node

# 3. Test DNS resolution (Split DNS)
nslookup claude.app.homelab
# Expected: Server 100.100.100.100 → Address 192.168.4.80

# 4. Test connectivity
curl -I http://claude.app.homelab/
# Expected: HTTP/1.1 200 OK
```

### If DNS Doesn't Resolve

Check Split DNS settings at https://login.tailscale.com/admin/dns:

| Setting | Expected Value |
|---------|----------------|
| Nameserver | 192.168.4.1 |
| Restrict to domain | enabled |
| Domain | homelab |
| Use with exit node | enabled |

### Quick Workaround (if needed)

```bash
# Bypass DNS entirely - access by IP with Host header
curl -H "Host: claude.app.homelab" http://192.168.4.80/
```

---

## Scenario 2: Phone at Home (192.168.1.X or 192.168.86.X)

**Problem:** Phone on Google WiFi (192.168.86.X) or AT&T (192.168.1.X) cannot reach homelab (192.168.4.X) - different subnets, no route between them.

**Solution:** Install Tailscale on phone.

### Setup Steps

1. **Install Tailscale**
   - iOS: App Store → "Tailscale"
   - Android: Play Store → "Tailscale"

2. **Sign In**
   - Use same account as your Mac

3. **Enable Subnet Routes**
   - iOS: Settings → Enable "Use subnet routes"
   - Android: Menu → Settings → Enable "Use subnet routes"

4. **Access Claude Code UI**
   - Open browser: `http://claude.app.homelab`
   - Or direct: `http://192.168.4.80` (Traefik will serve default)

### Why This Works

```
Phone (192.168.86.X - Google WiFi)     Phone (192.168.1.X - AT&T)
              │                                   │
              └─────────────┬─────────────────────┘
                            ↓ Tailscale VPN tunnel
                    Tailnet Mesh (100.x.x.x)
                            ↓ Subnet Route
                  ts-homelab-router (K3s pod)
                            ↓ 192.168.4.0/24
                    Traefik (192.168.4.80)
                            ↓ Ingress
                      claudecodeui:3001
```

---

## Architecture Diagram

```
                        HOME NETWORKS (isolated from homelab)
    ┌──────────────────────────────────────────────────────────────┐
    │  Google WiFi          AT&T Router         Work/Office        │
    │  192.168.86.0/24      192.168.1.0/24      (any network)      │
    │       │                    │                   │             │
    │  ┌────┴────┐          ┌────┴────┐        ┌────┴────┐        │
    │  │  Phone  │          │  Phone  │        │   Mac   │        │
    │  │ Android │          │   iOS   │        │         │        │
    │  └────┬────┘          └────┬────┘        └────┬────┘        │
    └───────┼────────────────────┼──────────────────┼──────────────┘
            │                    │                  │
            └────────────────────┼──────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │    TAILSCALE TAILNET    │
                    │      (100.x.x.x)        │
                    │                         │
                    │  Split DNS configured:  │
                    │  homelab → 192.168.4.1  │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  ts-homelab-router      │
                    │  (K3s subnet router)    │
                    │                         │
                    │  Advertises:            │
                    │  • 192.168.4.0/24       │
                    │  • 10.42.0.0/16 (pods)  │
                    │  • 10.43.0.0/16 (svcs)  │
                    └────────────┬────────────┘
                                 │
    ┌────────────────────────────▼─────────────────────────────────┐
    │                   HOMELAB 192.168.4.0/24                     │
    │                                                              │
    │   ┌─────────────────────────────────────────────────────┐   │
    │   │              Traefik @ 192.168.4.80                 │   │
    │   │                        │                            │   │
    │   │         ┌──────────────┼──────────────┐            │   │
    │   │         │              │              │            │   │
    │   │   claude.app    claude-blue.app   grafana.app      │   │
    │   │   .homelab        .homelab        .homelab         │   │
    │   │         │              │              │            │   │
    │   │         └──────────────┼──────────────┘            │   │
    │   │                        ▼                            │   │
    │   │              claudecodeui pod :3001                 │   │
    │   └─────────────────────────────────────────────────────┘   │
    └──────────────────────────────────────────────────────────────┘
```

---

## URLs for Access

| URL | Works From | Notes |
|-----|------------|-------|
| `http://claude.app.homelab` | Mac (office), Phone (Tailscale) | Primary URL |
| `http://claude-blue.app.homelab` | Mac (office), Phone (Tailscale) | Blue/test deployment |
| `http://192.168.4.80` | Any Tailscale client | Direct IP access |

---

## No Implementation Needed

This is a configuration verification task. No code changes, no new deployments.

### Checklist

- [ ] Verify Mac can access `http://claude.app.homelab` when at office (Tailscale connected)
- [ ] Install Tailscale on phone (iOS/Android)
- [ ] Enable "Use subnet routes" on phone
- [ ] Verify phone can access `http://claude.app.homelab` from Google WiFi (192.168.86.X)
- [ ] Verify phone can access `http://claude.app.homelab` from AT&T (192.168.1.X)

---

## Troubleshooting

### "Connection refused" from Mac at office

1. Check Tailscale is connected: `tailscale status`
2. Check subnet routes approved: https://login.tailscale.com/admin/machines → ts-homelab-router
3. Check K3s cluster is running: `KUBECONFIG=~/kubeconfig kubectl get pods -n tailscale`

### "Name not resolved"

Split DNS may not be propagating:
```bash
# Force DNS resolution via Tailscale
sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder
nslookup claude.app.homelab 100.100.100.100
```

### Phone can't connect

1. Ensure Tailscale app is running (not just installed)
2. Check "Use subnet routes" is enabled in app settings
3. **Re-login via Settings** - go to Tailscale Settings → Log in again, then refresh browser
4. Try direct IP: `http://192.168.4.80` in browser
