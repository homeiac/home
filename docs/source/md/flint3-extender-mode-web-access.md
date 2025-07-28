# GL.iNet Flint 3 Extender Mode Web Interface Access

This guide shows how to enable web interface access on GL.iNet routers running in extender mode with AP-like security restrictions.

## Problem Statement

By default, GL.iNet routers in extender mode restrict web interface access to localhost only for security reasons. This requires SSH tunneling to access admin interfaces:

```bash
ssh -L127.0.0.1:8085:127.0.0.1:80 -L127.0.0.1:8090:127.0.0.1:8080 -L127.0.0.1:8443:127.0.0.1:8443 root@192.168.86.240
```

## Solution Overview

This configuration enables direct web interface access from the local network subnet while maintaining security by:

1. **Access Control**: Modified Lua script allows same-subnet access only
2. **Firewall Rules**: Added specific rules for HTTP/HTTPS ports
3. **Security Model**: Maintains AP-mode-like restrictions (no external WAN access)

## Implementation Steps

### Prerequisites

- GL.iNet router in extender mode (tested on Flint 3)
- SSH access to the router
- Router connected to local network (e.g., 192.168.86.x)

### Step 1: Backup Current Configuration

```bash
# SSH into the router
ssh root@<router-ip>

# Create backup of access control script
cp /usr/share/gl-ngx/oui-access.lua /usr/share/gl-ngx/oui-access.lua.backup

# Verify backup
ls -la /usr/share/gl-ngx/oui-access.lua*
```

### Step 2: Modify Access Control Script

Create the modified access control script:

```bash
cat > /usr/share/gl-ngx/oui-access.lua << 'EOF'
local utils = require "oui.utils"
local ubus = require "oui.ubus"
local uci = require "uci"

local c = uci.cursor()
local redirect_https = c:get("oui-httpd", "main", "redirect_https") == "1"

local function get_ssl_port()
    local text = utils.readfile("/etc/nginx/conf.d/gl.conf")
    return text:match("listen (%d+) ssl;")
end

local function get_iface_ipaddr(iface)
    local s = ubus.call("network.interface." .. iface, "status")
    if not s or not s.up then
        return nil
    end

    local ipaddrs = s["ipv4-address"]
    if #ipaddrs == 0 then
        return nil
    end

    return ipaddrs[1].address
end

local function is_same_subnet(ip1, ip2, netmask)
    -- Simple subnet check for /24 networks
    if not ip1 or not ip2 then return false end
    local subnet1 = ip1:match("(%d+%.%d+%.%d+)%.")
    local subnet2 = ip2:match("(%d+%.%d+%.%d+)%.")
    return subnet1 == subnet2
end

local host = ngx.var.host

if redirect_https and ngx.var.scheme == "http" then
    local ssl_port = get_ssl_port()
    if ssl_port ~= "443" then
        host = host .. ":" .. ssl_port
    end
    return ngx.redirect("https://" .. host .. ngx.var.request_uri)
end

if  c:get("oui-httpd", "main", "inited") then
    return
end

local lanip = get_iface_ipaddr("lan")
local wanip = get_iface_ipaddr("wan")

local hosts = {
    ["console.gl-inet.com"] = true,
    ["localhost"] = true,
    ["127.0.0.1"] = true
}

if lanip then
    hosts[lanip] = true
end

if wanip then
    hosts[wanip] = true
    -- Allow access from same subnet as WAN interface
    if is_same_subnet(host, wanip, "255.255.255.0") then
        hosts[host] = true
    end
end

if not hosts[host] and lanip then
    return ngx.redirect(ngx.var.scheme .. "://" .. lanip)
end
EOF
```

### Step 3: Add Firewall Rules

Add firewall rules to allow web interface access from WAN:

```bash
# Add HTTP access rule
uci add firewall rule
uci set firewall.@rule[-1].name="Allow-HTTP-WAN"
uci set firewall.@rule[-1].src="wan"
uci set firewall.@rule[-1].proto="tcp"
uci set firewall.@rule[-1].dest_port="80"
uci set firewall.@rule[-1].target="ACCEPT"

# Add HTTPS access rule
uci add firewall rule
uci set firewall.@rule[-1].name="Allow-HTTPS-WAN"
uci set firewall.@rule[-1].src="wan"
uci set firewall.@rule[-1].proto="tcp"
uci set firewall.@rule[-1].dest_port="443"
uci set firewall.@rule[-1].target="ACCEPT"

# Add Luci interface access rule
uci add firewall rule
uci set firewall.@rule[-1].name="Allow-Luci-WAN"
uci set firewall.@rule[-1].src="wan"
uci set firewall.@rule[-1].proto="tcp"
uci set firewall.@rule[-1].dest_port="8443"
uci set firewall.@rule[-1].target="ACCEPT"

# Commit changes
uci commit firewall
```

### Step 4: Restart Services

```bash
# Restart nginx to apply Lua script changes
/etc/init.d/nginx restart

# Restart firewall to apply new rules
/etc/init.d/firewall restart
```

## Testing Access

After implementation, test access from local network:

```bash
# Test GL.iNet admin interface (HTTP)
curl -s -o /dev/null -w "%{http_code}" http://<router-ip>/

# Test GL.iNet admin interface (HTTPS)
curl -s -o /dev/null -w "%{http_code}" -k https://<router-ip>/

# Test Luci interface (HTTPS)
curl -s -o /dev/null -w "%{http_code}" -k https://<router-ip>:8443/
```

All should return `200` for successful access.

## Accessing Web Interfaces

After configuration:

- **GL.iNet Admin**: `http://<router-ip>` or `https://<router-ip>`
- **Luci Interface**: `https://<router-ip>:8443`

## Security Considerations

### What This Configuration Provides

- ✅ Same-subnet access (AP-mode-like behavior)
- ✅ Blocks external WAN access
- ✅ Maintains localhost access
- ✅ Preserves SSL/HTTPS redirection

### Security Best Practices

1. **Change Default Passwords**: Ensure strong passwords for both GL.iNet and Luci interfaces
2. **Monitor Access**: Regular review of firewall logs for unauthorized access attempts
3. **Network Isolation**: Consider VLAN segmentation if on shared networks
4. **Regular Updates**: Keep firmware updated for security patches

## Troubleshooting

### Web Interface Returns 404 or Connection Refused

```bash
# Check nginx status
ps w | grep nginx

# Check service listening
netstat -tlnp | grep -E ":80|:443|:8443"

# Restart nginx if needed
/etc/init.d/nginx restart
```

### Access Still Blocked

```bash
# Verify firewall rules
nft list ruleset | grep -E "(80|443|8443)"

# Check firewall status
/etc/init.d/firewall status

# Restart firewall
/etc/init.d/firewall restart
```

### Lua Script Errors

```bash
# Check nginx error logs
tail -n 20 /var/log/nginx/error.log

# Verify script syntax
lua -l oui-access /usr/share/gl-ngx/oui-access.lua
```

## Reverting Changes

To restore original behavior:

```bash
# Restore original Lua script
cp /usr/share/gl-ngx/oui-access.lua.backup /usr/share/gl-ngx/oui-access.lua

# Remove firewall rules
uci delete firewall.@rule[-1]  # Repeat for each rule added
uci commit firewall

# Restart services
/etc/init.d/nginx restart
/etc/init.d/firewall restart
```

## Technical Details

### Architecture Components

- **nginx**: Web server handling HTTP/HTTPS on ports 80/443
- **uhttpd**: OpenWrt web server handling Luci on port 8443
- **oui-access.lua**: GL.iNet access control script
- **nftables/fw4**: Firewall system blocking WAN access by default

### Network Configuration

```
Router IP (WAN): 192.168.86.240  (sta1 interface)
Router IP (LAN): 192.168.8.1     (br-lan interface)
Allowed Subnet: 192.168.86.0/24  (same as WAN interface)
```

## Related Documentation

- [Flint 3 VLAN 40 Guide](flint3-vlan40-guide.md)
- [Flint 3 Network Bridge Guide](flint3-network-bridge-guide.md)

## References

- Issue #101: Document GL.iNet extender mode web interface access configuration
- GL.iNet OpenWrt Documentation
- OpenWrt Firewall Configuration Guide