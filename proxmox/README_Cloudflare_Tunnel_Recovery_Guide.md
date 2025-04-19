# Cloudflare Tunnel Recovery Guide (test-nginx)

This guide documents how to restore the Cloudflare Tunnel named `test-nginx` in case the Proxmox server or the LXC container is lost and needs to be recreated.

---

## 🧩 Overview

This tunnel securely exposes a self-hosted web service (e.g., NGINX on your LAN) to the internet via Cloudflare Tunnel and is protected by Cloudflare Zero Trust Access.

---

## ✅ Prerequisites

- Access to your Cloudflare account
- Your domain and subdomain (e.g., demo.example.com) are active in Cloudflare
- You have SSH or console access to your new Proxmox setup

---

## 🔁 Step-by-Step Recovery Instructions (Tteck Script Method)

### 1. Reinstall the cloudflared LXC container

On the Proxmox host:

```bash
bash -c "$(wget -qLO - https://github.com/tteck/Proxmox/raw/main/ct/cloudflared.sh)"
```

- Accept the defaults or configure as needed
- When prompted about DNS-over-HTTPS, choose “N”

---

### 2. Enter the container

```bash
pct enter <container_id>
```

(Replace with actual container ID)

---

### 3. Authenticate cloudflared with Cloudflare

```bash
cloudflared tunnel login
```

- Open the login URL in a browser
- Select your domain
- cloudflared will now have access to manage tunnels under your domain

---

### 4. Recreate the tunnel (if config was not backed up)

```bash
cloudflared tunnel create test-nginx
```

This generates a new credentials file in:
```
/root/.cloudflared/<tunnel-id>.json
```

If you had previously backed this file up, copy it back now and skip the step above.

---

### 5. Create the config.yml

```bash
vim /root/.cloudflared/config.yml
```

Paste and edit as needed:

```yaml
tunnel: test-nginx
credentials-file: /root/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: demo.example.com
    service: http://192.168.1.123:3000  # Replace with your local service IP and port
  - service: http_status:404
```

---

### 6. Link the tunnel to your DNS

```bash
cloudflared tunnel route dns test-nginx demo.example.com
```

This creates a DNS record in Cloudflare for demo.example.com pointing to the tunnel.

---

### 7. Set up systemd service for auto-start

```bash
vim /etc/systemd/system/cloudflared-tunnel.service
```

Paste:

```ini
[Unit]
Description=Cloudflare Tunnel: test-nginx
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/cloudflared tunnel run test-nginx
Restart=on-failure
User=root
WorkingDirectory=/root/.cloudflared/

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
systemctl daemon-reexec
systemctl daemon-reload
systemctl enable cloudflared-tunnel.service
systemctl start cloudflared-tunnel.service
```

---

### 8. Verify it works

Test in a browser:

```
https://demo.example.com
```

Check service status:

```bash
systemctl status cloudflared-tunnel.service
```

---

## 🔒 Cloudflare Zero Trust Access

Your Cloudflare Access (Zero Trust) policy remains in the dashboard and does not need to be recreated.

To verify or edit:

- Visit: https://one.cloudflare.com
- Go to: Access → Applications
- Confirm `demo.example.com` is still protected

You can adjust session duration or login method as needed.

---

## 🗃️ Recommended Backups

To make recovery easier, keep copies of:

- /root/.cloudflared/<tunnel-id>.json
- /root/.cloudflared/config.yml
- /etc/systemd/system/cloudflared-tunnel.service
- This README.md

---

## 🧪 Optional: Test Your Recovery Plan

1. Power off or delete the container
2. Re-run the steps above to recreate it from scratch
3. Confirm:
   - Tunnel auto-starts on boot
   - Subdomain routes to your local service
   - Zero Trust login still works
