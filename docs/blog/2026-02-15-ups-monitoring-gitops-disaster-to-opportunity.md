# Turning a Power Outage Scare into GitOps Gold

**Date:** 2026-02-15
**Tags:** ups, nut, gitops, prometheus, grafana, homelab, power, monitoring, disaster-recovery

## The Wake-Up Call

Nothing motivates infrastructure improvements like a close call. When my homelab experienced an unexpected power event, I realized I had a CyberPower CP1500 UPS sitting there... completely unmonitored. No alerts. No graceful shutdown. Just hoping for the best.

Time to fix that. And since this is a GitOps-managed homelab, we're going to do it properly - everything in git, deployable from scratch.

## The Goal

1. **NUT (Network UPS Tools)** on pve (the Proxmox host with USB connection to UPS)
2. **Tiered graceful shutdown** - not all hosts are equal:
   - 40% battery: Shutdown GPU/K3s worker hosts (pumped-piglet, still-fawn)
   - 20% battery: Shutdown MAAS VM (DHCP/DNS)
   - 10% battery: Shutdown everything else, then pve itself
3. **Prometheus metrics** via nut_exporter
4. **Grafana dashboard** for visualization
5. **Alerts** via Alertmanager (email) and ntfy.sh (backup)
6. **Fully GitOps** - deploy everything via K8s CronJob that SSHs to pve

## The Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  K3s Cluster                                                    │
│  ┌──────────────────┐    ┌─────────────────┐                   │
│  │ CronJob:         │    │ ServiceMonitor  │                   │
│  │ nut-deploy       │    │ nut-exporter    │                   │
│  │ (hourly sync)    │    │                 │                   │
│  └────────┬─────────┘    └────────┬────────┘                   │
│           │                       │                             │
└───────────┼───────────────────────┼─────────────────────────────┘
            │ SSH                   │ scrape :9199
            ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  pve (192.168.4.122)                                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ nut-server  │  │ nut-monitor │  │ nut_exporter :9199      │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│         ▲                                                       │
│         │ USB                                                   │
│  ┌──────┴──────┐                                               │
│  │ CyberPower  │                                               │
│  │ CP1500      │                                               │
│  └─────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
```

## The Journey (Including All the Mistakes)

### Mistake 1: Manual SCP Instead of GitOps

My first instinct was to `scp` scripts directly to pve. Old habits die hard.

```bash
# What I started doing (wrong)
scp scripts/pve/setup-nut.sh root@pve.maas:/tmp/
```

Then I caught myself - the whole point is GitOps! If pve needs to be rebuilt, I want everything to redeploy automatically. So I created a K8s CronJob that SSHs to pve and deploys configs from ConfigMaps.

### Mistake 2: Using Hostnames from Inside K8s

The deploy script used `pve.maas` as the target host. Works great from my Mac. Fails completely from inside a K8s pod.

```
[2026-02-15 20:32:03] ERROR: Cannot SSH to pve.maas
```

MAAS DNS isn't available inside the cluster. Fixed by using the IP address directly:

```bash
PVE_HOST="192.168.4.122"  # Not pve.maas
```

### Mistake 3: Wrong nut_exporter Download URL

I used an old URL format for nut_exporter:

```bash
# Wrong - returns HTML, not a tarball
curl -sLO https://github.com/DRuggeri/nut_exporter/releases/download/2.5.2/nut_exporter-2.5.2.linux-amd64.tar.gz

# Right - direct binary download for v3.x
curl -sL -o /usr/local/bin/nut_exporter https://github.com/DRuggeri/nut_exporter/releases/download/v3.2.2/nut_exporter-v3.2.2-linux-amd64
```

The error was subtle - `tar: stdin: not in gzip format`. Always verify your download URLs.

### Mistake 4: Wrong Prometheus Metrics Path

The ServiceMonitor was scraping `/metrics` but nut_exporter v3 serves UPS data at `/ups_metrics`:

```yaml
# Wrong
path: /metrics

# Right
path: /ups_metrics
```

### Mistake 5: Wrong Metric Names in Alerts

I copied alert expressions from examples that used the HON95 exporter (`nut_*` metrics), but DRuggeri's exporter uses `network_ups_tools_*`:

```yaml
# Wrong
expr: nut_battery_charge < 30

# Right
expr: network_ups_tools_battery_charge < 30
```

### Mistake 6: Using a Dashboard That Didn't Match Our Exporter

Grabbed dashboard ID 15406 from Grafana.com. It uses `nut_*` metrics. Our exporter outputs `network_ups_tools_*`. Dashboard showed nothing.

Had to create a custom dashboard with the correct metric names.

### Mistake 7: YAML Parsing Errors in ConfigMap

This one was fun. My notification script had a multiline string:

```bash
local full_body="$body

UPS Status:
  Battery: ${charge}%
  Tier 1 (40%): $(tier_done 1 && echo "DONE" || echo "pending")
"
```

Kustomize failed with: `yaml: line 63: could not find expected ':'`

The colons in `Tier 1 (40%):` were being interpreted as YAML key-value pairs, even inside a literal block scalar. Fixed by simplifying to a single line:

```bash
local full_body="${body} | Battery=${charge}% | Tiers: T1=${t1} T2=${t2} T3=${t3}"
```

### Mistake 8: Changing Dashboard UID Created Orphan

When I replaced the broken Grafana.com dashboard with my custom one, I changed the UID from `80-PUnWMk` to `nut-ups-pve`.

Grafana's sidecar doesn't delete dashboards - it only adds/updates. So now I had TWO dashboards: the old broken one (orphaned but still "provisioned") and the new working one.

Couldn't delete via API: `"provisioned dashboard cannot be deleted"`

Had to delete the Grafana pod to clear its database cache and let it reprovision fresh.

**Lesson learned:** When updating a dashboard, keep the same UID to ensure it's an update, not a new dashboard.

## The Final Result

After all the iterations, here's what we have:

### GitOps Structure

```
gitops/clusters/homelab/infrastructure/nut-pve/
├── kustomization.yaml
├── configmap-nut-configs.yaml      # /etc/nut/* files
├── configmap-nut-scripts.yaml      # nut-notify.sh, test-nut-status.sh
├── configmap-deploy-script.yaml    # SSH deploy script
├── cronjob-nut-deploy.yaml         # Hourly sync
├── secrets/
│   └── pve-ssh-key.sops.yaml       # SOPS-encrypted SSH key
├── service-nut-exporter.yaml       # External Service → pve:9199
└── servicemonitor-nut-exporter.yaml # Prometheus scrape + alerts
```

### Prometheus Alerts

| Alert | Condition | Severity |
|-------|-----------|----------|
| UPSOnBattery | status=OB | warning |
| UPSLowBattery | charge < 30% | critical |
| UPSBatteryCritical | charge < 15% | critical |
| UPSOffline | exporter unreachable | warning |
| UPSHighLoad | load > 80% | warning |
| UPSReplaceBattery | status=RB | warning |

### Dual Notification Path

1. **Prometheus → Alertmanager → Email** (when K8s is healthy)
2. **nut-notify.sh → ntfy.sh** (direct from pve, even when K8s is down)

### Grafana Dashboard

Custom dashboard with gauges for battery/load, status indicators, and time series for voltage and charge history.

## What I Learned

1. **GitOps for bare-metal config is possible** - Use a K8s Job/CronJob to SSH and deploy. Store configs in ConfigMaps.

2. **SOPS for secrets works great** - SSH key encrypted in git, decrypted by Flux at deploy time.

3. **Always verify your assumptions:**
   - Can K8s pods resolve your hostnames? (No)
   - Does your download URL return what you expect? (Check it)
   - Do your metric names match your queries? (Verify)

4. **Grafana dashboard UIDs matter** - Changing UID = new dashboard, not update.

5. **The sidecar doesn't clean up** - Orphaned dashboards need manual deletion.

6. **Test the failure path** - Notifications need to work when everything else is down. That's why we have ntfy.sh as a backup that runs directly from pve.

## Recovery Scenario

If pve needs to be rebuilt from scratch:

1. Install Proxmox
2. Ensure SSH key is authorized for root
3. Flux automatically deploys NUT CronJob
4. CronJob runs (hourly or trigger manually):
   ```bash
   kubectl create job --from=cronjob/nut-deploy nut-deploy-now -n monitoring
   ```
5. NUT, nut_exporter, and all configs are deployed
6. Prometheus starts scraping, alerts are active

Total manual intervention: Just authorize the SSH key. Everything else is GitOps.

## Commits

The journey in git:

```
995a928 fix: simplify notification message to avoid YAML parsing issues
fdd28eb fix: custom NUT dashboard with correct metrics + ntfy.sh notifications
d8e07ec feat: add NUT UPS Grafana dashboard (ID 15406)
13967b2 fix: update ServiceMonitor path and metric names for nut_exporter v3
0a07dc4 fix: correct nut_exporter download URL (v3.2.2 direct binary)
e23e7ee fix: use IP address for pve in NUT deploy script
891fb29 feat: add NUT UPS monitoring with GitOps deployment for pve
```

Seven commits to get it right. Each fix taught me something.

## Current Status

- **UPS:** CyberPower CP1500AVRLCDa
- **Battery:** 100%
- **Load:** ~23%
- **Prometheus:** Scraping every 30s
- **Alerts:** Configured and ready
- **Dashboard:** Working with live data

The next power outage will be graceful. And if I ever need to rebuild pve, I just need to authorize an SSH key and let GitOps do the rest.

---

*Sometimes the best infrastructure improvements come from near-disasters. The key is to use that motivation to build something better, not just patch the immediate problem.*
