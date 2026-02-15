# NUT Tiered Shutdown Runbook

## Overview

Network UPS Tools (NUT) on `pve` manages graceful shutdown of all Proxmox hosts during power outages. The CyberPower CP1500 UPS is connected via USB to pve, which orchestrates tiered shutdowns via SSH to other hosts.

**GitOps Managed**: Configuration is deployed via K8s CronJob that SSHs to pve. Changes to configs in `gitops/clusters/homelab/infrastructure/nut-pve/` are automatically synced hourly.

## Architecture

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
│  │ (upsd)      │  │ (upsmon)    │  │ (prometheus metrics)    │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│         ▲                                                       │
│         │ USB                                                   │
│  ┌──────┴──────┐                                               │
│  │ CyberPower  │                                               │
│  │ CP1500      │                                               │
│  └─────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
```

## Tiered Shutdown Strategy

Not all hosts are equal. Heavy GPU/K3s hosts are shut down first to extend battery runtime for critical infrastructure.

| Battery Level | Action | Hosts Affected |
|---------------|--------|----------------|
| ≤40% | Tier 1: Shutdown heavy hosts | pumped-piglet, still-fawn |
| ≤20% | Tier 2: Shutdown MAAS | VM 102 on pve |
| ≤10% | Tier 3: Shutdown critical infra | chief-horse, then pve |

### Rationale

- **Tier 1 (40%)**: GPU workloads (RTX 3070, AMD GPU) and K3s workers consume significant power. Shedding them early extends runtime for DHCP/DNS (MAAS) and Home Assistant.
- **Tier 2 (20%)**: MAAS provides DHCP/DNS. By 20%, we're in serious territory.
- **Tier 3 (10%)**: Last resort. Shutdown HAOS and pve itself before battery depletion.

## Host Reference

| Host | IP | Role | VMs/LXCs | Tier |
|------|-----|------|----------|------|
| pumped-piglet | 192.168.4.175 | K3s worker | VM 105 (RTX 3070), PBS LXC 103 | 1 |
| still-fawn | 192.168.4.17 | K3s worker | VM 108 (AMD GPU + Coral) | 1 |
| pve | 192.168.4.122 | NUT server | MAAS VM 102 | 3 |
| chief-horse | 192.168.4.19 | HAOS host | HAOS VM 116 | 3 |

**Not on this UPS**: fun-bedbug (192.168.4.172), rapid-civet (192.168.4.11)

## Files

### GitOps (Source of Truth)

| File | Purpose |
|------|---------|
| `gitops/clusters/homelab/infrastructure/nut-pve/configmap-nut-configs.yaml` | NUT config files (/etc/nut/*) |
| `gitops/clusters/homelab/infrastructure/nut-pve/configmap-nut-scripts.yaml` | nut-notify.sh, test-nut-status.sh |
| `gitops/clusters/homelab/infrastructure/nut-pve/configmap-deploy-script.yaml` | Deployment script run by CronJob |
| `gitops/clusters/homelab/infrastructure/nut-pve/cronjob-nut-deploy.yaml` | Hourly sync CronJob + initial Job |
| `gitops/clusters/homelab/infrastructure/nut-pve/service-nut-exporter.yaml` | External Service/Endpoints for pve:9199 |
| `gitops/clusters/homelab/infrastructure/nut-pve/servicemonitor-nut-exporter.yaml` | Prometheus scrape config + alerts |

### On pve (Deployed by CronJob)

| File | Purpose |
|------|---------|
| /etc/nut/* | NUT configuration |
| /root/nut-notify.sh | Tiered shutdown script |
| /root/test-nut-status.sh | Quick status check |
| /usr/local/bin/nut_exporter | Prometheus exporter |

## Installation

### Prerequisites

1. USB cable connected from CyberPower UPS to pve
2. SSH key that can access root@pve.maas from K8s cluster
3. SSH keys on pve for shutdown targets:
   ```bash
   ssh root@pve.maas "ssh root@pumped-piglet.maas hostname"
   ssh root@pve.maas "ssh root@still-fawn.maas hostname"
   ssh root@pve.maas "ssh root@chief-horse.maas hostname"
   ```

### Deploy via GitOps

```bash
# 1. Create SSH key secret (one-time setup)
kubectl create secret generic nut-deploy-ssh-key -n monitoring \
  --from-file=id_rsa=$HOME/.ssh/id_rsa

# 2. Apply the kustomization (or let Flux sync it)
kubectl apply -k gitops/clusters/homelab/infrastructure/nut-pve/

# 3. Trigger initial deployment
kubectl create job --from=cronjob/nut-deploy nut-deploy-now -n monitoring

# 4. Watch the logs
kubectl logs -f job/nut-deploy-now -n monitoring
```

### Manual Deploy (Legacy)

```bash
# From Mac, copy scripts to pve
scp scripts/pve/setup-nut.sh scripts/pve/nut-notify.sh root@pve.maas:/tmp/

# On pve, run setup
ssh root@pve.maas
cd /tmp
chmod +x setup-nut.sh nut-notify.sh
./setup-nut.sh
```

## Verification

### Check UPS Status

```bash
# Quick status
/root/test-nut-status.sh

# Full details
upsc ups@localhost

# Key metrics only
upsc ups@localhost battery.charge
upsc ups@localhost battery.runtime
upsc ups@localhost ups.status
```

### Check Services

```bash
systemctl status nut-server
systemctl status nut-monitor
```

### Check Logs

```bash
# NUT notify log
tail -f /var/log/nut-notify.log

# System log
journalctl -u nut-monitor -f
```

## Testing

### Dry Run Notify Script

```bash
# Simulate ONBATT event (won't actually shutdown unless battery is low)
UPSNAME=ups NOTIFYTYPE=ONBATT /root/nut-notify.sh

# Check what would happen
cat /var/log/nut-notify.log
```

### Test SSH Connectivity

```bash
# Must work without password prompts
for host in pumped-piglet.maas still-fawn.maas chief-horse.maas; do
    echo "Testing $host..."
    ssh -o ConnectTimeout=5 -o BatchMode=yes root@$host hostname
done
```

### Simulate Power Failure (CAUTION)

**WARNING**: This will actually shut down systems!

```bash
# Only do this during maintenance window
upsmon -c fsd  # Force Shutdown - triggers full shutdown sequence
```

## Recovery After Power Outage

### 1. Verify Power Restored

Check that mains power is stable before bringing systems back up.

### 2. Start Hosts in Reverse Order

```bash
# 1. pve should auto-start (first to have power)
# 2. Start chief-horse (HAOS)
# 3. Start pumped-piglet, still-fawn

# If hosts don't auto-start, wake via IPMI/iLO or physical button
```

### 3. Verify VMs Started

```bash
# On each Proxmox host
qm list
pct list
```

### 4. Check K3s Cluster

```bash
# From a K3s node or with kubeconfig
kubectl get nodes
kubectl get pods -A | grep -v Running
```

### 5. Clear Shutdown State

The state file is automatically cleared when power returns (ONLINE event), but you can manually clear it:

```bash
rm -f /var/run/nut-shutdown-state
```

## Troubleshooting

### UPS Not Detected

```bash
# Check USB connection
lsusb | grep -i cyber

# Check driver
upsdrvctl start

# Check permissions
ls -la /dev/bus/usb/*/*

# Reload udev rules
udevadm control --reload-rules
udevadm trigger
```

### SSH Failures

```bash
# Test SSH
ssh -v root@pumped-piglet.maas hostname

# Check SSH key
cat /root/.ssh/id_rsa.pub

# Ensure key is in target's authorized_keys
ssh root@pumped-piglet.maas "cat /root/.ssh/authorized_keys"
```

### Notify Script Not Running

```bash
# Check upsmon config
grep NOTIFYCMD /etc/nut/upsmon.conf

# Check script permissions
ls -la /root/nut-notify.sh

# Test manually
UPSNAME=ups NOTIFYTYPE=ONBATT /root/nut-notify.sh
```

## NUT Commands Reference

| Command | Description |
|---------|-------------|
| `upsc ups@localhost` | Show all UPS variables |
| `upsc ups@localhost battery.charge` | Battery percentage |
| `upsc ups@localhost battery.runtime` | Estimated runtime (seconds) |
| `upsc ups@localhost ups.status` | OL=online, OB=on battery, LB=low battery |
| `upscmd -l ups@localhost` | List available commands |
| `upscmd ups@localhost test.battery.start.quick` | Start quick battery test |
| `upsmon -c fsd` | Force shutdown (DANGEROUS) |

## UPS Capabilities

The CyberPower CP1500 via NUT supports:
- Battery monitoring (charge, runtime, voltage)
- Load monitoring
- Whole-load control (`load.off`, `load.on`)
- Battery tests

**NOT supported**: Per-outlet control. All outlets are controlled together.

## Maintenance

### Battery Replacement

When `ups.status` shows `RB` (Replace Battery) or NUT sends REPLBATT notification:

1. Order replacement battery (check UPS manual for specs)
2. Schedule maintenance window
3. Replace battery
4. Run battery test: `upscmd ups@localhost test.battery.start.deep`

### Testing Schedule

- **Monthly**: Run `test-nut-status.sh` to verify connectivity
- **Quarterly**: Test SSH to all hosts
- **Annually**: Simulate power failure during maintenance window

## Prometheus Metrics

The `nut_exporter` on pve exposes metrics at `http://192.168.4.122:9199/metrics`:

| Metric | Description |
|--------|-------------|
| `nut_battery_charge` | Battery charge percentage |
| `nut_battery_runtime_seconds` | Estimated runtime remaining |
| `nut_ups_status` | UPS status (OL=online, OB=on battery, LB=low battery) |
| `nut_load` | UPS load percentage |
| `nut_input_voltage` | Input voltage |
| `nut_output_voltage` | Output voltage |

### Grafana Dashboard

Query examples:
```promql
# Battery charge
nut_battery_charge{ups="ups"}

# Runtime in minutes
nut_battery_runtime_seconds{ups="ups"} / 60

# Is on battery?
nut_ups_status{ups="ups", status="OB"}
```

### Configured Alerts

| Alert | Condition | Severity |
|-------|-----------|----------|
| UPSOnBattery | status=OB | warning |
| UPSLowBattery | charge < 30% | critical |
| UPSBatteryCritical | charge < 15% | critical |
| UPSOffline | exporter down > 2m | warning |
| UPSHighLoad | load > 80% for 5m | warning |
| UPSReplaceBattery | status=RB | warning |

## Modifying Configuration

1. Edit files in `gitops/clusters/homelab/infrastructure/nut-pve/`
2. Commit and push to git
3. Flux syncs automatically, or force sync:
   ```bash
   flux reconcile kustomization flux-system --with-source
   ```
4. CronJob runs hourly, or trigger immediately:
   ```bash
   kubectl create job --from=cronjob/nut-deploy nut-deploy-manual-$(date +%s) -n monitoring
   ```

## Tags

nut, ups, network-ups-tools, cyberpower, cp1500, power, outage, shutdown, tiered-shutdown, graceful-shutdown, pve, proxmox, battery, usb, prometheus, nut-exporter, gitops
