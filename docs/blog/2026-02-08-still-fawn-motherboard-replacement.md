# Still-Fawn Dies Again: Motherboard Edition

**Date**: February 8, 2026
**Symptom**: Stuck at "Press F2/DEL" - won't POST
**Root cause**: Dead ASUS B85M-G R2.0 motherboard
**Solution**: $60 replacement board (same model)

## The Failure

Still-fawn has been through a lot:
- October 2025: PSU failure (11 years old, couldn't handle GPU power spikes)
- January 2026: Boot SSD failure (KingSpec - you get what you pay for)
- February 2026: Motherboard failure (this post)

This time the symptom was different. Not a "cannot import rpool" ZFS error. Not random shutdowns. The system wouldn't even POST. Stuck at the BIOS splash screen - "Press F2 to enter Setup, DEL to enter BIOS" - and nothing happens.

Tried:
- Removing CMOS battery, waiting, reinstalling
- Clearing CMOS via jumper
- Removing GPU, booting with integrated graphics
- Removing all but 1 RAM stick
- Full power drain (unplug, hold power 30 seconds)

Nothing worked. The board is dead.

## The Decision: Motherboard vs Complete System

With a dead LGA 1150 motherboard, I had two options:

### Option A: Replace the Motherboard (~$60-80)

Reuse everything: i5-4460, 32GB DDR3, RX 580, SSDs, Coral TPU.

### Option B: Buy a Refurbished Desktop (~$110-180)

Get a Dell OptiPlex 7020 or HP EliteDesk 800 G1 and transplant the parts.

## Why Option B Doesn't Work

I did the research. Here's what I found:

### Dell OptiPlex 7020: VT-d Hidden in BIOS

The Dell OEM BIOS **hides the VT-d option** even though the chipset supports it. For Proxmox GPU passthrough, you need VT-d. Without it, no GPU passthrough. Dell doesn't expose it.

The workaround is flashing Libreboot/coreboot. That's not a quick weekend project.

### Proprietary PSU Connectors

Both Dell and HP use proprietary motherboard power connectors:
- Dell: 8-pin proprietary
- HP: 6-pin proprietary

The stock PSUs are 290-320W. The RX 580 alone needs a 500W system. So you need:
1. A new standard ATX PSU ($50-70)
2. A 24-pin to 8-pin or 24-pin to 6-pin adapter ($10)

Suddenly the "$50 refurb desktop" costs $110-130 before you even power it on.

### HP EliteDesk 800 G1: The "Better" Option

HP does expose VT-d in the BIOS (Security menu). But you still need the PSU swap and adapter. Total cost: $110-180.

## The Math

| Option | Cost | Complexity |
|--------|------|------------|
| Same motherboard (ASUS B85M-G R2.0) | $60 | Drop-in, 30 minutes |
| Different LGA 1150 board | $70-100 | May need BIOS config changes |
| HP EliteDesk 800 G1 + PSU + adapter | $110-180 | Hours of adapter fiddling |
| Dell OptiPlex 7020 | Dead end | VT-d not exposed |

## Why Same Model Wins

The ASUS B85M-G R2.0 I found on eBay:
- $60 shipped
- Same BIOS layout I already know
- VT-d location: Advanced -> System Agent Configuration -> VT-d -> Enabled
- Zero compatibility surprises

When the replacement arrives:
1. Swap board into existing case
2. Clear CMOS jumper
3. Enable VT-d in BIOS
4. Boot Proxmox USB, reinstall
5. Run `poetry run python src/homelab/cluster_manager.py rejoin still-fawn`
6. Done

## DDR3 Is Still Valuable

A brief aside: I considered going modern. Then I looked at DDR4/DDR5 prices in 2026.

I already have 32GB of working DDR3. A modern platform means:
- New motherboard ($100-200)
- New CPU ($150-300)
- New RAM ($100-150 for 32GB DDR4)

That's $350-650 to replace a $60 board. The i5-4460 is old, but it runs Proxmox fine. It handles K3s. It passes through the GPU. Why spend 6x more?

## Redundancy Restored

The real reason I'm fixing still-fawn instead of just running everything on pumped-piglet: **single points of failure**.

When still-fawn died, pumped-piglet became the only K3s control plane node. One more hardware failure and the whole cluster goes down. With two nodes:
- Either can die without losing the cluster
- etcd has quorum redundancy
- Workloads can migrate

$60 for redundancy is cheap.

## The Current State

- **still-fawn**: Waiting for replacement motherboard (ASUS B85M-G R2.0, $60)
- **pumped-piglet**: Running solo as the only K3s node (RTX 3070)
- **Workloads**: All running on pumped-piglet, stable but not redundant

Once the board arrives, I'll have the cluster back to 2 control plane nodes. Then I can stop worrying about pumped-piglet's PSU.

## Lessons Learned

1. **Research VT-d before buying refurb desktops** - OEM BIOSes hide features
2. **Proprietary PSU connectors kill the value proposition** - "$50 desktop" becomes $120
3. **Same model replacement is lowest risk** - known BIOS, known compatibility
4. **DDR3 is worth reusing** - new platform costs 6x more
5. **Hardware redundancy is worth $60** - single node = single point of failure

## The Hardware Saga Continues

| Date | Component | Cause of Death | Cost to Fix |
|------|-----------|----------------|-------------|
| Oct 2025 | PSU | 11 years old | $80 |
| Jan 2026 | Boot SSD | KingSpec quality | $0 (had spare) |
| Feb 2026 | Motherboard | Unknown (age?) | $60 |
| **Total** | | | **$140** |

Still cheaper than a new system. Still running. Still learning.

---

**Parts ordered:**
- ASUS B85M-G R2.0 motherboard (eBay, $60)

**Parts reused:**
- Intel i5-4460
- 32GB DDR3
- AMD RX 580
- T-FORCE 2TB SSD
- Coral USB TPU

**Tags**: hardware-failure, motherboard, asus, b85m, lga-1150, proxmox, still-fawn, redundancy, ddr3, vt-d, gpu-passthrough
