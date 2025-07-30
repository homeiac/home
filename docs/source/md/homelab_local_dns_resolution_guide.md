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

1. **Remove stale scoped resolver (if present)**

   ```bash
   sudo rm /etc/resolver/homelab
   sudo killall -HUP mDNSResponder
   ```
2. **Manually set DNS order so OPNsense is primary**

   ```bash
   SERVICE="USB 10/100/1000 LAN"   # or "Wi-Fi"
   sudo networksetup -setdnsservers "$SERVICE" 192.168.4.1 192.168.4.53
   sudo killall -HUP mDNSResponder
   ```
3. **Verify**

   ```bash
   networksetup -getdnsservers "$SERVICE"
   ```
4. **Flush DNS cache after any change**

   ```bash
   sudo killall -HUP mDNSResponder
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

## 8. Final Gotchas & Lessons Learned

- MAAS DNS limitations: no wildcard support for subdomains.
- OPNsense Host Overrides: supports wildcards (`Host=*`, `Domain=app.homelab`).
- Reboot needed: OPNsense only reliably applies new overrides after a reboot.
- MAAS DHCP snippet reboot: DHCP options may require a rack controller reboot to apply.
- macOS scoped resolvers: remove `/etc/resolver/homelab` to avoid conflicts.
- Client DNS ordering: manually enforce the correct DNS order, as MAAS DHCP won't.

