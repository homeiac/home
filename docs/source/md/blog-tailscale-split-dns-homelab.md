# Why Can't I Access My Homelab From the Office?

*A 10-minute debugging session that saved hours of future frustration*

---

It started with a simple goal: check my Grafana dashboards from work.

```
$ nslookup grafana.app.homelab
** server can't find grafana.app.homelab: NXDOMAIN
```

I'm on Tailscale. I have an exit node. Everything *should* just work. Right?

## The Setup

My homelab runs Kubernetes (K3s) with Traefik as the ingress controller. All my services - Grafana, Ollama, Stable Diffusion - are accessible via `.app.homelab` domains:

```
grafana.app.homelab      → 192.168.4.80 (Traefik)
ollama.app.homelab       → 192.168.4.80 (Traefik)
stable-diffusion.app.homelab → 192.168.4.80 (Traefik)
```

At home, my router (OPNsense at `192.168.4.1`) handles DNS and knows about these domains. Works perfectly.

At the office, I connect through Tailscale with my homelab router as an exit node. All traffic flows through home. Should be seamless.

Except it wasn't.

## The Investigation

First, I asked Claude to help debug. It immediately started SSHing into my Proxmox hosts to check the infrastructure:

```
$ ssh root@still-fawn.maas "qm list"
VMID NAME                 STATUS
108  k3s-vm-still-fawn    stopped    ← Wait, what?
```

My entire Kubernetes cluster was down. Someone (or something) had shut down the K3s VM 21 hours ago. Mystery for another day.

After starting the VM:

```
$ ssh root@still-fawn.maas "qm start 108"
K3s VM starting...
```

I verified Traefik was running and the ingress was configured:

```
$ kubectl get ingress -A
NAMESPACE    NAME              HOSTS                  ADDRESS
monitoring   grafana-ingress   grafana.app.homelab    192.168.4.80
```

Everything looked correct. But DNS still wasn't resolving.

## The Aha Moment

Here's what I missed: **Tailscale's DNS (`100.100.100.100`) doesn't know about my `.homelab` domains.**

When you use Tailscale, it acts as your DNS resolver. It knows about Tailscale hostnames (`*.ts.net`) but has no idea that `grafana.app.homelab` should resolve to `192.168.4.80`.

Even though I'm routing all traffic through my home exit node, DNS queries were being handled by Tailscale's resolver - which correctly said "I don't know what `.homelab` is."

## The Fix: Split DNS

Tailscale has a feature called **Split DNS** that routes specific domain queries to specific nameservers.

In the Tailscale admin console (DNS settings):

1. Add a nameserver: `192.168.4.1` (my home router)
2. Enable "Restrict to domain"
3. Set domain: `homelab`
4. **Critical**: Enable "Use with exit node"

That last toggle is the one that got me. When you're using an exit node, Tailscale normally bypasses split DNS rules. You have to explicitly tell it "no really, use this DNS server for this domain even when I'm on the exit node."

## The Result

```
$ nslookup grafana.app.homelab
Server:    100.100.100.100
Address:   100.100.100.100#53

Name:      grafana.app.homelab
Address:   192.168.4.80
```

Now I can access all my homelab services from anywhere - coffee shop, office, airport - as if I'm sitting at home.

## The Lesson

When debugging network issues, check the entire chain:

1. **Is the service running?** (My K3s VM was stopped)
2. **Is the ingress configured?** (Traefik was fine)
3. **Is DNS resolving?** (This was the actual problem)
4. **Is DNS routing correctly?** (Split DNS + exit node interaction)

The fix took 30 seconds once I understood the problem. Finding the problem took the debugging session.

## Quick Reference

**Tailscale Split DNS for Homelab:**

| Setting | Value |
|---------|-------|
| Nameserver | Your home router IP (e.g., `192.168.4.1`) |
| Restrict to domain | ON |
| Domain | `homelab` (or your TLD) |
| Use with exit node | ON (if you use an exit node) |

**Verify it works:**
```bash
# Should resolve via Tailscale DNS
nslookup your-service.app.homelab

# If curl fails but nslookup works, flush DNS cache (macOS)
sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder
```

---

*Debugging homelab issues at 2pm is much better than debugging them at 2am. Tailscale + Split DNS means I can do it from anywhere.*
