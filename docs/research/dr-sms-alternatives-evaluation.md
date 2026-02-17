# DR SMS Alternatives Evaluation

**Date**: 2026-02-16
**Status**: NO-GO - Stick with Helium Mobile
**Current Solution**: Helium Mobile Zero (~$2.50/month taxes only)

## Problem Statement

Evaluate cheaper alternatives to Helium Mobile for disaster recovery SMS alerts when home internet is down.

## Current Solution: Helium Mobile Zero

- **Cost**: ~$30/year (taxes only, plan is free)
- **Hardware**: Old Pixel 7 running Traccar SMS Gateway
- **How it works**: pve connects to phone hotspot when router dies, sends SMS via HTTP API
- **Documented in**: `docs/source/md/blog-out-of-band-sms-disaster-recovery.md`

## Alternatives Evaluated

### 1. 1NCE IoT Lifetime Flat

**Advertised**: $14 for 10 years (500MB + 250 SMS)

**Verdict**: NO-GO - Business customers only

**Details**:
- Requires AWS Marketplace account
- AWS Marketplace requires business registration number
- "1NCE For All" free developer program also requires business verification
- No path for individual/hobbyist use

### 2. Soracom Arc (Virtual SIM)

**Advertised**: Free tier (1GB/month), WireGuard-based

**Verdict**: NO-GO - Cannot send SMS to regular phones

**Details**:
- Successfully deployed WireGuard pod in K3s (tested, tunnel worked)
- Soracom SMS only works between Soracom SIMs
- Cannot send SMS to personal phone numbers
- Documentation explicitly states: "Sending SMS from an IoT SIM to a non-Soracom SIM device (such as a personal smartphone) is not supported"
- Useful for device-to-cloud data, not human notifications

**What Soracom is actually for**:
- Fleet tracking (trucks sending GPS)
- Smart agriculture (sensors → dashboard)
- Industrial IoT telemetry
- NOT consumer SMS alerts

### 3. Hologram IoT SIM

**Cost**: $3 SIM (FREE with promo code FREEPILOTSIM) + $1/month + $0.19/outbound SMS

**Verdict**: TECHNICALLY VIABLE but not worth it

**Annual cost**: ~$13/year (vs $30/year Helium Mobile)

**Problem**: Requires USB LTE modem hardware

**Hardware situation**:
- Huawei E3372-325 (best option): **Currently unavailable** on Amazon
- Quectel EC25-AF dongles: Hard to find, mostly out of stock
- AliExpress options: ~$52 + 2-3 week shipping
- USB LTE modems are a dying market (smartphones killed demand, Huawei sanctions reduced supply)

**Break-even analysis**:
| Year | Hologram + $52 Dongle | Helium Mobile |
|------|----------------------|---------------|
| 1 | $65 | $30 |
| 2 | $78 | $60 |
| 3 | $91 | $90 |
| 4 | $104 | $120 |

Break-even at ~2.5 years, plus hours of setup time (Linux drivers, AT commands, scripts).

### 4. Other IoT SIM Providers

| Provider | Issue |
|----------|-------|
| Things Mobile | Similar pricing to Hologram, same hardware problem |
| Telnyx | Business-focused |
| Twilio | Requires internet (defeats purpose) |

### 5. Satellite Options

| Provider | Cost | Notes |
|----------|------|-------|
| Swarm (SpaceX) | $5/month + $119 hardware | Overkill for SMS alerts |
| Iridium SBD | $14+/month + $200+ hardware | Way overkill |

## Why USB LTE Modems Are Hard to Find

1. **Smartphones killed the market** - Everyone tethers phones now
2. **IoT went embedded** - Businesses solder M.2 modules, don't buy USB dongles
3. **Huawei sanctions** - They made 80% of cheap USB modems
4. **No consumer demand** - Tiny niche market (homelabbers, preppers)

## Decision

**STICK WITH HELIUM MOBILE**

Reasons:
- Already working, zero additional setup
- $30/year is cheap enough
- Phone can do more than just SMS (HA app, voice calls, hotspot)
- No hardware hunting or maintenance
- Time has value - hours spent on $17/year savings is not worth it

## Files Created/Removed

- **Removed**: `gitops/clusters/homelab/apps/soracom-arc/` (WireGuard pod - worked but useless for SMS)
- **Created**: This document

## Future Considerations

Revisit if:
- Helium Mobile raises prices significantly
- USB LTE modems become readily available again
- A true hobbyist-friendly IoT SMS provider emerges

## Tags

dr, disaster-recovery, sms, helium-mobile, soracom, hologram, 1nce, iot, cellular, lte, usb-modem, no-go, evaluation
