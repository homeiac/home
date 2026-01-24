# Proxmox Memory Analysis: Why "Low Free Memory" is Normal

## TL;DR

Low "free" memory on Proxmox hosts is normal and healthy. Linux and ZFS use available RAM for caching, which is instantly reclaimable when needed.

## Case Study: pumped-piglet (62.4GB RAM)

### atop showed concerning numbers

```
MEM | tot 62.4G | free 2.4G | cache 196.8M | buff 664.2M | slab 2.2G
```

Only 2.4GB free on a 64GB host? Investigation revealed:

### Actual memory breakdown

| Consumer | Memory | Notes |
|----------|--------|-------|
| K3s VM (VMID 105) | 32.0 GB | Fixed allocation via `qm config` |
| ZFS ARC cache | 24.8 GB | Read cache, auto-shrinks on demand |
| Host overhead | ~3-4 GB | Kernel, slab, services |
| Free | 2.4 GB | Intentionally low - unused RAM is wasted RAM |
| **Total** | ~62 GB | ✓ All accounted for |

### How to verify

```bash
# Check VM memory allocation
qm config 105 | grep -E 'memory|balloon'

# Check ZFS ARC size (in bytes)
cat /proc/spl/kstat/zfs/arcstats | grep -E '^size|^c_max'

# Check top memory consumers
ps aux --sort=-%mem | head -10
```

## What indicates REAL memory pressure

| Indicator | How to check | Healthy value |
|-----------|--------------|---------------|
| Swap activity | `atop` SWP line, `shswp` field | 0 or near-zero |
| OOM kills | `atop` MEM line, `oomkill` field | 0 |
| Memory full % | `atop` SI line, `memfull` field | 0% |
| Page-in/out | `vmstat 1` si/so columns | 0 or near-zero |

## Why ZFS ARC makes "free" misleading

ZFS Adaptive Replacement Cache (ARC) aggressively caches disk reads in RAM:

- **c_max**: Maximum ARC size (configurable)
- **size**: Current ARC usage
- ARC **automatically shrinks** when applications request memory
- This is different from application memory - it's instantly reclaimable

### Check ARC status

```bash
# Current ARC size in human-readable format
arc_size=$(cat /proc/spl/kstat/zfs/arcstats | grep "^size" | awk '{print $3}')
echo "ZFS ARC: $(echo "scale=2; $arc_size / 1024 / 1024 / 1024" | bc) GB"

# ARC max limit
arc_max=$(cat /proc/spl/kstat/zfs/arcstats | grep "^c_max" | awk '{print $3}')
echo "ARC Max: $(echo "scale=2; $arc_max / 1024 / 1024 / 1024" | bc) GB"
```

## Rule of thumb

- **Low free memory + no swap activity = healthy**
- **Low free memory + active swapping = investigate**
- **OOM kills occurring = definite problem**

## References

- [ZFS ARC Documentation](https://openzfs.github.io/openzfs-docs/Performance%20and%20Tuning/Module%20Parameters.html)
- [Linux Memory Management](https://www.kernel.org/doc/html/latest/admin-guide/mm/concepts.html)
