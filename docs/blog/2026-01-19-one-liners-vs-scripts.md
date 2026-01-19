# One-Liners Fix Today, Scripts Fix Tomorrow

**Date**: 2026-01-19
**Tags**: automation, scripts, homelab, methodology, lessons-learned

## The Situation

Grafana dashboard showing "No data" for hardware temperature on still-fawn. Quick investigation revealed: node-exporter wasn't installed on the Proxmox host.

The fix? One command:

```bash
ssh root@still-fawn.maas "apt-get update && apt-get install -y prometheus-node-exporter"
```

Done. Dashboard works. Move on with life.

## Why That's Wrong

Three months from now:
- New Proxmox host joins the cluster
- "Why isn't it showing up in Grafana?"
- Spend 20 minutes rediscovering the fix
- Run the one-liner again
- Repeat forever

The one-liner fixes today but leaves nothing for tomorrow.

## The Right Approach

Build a tool that:
1. Reads from existing config (don't duplicate host lists)
2. Is idempotent (safe to run repeatedly)
3. Integrates with existing CLI
4. Has both `status` and `apply` commands

What I built:

```bash
# Check what's missing
poetry run homelab monitoring status

================================================================================
Host                 IP               Status     Version      Sensors
================================================================================
still-fawn           192.168.4.17     MISSING    -            -
pumped-piglet        192.168.4.175    OK         1.5.0-1+b6   coretemp, nvme
chief-horse          192.168.4.174    OK         1.5.0-1+b6   acpitz, coretemp
fun-bedbug           192.168.4.172    OK         1.5.0-1+b6   amdgpu, k10temp
================================================================================

# Fix all hosts
poetry run homelab monitoring apply
```

The module reads hosts from `config/cluster.yaml` - the same file that defines GPU passthrough, storage, and backup jobs. Single source of truth.

## The Decision Framework

| Approach | When to Use |
|----------|-------------|
| Run command directly | Never for infra changes |
| Bash script in `scripts/` | Simple, standalone tasks |
| Python module with CLI | Integrates with existing config/tooling |

The key question: **Will this need to run again?**

For infrastructure: the answer is always yes.

## What the Module Does

```python
# node_exporter_manager.py

def apply_from_config(config_path):
    """Deploy node-exporter to all enabled hosts from cluster.yaml"""
    config = load_cluster_config(config_path)
    hosts = get_enabled_hosts(config)

    for host in hosts:
        with NodeExporterManager(host["name"], config=config) as manager:
            result = manager.deploy()  # Idempotent
```

It's ~300 lines of Python instead of a 1-line bash command. But:
- Next host addition: just add to `cluster.yaml`, run `apply`
- Audit what's deployed: `homelab monitoring status`
- Consistent with other homelab tooling
- Self-documenting

## The Config

```yaml
# config/cluster.yaml
monitoring:
  node_exporter:
    enabled: true
    package: prometheus-node-exporter
    port: 9100
    collectors:
      - hwmon
      - thermal_zone
    host_sensors:
      still-fawn:
        - amdgpu
      pumped-piglet:
        - coretemp
```

Expected sensors per host means the status command can warn when something's missing.

## Time Comparison

| Approach | Time Today | Time Next Occurrence |
|----------|-----------|---------------------|
| One-liner | 2 min | 20 min (rediscover) |
| Script | 15 min | 1 min (run script) |
| Module | 45 min | 30 sec (`homelab monitoring apply`) |

The module took longer upfront but pays off on every future use.

## The Rule

From my CLAUDE.md:

> **If a task might be done more than once, CREATE A SCRIPT FILE.**
> - Even for one-liners - make it a script
> - Location: `scripts/<component>/`

For infrastructure tasks, "might be done more than once" is always true.

## Conclusion

The one-liner was tempting. It would have worked. The dashboard would show data.

But the question isn't "does it work now?" - it's "what happens when I need to do this again and don't remember how?"

Build the tool. Integrate with config. Make it idempotent. Future you will thank present you.
