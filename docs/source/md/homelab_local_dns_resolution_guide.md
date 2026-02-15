# Homelab Local DNS Resolution Guide

This guide covers the full end-to-end setup and gotchas for local DNS resolution of `*.app.homelab` and `*.maas` in your homelab environment. It also explains how to configure macOS clients to prioritize OPNsense as the primary DNS server.

---

## 1. OPNsense Unbound Overrides & Forwarding

1. **Host Override for OPNsense**
   - **Services → Unbound DNS → Overrides → Host Overrides**
     - **Host:** `opnsense`
     - **Domain:** `homelab`
     - **IP:** `192.168.4.1`
2. **Query Forwarding for `.maas`**
   - **Services → Unbound DNS → Query Forwarding**
     - **Domain:** `maas`
     - **Server:** `192.168.4.53` (MAAS DNS)
     - **Forward first:** ✓
3. **Wildcard Host Override for Apps**
   - **Services → Unbound DNS → Overrides → Host Overrides**
     - **Host:** `*`
     - **Domain:** `app.homelab`
     - **IP:** `192.168.4.80` (Traefik LoadBalancer - routes to backend services)
4. **Reboot Required**
   - A **full OPNsense reboot** reliably applies these overrides.
   - `service unbound onerestart` or the GUI *Apply* button did **not** always reload the wildcard override.

---

## 2. MAAS DNS Settings

- MAAS's DNS UI only supports its built‑in `*.maas` domain and **does not** allow wildcards under that zone.
- In **Settings → DNS**:
  - **Upstream DNS:** `192.168.4.1` (OPNsense)
  - **Enable DNS forwarding** and **recursion**

---

## 3. MAAS DHCP Snippets (Optional)

- In **Network services → DHCP → Manage DHCP snippets**, you can add:

```dhcp
option domain-name-servers 192.168.4.53, 192.168.4.1;
```

- **Gotcha:** the MAAS rack controller may not serve the extra DNS server until it is fully rebooted.

---

## 4. macOS Client Setup

### Recommended: Scoped Resolver (Survives DHCP)

When your Mac is on multiple networks (e.g., Wi-Fi on `192.168.1.x` and USB LAN on `192.168.4.x`), macOS uses DNS from the default route interface. If Wi-Fi is your default route, `*.app.homelab` won't resolve because your ISP's DNS doesn't know about it.

**Solution**: Create a scoped resolver that routes `*.homelab` to OPNsense:

```bash
# Run the setup script
sudo ./scripts/dns/setup-macos-resolver.sh

# Or manually:
sudo sh -c 'echo "nameserver 192.168.4.1" > /etc/resolver/homelab'
```

**Verify**:
```bash
# Check macOS sees the resolver
scutil --dns | grep -A3 "homelab"

# Test resolution
dig frigate.app.homelab +short
# Should return: 192.168.4.80
```

**Why this is better than `networksetup`**:
- Survives DHCP lease renewals
- Only affects `*.homelab` domains, not all DNS
- Works regardless of which interface has the default route
- No need to reconfigure when switching networks

### Alternative: Manual DNS (Gets Overwritten by DHCP)

If you prefer setting DNS on a specific interface (note: DHCP will overwrite this):

```bash
SERVICE="USB 10/100/1000 LAN"   # or "Wi-Fi"
sudo networksetup -setdnsservers "$SERVICE" 192.168.4.1 192.168.4.53
sudo killall -HUP mDNSResponder
```

Verify:
```bash
networksetup -getdnsservers "$SERVICE"
```

### Cleanup Stale Resolvers

Remove any old/incorrect resolver files:
```bash
ls -la /etc/resolver/
# Remove files pointing to wrong IPs
sudo rm /etc/resolver/homelab.local  # example
```

---

## 5. Verification Commands

### On OPNsense (after reboot)

```bash
host opnsense.homelab 127.0.0.1      # → 192.168.4.1
host test.app.homelab 127.0.0.1     # → 192.168.4.80
host somehost.maas 127.0.0.1        # → MAAS record IP
```

### On MAAS server

```bash
dig opnsense.homelab @192.168.4.53 +short   # → 192.168.4.1
dig test.app.homelab @192.168.4.53 +short    # → 192.168.4.80
```

### On macOS

```bash
dig opnsense.homelab +short
dig test.app.homelab +short
dig somehost.maas +short
```

---

## 6. Troubleshooting Common Issues

### Issue: `*.app.homelab` domains all route to the same service

**Symptoms:**
- `ollama.app.homelab` and `stable-diffusion.app.homelab` both return the same response
- One service works but the other doesn't

**Root Cause:**
The wildcard DNS override `*.app.homelab` is pointing to a specific service's LoadBalancer IP instead of Traefik's LoadBalancer IP.

**Diagnosis:**
```bash
# Check what IP the domains resolve to
nslookup ollama.app.homelab
nslookup stable-diffusion.app.homelab

# Both should return 192.168.4.80 (Traefik), not individual service IPs
```

**Fix:**
1. **Navigate to**: Services → Unbound DNS → Overrides → Host Overrides
2. **Find**: `*.app.homelab` entry  
3. **Change IP to**: `192.168.4.80` (Traefik LoadBalancer)
4. **Reboot OPNsense** to apply changes

**Verification:**
```bash
# Test Host header routing works
curl -H "Host: ollama.app.homelab" -I http://192.168.4.80
curl -H "Host: stable-diffusion.app.homelab" -I http://192.168.4.80

# Should return different responses indicating proper routing
```

---

## 7. Service IP Reference

- **Traefik LoadBalancer**: `192.168.4.80` (routes based on Host header)
- **Ollama LoadBalancer**: `192.168.4.81` (direct access)
- **Stable Diffusion LoadBalancer**: `192.168.4.82` (direct access)

**Important**: All `*.app.homelab` DNS entries should point to Traefik (`192.168.4.80`), not individual service IPs.

---

## 8. Detailed RCA: Traefik Host-Based Routing Failure

### Incident Summary (2025-07-30)
**Issue**: `ollama.app.homelab` was redirecting to `stable-diffusion.app.homelab` application despite correct ingress configurations.

**Root Cause**: OPNsense DNS cache contained stale entries where `ollama.app.homelab` resolved to `192.168.4.82` (Stable Diffusion's LoadBalancer IP) instead of `192.168.4.80` (Traefik's LoadBalancer IP), causing requests to bypass Traefik entirely.

### Investigation Methodology

#### Phase 1: DNS Resolution Analysis
The key insight came from using **verbose curl** to identify where requests were actually going:

```bash
# This revealed the smoking gun - wrong IP resolution
$ curl -v http://ollama.app.homelab 2>&1 | head -10
* Host ollama.app.homelab:80 was resolved.
* IPv4: 192.168.4.82          # ← WRONG! Should be 192.168.4.80
*   Trying 192.168.4.82:80...
* Connected to ollama.app.homelab (192.168.4.82) port 80
```

#### Phase 2: DNS Tool Comparison
Different DNS resolution tools returned different results, indicating cache inconsistency:

```bash
$ nslookup ollama.app.homelab    # → 192.168.4.80 ✅ (correct)
$ dig ollama.app.homelab +short  # → 192.168.4.80 ✅ (correct)  
$ host ollama.app.homelab        # → 192.168.4.80 ✅ (correct)
$ ping -c 1 ollama.app.homelab   # → 192.168.4.82 ❌ (cached/wrong)
$ curl ollama.app.homelab        # → 192.168.4.82 ❌ (cached/wrong)
```

#### Phase 3: Traefik Routing Verification
Direct Host header testing proved Traefik routing was working correctly:

```bash
# Direct Traefik access with Host headers worked perfectly
$ curl -H "Host: ollama.app.homelab" -I http://192.168.4.80
HTTP/1.1 200 OK
Content-Length: 17              # ← Ollama response

$ curl -H "Host: stable-diffusion.app.homelab" -I http://192.168.4.80  
HTTP/1.1 200 OK
Content-Length: 3076662         # ← Stable Diffusion response
```

#### Phase 4: Multi-Host DNS Testing
Testing from different hosts revealed DNS propagation issues:

```bash
# Mac client (where issue was reported)
$ nslookup ollama.app.homelab → 192.168.4.80 ✅
$ curl ollama.app.homelab → connects to 192.168.4.82 ❌

# PVE host test
$ ssh root@still-fawn.maas "ping ollama.app.homelab"
ping: ollama.app.homelab: Name or service not known ❌
```

### Key Diagnostic Commands That Identified Root Cause

1. **Verbose curl for actual connection tracking**:
   ```bash
   curl -v http://ollama.app.homelab 2>&1 | grep -E "(Trying|Connected|Host:)"
   ```

2. **Direct Traefik Host header testing**:
   ```bash
   curl -H "Host: ollama.app.homelab" -I http://192.168.4.80
   curl -H "Host: stable-diffusion.app.homelab" -I http://192.168.4.80
   ```

3. **Cross-platform DNS resolution comparison**:
   ```bash
   nslookup ollama.app.homelab
   dig ollama.app.homelab +short
   ping -c 1 ollama.app.homelab
   ```

4. **Service IP correlation**:
   ```bash
   kubectl get svc -A | grep "192.168.4.82"  # Found stable-diffusion-webui
   ```

### Resolution
**OPNsense reboot** cleared the DNS cache, allowing the wildcard `*.app.homelab → 192.168.4.80` override to function correctly.

---

## 9. Troubleshooting Runbook: *.app.homelab Routing Issues

### When to Use This Runbook
- `*.app.homelab` domains routing to wrong service
- Domains resolving to individual service IPs instead of Traefik
- Inconsistent DNS resolution across different tools

### Step 1: Verify Current Resolution Pattern
```bash
# Check what IP domains are resolving to
echo "=== DNS Resolution Check ==="
nslookup ollama.app.homelab
nslookup stable-diffusion.app.homelab

# Check actual connection behavior  
echo "=== Connection Behavior Check ==="
curl -v http://ollama.app.homelab --connect-timeout 5 2>&1 | grep -E "(Trying|Connected)"
curl -v http://stable-diffusion.app.homelab --connect-timeout 5 2>&1 | grep -E "(Trying|Connected)"
```

**Expected**: Both should connect to `192.168.4.80` (Traefik)  
**Problem**: If connecting to `192.168.4.81`, `192.168.4.82`, or other IPs

### Step 2: Test Traefik Host-Based Routing
```bash
echo "=== Traefik Routing Verification ==="
curl -H "Host: ollama.app.homelab" -I http://192.168.4.80
curl -H "Host: stable-diffusion.app.homelab" -I http://192.168.4.80

# Check service responses are different
echo "Expected: Different Content-Length values indicating proper routing"
```

**Expected**: Different responses (Content-Length: 17 vs 3076662)  
**Problem**: If both return same response, check ingress configurations

### Step 3: Verify Kubernetes Service Configuration
```bash
echo "=== Kubernetes Service Check ==="
export KUBECONFIG=~/kubeconfig

# Check service IPs
kubectl get svc -A | grep -E "(traefik|ollama|stable-diffusion)"

# Check ingress status
kubectl get ingress -A | grep -E "(ollama|stable-diffusion)"

# Verify ingress rules
kubectl describe ingress ollama-ingress -n ollama
kubectl describe ingress stable-diffusion-ingress -n stable-diffusion
```

**Expected Service IPs**:
- traefik: `192.168.4.80`
- ollama-lb: `192.168.4.81` 
- stable-diffusion-webui: `192.168.4.82`

### Step 4: Multi-Platform DNS Resolution Test
```bash
echo "=== Cross-Platform DNS Test ==="
# Test from Mac client
nslookup ollama.app.homelab
dig ollama.app.homelab +short
host ollama.app.homelab

# Test from PVE host
ssh root@still-fawn.maas "host ollama.app.homelab 192.168.4.1"
ssh root@still-fawn.maas "curl -H 'Host: ollama.app.homelab' -I http://192.168.4.80"
```

### Step 5: DNS Server Chain Verification
```bash
echo "=== DNS Server Chain Check ==="
# Test OPNsense directly
nslookup ollama.app.homelab 192.168.4.1

# Test MAAS DNS
nslookup ollama.app.homelab 192.168.4.53

# Check current DNS configuration
cat /etc/resolv.conf
scutil --dns | head -20
```

**Expected**: OPNsense should return `192.168.4.80`, MAAS should forward or return NXDOMAIN

### Step 6: Resolution Actions

#### If DNS Resolution is Wrong (Most Common)
```bash
# Clear local DNS cache (macOS)
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder

# If problem persists, reboot OPNsense (most reliable)
# Navigate to OPNsense → System → Reboot
# Wait for full reboot, then test again
```

#### If Traefik Routing is Wrong
```bash
# Check and restart Traefik
kubectl rollout restart deployment traefik -n kube-system
kubectl rollout status deployment traefik -n kube-system

# Verify ingress applications
kubectl apply -f gitops/clusters/homelab/apps/ollama/ingress.yaml
kubectl apply -f gitops/clusters/homelab/apps/stable-diffusion/ingress.yaml
```

#### If Services Have Wrong IPs
```bash
# Check MetalLB IP allocation
kubectl get svc -A | grep LoadBalancer

# If IPs are wrong, restart MetalLB
kubectl rollout restart daemonset speaker -n metallb-system
kubectl rollout restart deployment controller -n metallb-system
```

### Step 7: Verification
```bash
echo "=== Final Verification ==="
# Test both domains
curl -I http://ollama.app.homelab
curl -I http://stable-diffusion.app.homelab

# Expected results:
# ollama.app.homelab: Content-Length: 17, Content-Type: text/plain
# stable-diffusion.app.homelab: Content-Length: 3076662, server: uvicorn
```

### Emergency Workaround
If DNS issues persist, add to `/etc/hosts`:
```bash
sudo tee -a /etc/hosts << EOF
192.168.4.80 ollama.app.homelab
192.168.4.80 stable-diffusion.app.homelab
EOF
```

---

## 10. Final Gotchas & Lessons Learned

- MAAS DNS limitations: no wildcard support for subdomains.
- OPNsense Host Overrides: supports wildcards (`Host=*`, `Domain=app.homelab`).
- Reboot needed: OPNsense only reliably applies new overrides after a reboot.
- MAAS DHCP snippet reboot: DHCP options may require a rack controller reboot to apply.
- **macOS scoped resolvers are the fix**: Use `/etc/resolver/homelab` to route `*.homelab` to OPNsense. This survives DHCP renewals and works on multi-network setups.
- **macOS default route determines DNS**: If Wi-Fi is your default route, `networksetup` DNS settings on USB LAN won't be used. Scoped resolvers bypass this.
- AT&T routers lock DNS settings: Can't customize DHCP-provided DNS, use scoped resolvers instead.

## 11. Related Documentation

- [macOS Homelab DNS Resolver Runbook](../../runbooks/macos-homelab-dns-resolver.md) - Quick setup and troubleshooting
- [Blog: Why Your Homelab DNS Breaks on Wi-Fi](blog-macos-scoped-dns-multi-network.md) - Deep dive explanation

