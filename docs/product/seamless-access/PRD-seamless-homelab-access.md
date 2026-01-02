# PRD: Seamless Homelab Access

**Author**: Nikhil
**Date**: 2026-01-01
**Status**: Draft
**Priority**: High

---

## Problem Statement

Currently, accessing homelab services requires different URLs and mental context switches depending on location:
- At home: `192.168.4.x` IPs or broken `.homelab` fake TLD
- Away: Tailscale MagicDNS names or raw Tailscale IPs
- No valid TLS certificates (browser warnings, HA app complains)
- MAAS DNS won't forward `.homelab` to OPNsense (unfixable without breaking provisioning)

**User frustration**: "I just want to type the same URL everywhere and have it work."

---

## User Personas

**Primary User**: Nikhil (me)
- Software engineer, homelab enthusiast
- Uses MacBook, iPhone, Voice PE (ESP32)
- Wants zero-friction access to home infrastructure

---

## Access Scenarios

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENARIO 1: AT HOME - COUCH (iPhone)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   ┌──────────────┐        ┌──────────────┐
   │  iPhone      │───────▶│   Home       │──────▶ Frigate (camera alerts)
   │  HA App      │  WiFi  │  Assistant   │──────▶ Ollama (LLM commands)
   └──────────────┘        │ 192.168.4.240│──────▶ Meross lights
         │                 └──────────────┘
         │
         │  "Hey Claude,          ┌──────────────┐
         │   approve PR"          │  Voice PE    │
         └───────────────────────▶│  ESP32       │──▶ HA ──▶ ClaudeCodeUI
                                  └──────────────┘

   CURRENT: Works via IP or ha.home.panderosystems.com (no valid cert)
   WANT: ha.home.panderosystems.com with valid TLS cert (green lock)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENARIO 2: AT HOME - DESK (MacBook + Claude Code)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   ┌──────────────┐
   │  MacBook     │
   │  Claude Code │
   └──────┬───────┘
          │
          ├────▶ kubectl ──────────────────────────▶ K3s API
          │
          ├────▶ grafana.app.home.panderosystems.com ──▶ Traefik ──▶ Grafana
          │
          ├────▶ frigate.app.home.panderosystems.com ──▶ Traefik ──▶ Frigate
          │
          └────▶ ollama.app.home.panderosystems.com ──▶ Traefik ──▶ Ollama

   CURRENT: .homelab domains broken (MAAS DNS issue), no certs
   WANT: .home.panderosystems.com with valid TLS, working DNS


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENARIO 3: AWAY - COFFEE SHOP / AIRPORT (MacBook + Tailscale)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   ┌──────────────┐         ┌─────────────┐         ┌─────────────────────┐
   │  MacBook     │────────▶│  Tailscale  │────────▶│  Home Network       │
   │  Claude Code │  Public │  WireGuard  │  Tunnel │  192.168.4.0/24     │
   └──────────────┘  WiFi   └─────────────┘         └─────────────────────┘
          │                                                   │
          │                                                   ▼
          │  grafana.app.home.panderosystems.com     ┌───────────────┐
          │  frigate.app.home.panderosystems.com     │ Same services │
          │  ha.home.panderosystems.com              │ Same URLs     │
          └─────────────────────────────────────────▶│ Same certs    │
                    (EXACT SAME URLs as at home)     └───────────────┘

   CURRENT: Must use Tailscale IPs or MagicDNS (different mental model)
   WANT: SAME FQDNs work - just connect Tailscale and go


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENARIO 4: AWAY - PHONE (iPhone + Tailscale)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   ┌──────────────┐         ┌─────────────┐         ┌─────────────────────┐
   │  iPhone      │────────▶│  Tailscale  │────────▶│  Home Network       │
   │  HA App      │   LTE   │  WireGuard  │  Tunnel │                     │
   └──────────────┘         └─────────────┘         └─────────────────────┘
          │                                                   │
          ├──▶ ha.home.panderosystems.com ───────────────────▶ HA VM
          │                                                   │
          └──▶ frigate.app.home.panderosystems.com ──────────▶ Frigate
                 (check cameras, review clips)

   CURRENT: HA app uses Nabu Casa or direct IP
   WANT: Same FQDN, valid cert, no Nabu Casa dependency


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENARIO 5: INTERNAL SERVICES (Machine-to-Machine)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   ┌─────────────────────────────────────────────────────────────────────────┐
   │                         CAMERA SUBNETS                                   │
   │                                                                         │
   │   192.168.1.x (IoT)       192.168.86.x (Google)    192.168.4.x (Main)  │
   │   ┌─────────────┐         ┌─────────────┐          ┌─────────────┐     │
   │   │Reolink Door │         │ WiFi Cams   │          │ PoE Cams    │     │
   │   └──────┬──────┘         └──────┬──────┘          └──────┬──────┘     │
   │          │ RTSP                  │ RTSP                   │ RTSP       │
   │          └───────────────────────┴────────────────────────┘            │
   │                                  │                                      │
   │                                  ▼                                      │
   │                          ┌───────────────┐                             │
   │                          │   FRIGATE     │◀────── Coral TPU            │
   │                          │ Object Detect │                             │
   │                          └───────┬───────┘                             │
   │                                  │                                      │
   │              ┌───────────────────┼───────────────────┐                 │
   │              ▼                   ▼                   ▼                 │
   │        ┌──────────┐        ┌──────────┐        ┌──────────┐           │
   │        │    HA    │        │  Ollama  │        │ Grafana  │           │
   │        │ (events) │        │(LLM vis) │        │(metrics) │           │
   │        └──────────┘        └──────────┘        └──────────┘           │
   │                                                                         │
   │   CURRENT: HA uses frigate.app.homelab (BROKEN - MAAS DNS)            │
   │   WANT: HA uses frigate.app.home.panderosystems.com                   │
   └─────────────────────────────────────────────────────────────────────────┘
```

---

## Requirements

### Must Have (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| P0-1 | Same FQDN works at home and via Tailscale | `grafana.app.home.panderosystems.com` resolves and loads from both locations |
| P0-2 | Valid LetsEncrypt TLS certificates | No browser warnings, green lock in HA app |
| P0-3 | Wildcard cert for K8s services | `*.app.home.panderosystems.com` cert issued and auto-renewed |
| P0-4 | HA VM has valid cert | `ha.home.panderosystems.com` with TLS (not in K8s) |
| P0-5 | Internal services can use FQDNs | HA can reach `frigate.app.home.panderosystems.com` |

### Should Have (P1)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| P1-1 | Google OAuth SSO | Login to Grafana with Google account |
| P1-2 | No public internet exposure | OAuth works without exposing services publicly |
| P1-3 | GitOps managed | All config in Flux, SOPS for secrets |

### Nice to Have (P2)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| P2-1 | Authelia/Authentik for SSO | Single auth proxy for all services |
| P2-2 | Automatic cert distribution to VMs | HA gets cert without manual steps |

---

## Current State

| Component | Status | Notes |
|-----------|--------|-------|
| Domain (panderosystems.com) | ✅ Owned | Cloudflare managed |
| external-dns | ✅ Running | Syncing DNSEndpoints to Cloudflare |
| DNSEndpoint for wildcard | ✅ Exists | `*.app.home.panderosystems.com` → 192.168.4.80 |
| Tailscale subnet router | ✅ Running | Advertising 192.168.4.0/24 |
| cert-manager | ❌ Not deployed | No namespace, no CRDs |
| ClusterIssuer (DNS-01) | ❌ Not created | Need Cloudflare solver |
| Wildcard certificate | ❌ Not issued | Blocked by cert-manager |
| Traefik TLS config | ❌ Not configured | Using self-signed or none |
| HA VM certificate | ❌ None | No automation |

---

## Constraints

1. **Cannot change MAAS DHCP/DNS** - Breaks bare-metal provisioning
2. **No public internet exposure** - Services only accessible via LAN or Tailscale
3. **GitOps managed** - Flux for K8s, SOPS for secrets
4. **Traefik as ingress** - Not switching to Caddy/NGINX

---

## Success Metrics

| Metric | Target |
|--------|--------|
| URL consistency | 100% - same URL works at home and away |
| TLS coverage | 100% - all services have valid certs |
| Manual intervention | 0 - certs auto-renew |
| Time to access from new location | <10s (connect Tailscale, go) |

---

## Out of Scope

- Public-facing services (no port forwarding)
- Multi-user access (just me for now)
- Service mesh / mTLS between pods

---

## Open Questions

1. **OAuth callback**: Can Google OAuth work with Tailscale-only access?
2. **HA cert automation**: Certbot on VM or cert-manager + cert-sync?
3. **Split DNS**: Do we need internal DNS override or is Cloudflare + Tailscale enough?

---

## References

- [Tailscale Split DNS](https://tailscale.com/learn/why-split-dns)
- [cert-manager DNS-01](https://cert-manager.io/docs/configuration/acme/dns01/)
- [Homelab via Tailscale](https://aottr.dev/posts/2024/08/homelab-using-the-same-local-domain-to-access-my-services-via-tailscale-vpn/)

---

## Tags

`homelab, tailscale, letsencrypt, cert-manager, dns, cloudflare, oauth, sso, prd`
