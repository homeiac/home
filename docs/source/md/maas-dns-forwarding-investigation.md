# MAAS DNS Forwarding Investigation Report

## 🕵️ Investigation Summary

**Date:** July 30, 2025  
**Issue:** MAAS DNS server (192.168.4.53) not forwarding `.homelab` domain queries to OPNsense (192.168.4.1)  
**Status:** ❌ **ROOT CAUSE IDENTIFIED**

## 🔍 Key Findings

### 1. MAAS DNS Server Location
- **Discovered:** MAAS DNS runs in VM "UbuntuMAAS" (VM ID 102) on pve host
- **Not on pve host directly** - pve only runs avahi-daemon on port 5353
- **Access:** `ssh gshiva@192.168.4.53` with password `elder137berry`

### 2. BIND9 Configuration Analysis

#### ✅ Forwarders ARE Configured Correctly
```bash
# /var/snap/maas/current/bind/named.conf.options.inside.maas
forwarders {
    192.168.4.1;  # Correct OPNsense IP
};
```

#### ✅ ACL Permissions Are Correct
```bash
acl "trusted" {
    192.168.4.0/24;        # Allows homelab network
    2600:1700:7270:933f::/64;
    localnets;
    localhost;
};
```

#### ✅ MAAS Zones Are Properly Defined
- `maas` domain (authoritative) ✅
- `maas-internal` domain (authoritative) ✅
- Reverse DNS zones ✅
- **No `homelab` zone defined** - should forward ✅

### 3. DNS Resolution Testing Results

| Query Type | Target | Result | Status |
|------------|--------|---------|---------|
| `.maas` domains via MAAS | `still-fawn.maas` → `192.168.4.17` | ✅ Works | Authoritative |
| External domains via MAAS | `google.com` → `142.250.191.78` | ✅ Works | Forwarded |
| `.homelab` via MAAS | `ollama.app.homelab` | ❌ NXDOMAIN | **NOT FORWARDED** |
| `.homelab` via OPNsense | `ollama.app.homelab` → `192.168.4.80` | ✅ Works | Direct query |
| `.homelab` from MAAS host | `ollama.app.homelab` → `192.168.4.80` | ✅ Works | Direct to OPNsense |

### 4. 🎯 **ROOT CAUSE IDENTIFIED**

#### DNS Query Trace Analysis
```bash
dig +trace ollama.app.homelab @192.168.4.53
```

**Result:** MAAS BIND is **NOT** forwarding `.homelab` queries to the configured forwarder (192.168.4.1). Instead, it's sending queries directly to root DNS servers, which return NXDOMAIN for the private `.homelab` domain.

#### Critical Configuration Finding
```bash
# /var/snap/maas/current/bind/named.conf.options.inside.maas
empty-zones-enable no;
dnssec-validation auto;
```

## 🔍 Why Forwarding Is Failing

### Hypothesis 1: BIND Forward Zone Configuration Issue
**Problem:** MAAS BIND may require explicit forward zone definitions for non-standard TLD domains like `.homelab`.

**Standard BIND behavior:**
- Global forwarders work for standard domains (.com, .org, etc.)
- Non-standard TLDs like `.homelab` may need explicit forward zone configuration

### ✅ **CONFIRMED ROOT CAUSE: DNSSEC Validation Blocking Private Domains**
**Problem:** `dnssec-validation auto` prevents forwarding of unsigned private domains like `.homelab`.

**Evidence from MAAS Community:**
- **MAAS Bug #1500683**: "By default DNSSEC is enabled with automatic keys" 
- **MAAS Bug #1513775**: "MAAS didn't parse dnssec-validation automatically"
- **Discourse Thread**: User reported MAAS DNS not forwarding, solved by disabling DNSSEC
- **Technical Explanation**: BIND validates all domains when `dnssec-validation auto` is enabled. Private domains like `.homelab` have no DNSSEC signatures, causing validation to fail and preventing forwarding.

**This is a KNOWN MAAS/BIND9 issue, not a configuration error!**

### Hypothesis 3: Empty Zones Configuration
**Problem:** `empty-zones-enable no` combined with missing explicit forward zones may cause queries to go to root servers instead of forwarders.

## 🛠️ **Recommended Solutions** 

### Option 1: Disable DNSSEC Validation (Fixes Root Cause) ✅
```bash
# Edit /var/snap/maas/current/bind/named.conf.options.inside.maas
# Change:
dnssec-validation auto;
# To:
dnssec-validation no;

# Then restart MAAS named service
sudo systemctl restart snap.maas.named
```

**Pros:**
- ✅ **Fixes the actual root cause** (DNSSEC blocking private domains)
- ✅ **Documented solution** from MAAS community  
- ✅ Simple configuration change
- ✅ Preserves MAAS as central DNS authority

**Cons:**
- Reduces DNSSEC security for all domains
- May need to survive MAAS updates

### Option 2: Use validate-except for Private Domains (Modern BIND9)
```bash
# Add to BIND configuration (requires BIND 9.13+)
options {
    dnssec-validation auto;
    validate-except { "homelab"; };
};
```

**Pros:**
- Maintains DNSSEC for public domains
- Only disables validation for private domains
- Clean solution for modern BIND versions

**Cons:**
- Requires BIND 9.13+ (check your version)
- More complex configuration

### Option 3: Add Explicit Forward Zone + Disable Validation
```bash
# Best of both worlds approach
zone "homelab" {
    type forward;
    forward only;
    forwarders { 192.168.4.1; };
};

# In options section:
dnssec-validation no;
```

**Pros:**
- Explicit control over .homelab forwarding
- Guaranteed to work regardless of DNSSEC issues
- Standard BIND practice for private domains

**Cons:**
- Requires MAAS configuration modification
- May need to survive MAAS updates

### Option 4: Keep Current Workaround (Temporary)
**Current workaround already implemented:** Use OPNsense (192.168.4.1) as primary DNS and MAAS (192.168.4.53) as secondary.

**Pros:**
- ✅ Already working in current implementation
- No MAAS configuration changes needed
- Maintains all functionality
- ⚠️ **Not a hack** - legitimate workaround for MAAS DNSSEC bug

**Cons:**
- MAAS not serving as central DNS authority as designed
- Doesn't fix the underlying MAAS issue

## 📊 Current Status

### ✅ **MAAS DNS FORWARDING FIXED** (July 30, 2025)
**Solution Applied:** Disabled DNSSEC validation through MAAS web GUI
- **Before:** `ollama.app.homelab @192.168.4.53` → NXDOMAIN ❌
- **After:** `ollama.app.homelab @192.168.4.53` → `192.168.4.80` ✅

### ✅ All DNS Functionality Verified
```bash
# MAAS DNS (192.168.4.53) now works for all domains:
still-fawn.maas → 192.168.4.17        # ✅ MAAS domains (authoritative)
ollama.app.homelab → 192.168.4.80     # ✅ .homelab forwarded to OPNsense
google.com → 142.250.189.206          # ✅ External domains (recursive)
```

### ✅ Working Configuration (All Options Available)
```bash
# Option 1: Use MAAS as primary (now works correctly)
nameserver 192.168.4.53         # MAAS (now forwards .homelab correctly)
nameserver 192.168.4.1          # OPNsense (backup)
nameserver [IPv6]                # ISP DNS (fallback)

# Option 2: Continue using OPNsense primary (still works)
nameserver 192.168.4.1          # OPNsense (primary)
nameserver [IPv6]                # ISP DNS (backup)  
nameserver 192.168.4.53         # MAAS (fallback)
search maas. homelab.
```

## 🎯 **Implementation Summary**

### ✅ **Root Cause Resolution** (Completed July 30, 2025)
1. **Identified:** DNSSEC validation in MAAS BIND9 blocking unsigned private domain forwarding
2. **Fixed:** Disabled DNSSEC validation through MAAS web GUI (Settings → DNS)
3. **Verified:** `.homelab` domains now forward correctly from MAAS to OPNsense
4. **Tested:** All existing functionality (`.maas` domains, external domains) still works

### 🔄 **Next Steps** (Optional)
1. **Monitor** MAAS updates to ensure DNSSEC setting persists
2. **Update container DNS** configurations to use MAAS as primary if desired
3. **Document** the MAAS DNSSEC setting as part of homelab setup procedures

## 📝 **Technical Details**

### MAAS Environment
- **VM:** UbuntuMAAS (VM ID 102) on pve host
- **IP:** 192.168.4.53
- **BIND Version:** 9.18.30 (snap package)
- **Config Path:** `/var/snap/maas/current/bind/`
- **Service:** Managed by MAAS snap

### Network Architecture
```
Clients → MAAS DNS (192.168.4.53) → Should forward to → OPNsense (192.168.4.1)
                                  → Actually goes to → Root DNS servers ❌
```

### Configuration Files Analyzed
- `/var/snap/maas/current/bind/named.conf` (main config)
- `/var/snap/maas/current/bind/named.conf.options.inside.maas` (forwarders)
- `/var/snap/maas/current/bind/named.conf.maas` (zones and ACLs)

## 🏆 **Success Criteria**

- [x] MAAS DNS forwards `.homelab` queries to OPNsense ✅
- [x] `nslookup ollama.app.homelab 192.168.4.53` returns `192.168.4.80` ✅
- [x] All existing `.maas` functionality preserved ✅
- [ ] Configuration survives MAAS updates (requires monitoring)

**Investigation Status:** ✅ **COMPLETE** - Root cause identified and **RESOLVED**