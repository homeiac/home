# MAAS IP Range Management Guide

## Overview
This guide explains the critical differences between IP range types in Ubuntu MAAS and provides practical examples for managing IP address allocation in homelab environments.

## Understanding MAAS IP Range Types

MAAS provides different types of IP ranges that serve distinct purposes. Understanding these differences is crucial for proper network management.

### Reserve Range (Static Reserved)
**Purpose**: User-controlled IP addresses that MAAS will not automatically assign

**Key Characteristics**:
- ✅ **Prevents automatic assignment** by MAAS DHCP
- ✅ **Allows manual static assignment** to specific machines
- ✅ **User has full control** over IP allocation within the range
- ✅ **Perfect for infrastructure services** that need consistent IPs

**Use Cases**:
- Database servers that need consistent IPs
- Kubernetes nodes requiring stable cluster membership
- Infrastructure services referenced by IP address
- Services that need DNS entries with static IPs

### Reserve Dynamic Range
**Purpose**: MAAS-controlled IP addresses for internal automation processes

**Key Characteristics**:
- ❌ **MAAS internal use only** - cannot manually assign from this range
- ✅ **Used for MAAS operations**: enlisting, commissioning, deployment
- ✅ **Temporary DHCP assignments** during machine provisioning
- ❌ **No user control** over individual IP assignments

**Use Cases**:
- Machine discovery (PXE boot process)
- Hardware commissioning phase
- OS deployment temporary networking
- MAAS automation workflows

## Common Misconception

**❌ Wrong Assumption**: "Reserve Dynamic Range" allows flexible user assignment of IPs
**✅ Reality**: "Reserve Dynamic Range" is for MAAS internal automation only

The naming is confusing - "dynamic" refers to MAAS-controlled dynamic assignment, not user-controlled flexibility.

## Practical IP Strategy

### Recommended IP Layout
```
Network: 192.168.4.0/24

Reserved Dynamic Range:  192.168.4.20-49   (MAAS internal operations)
DHCP Pool:              192.168.4.50-79   (Auto-assigned to new machines)
External Services:      192.168.4.80-120  (MetalLB, appliances - fully reserved)
Static Infrastructure:  192.168.4.200-250 (Reserved range for manual assignment)
```

### Why This Layout Works

**Reserved Dynamic Range (20-49)**:
- Sufficient IPs for MAAS commissioning operations
- Isolated from user-managed ranges
- Automatically managed by MAAS

**DHCP Pool (50-79)**:
- Default assignment for new machines
- No manual intervention required
- Good for ephemeral workloads

**External Services (80-120)**:
- Completely outside MAAS control
- Used by MetalLB, network appliances
- Prevents IP conflicts

**Static Infrastructure (200-250)**:
- Manual assignment within MAAS
- Consistent IPs for important services
- User-controlled allocation

## Implementation Examples

### Creating IP Ranges via Web UI

**Step 1: Reserve Dynamic Range (MAAS Internal)**
1. Navigate to **Subnets** → Select your subnet
2. Click **Reserve Dynamic Range**
3. **Start IP**: 192.168.4.20
4. **End IP**: 192.168.4.49
5. **Comment**: "MAAS internal operations - commissioning/deployment"

**Step 2: Reserve Range (Manual Assignment)**
1. Navigate to **Subnets** → Select your subnet  
2. Click **Reserve Range**
3. **Start IP**: 192.168.4.200
4. **End IP**: 192.168.4.250
5. **Comment**: "Static infrastructure - manual assignment only"

### CLI Configuration

**Create Reserved Dynamic Range:**
```bash
maas $PROFILE ipranges create type=dynamic \
  subnet=192.168.4.0/24 \
  start_ip=192.168.4.20 \
  end_ip=192.168.4.49 \
  comment='MAAS internal operations'
```

**Create Reserved Range (Static):**
```bash
maas $PROFILE ipranges create type=reserved \
  subnet=192.168.4.0/24 \
  start_ip=192.168.4.200 \
  end_ip=192.168.4.250 \
  comment='Static infrastructure services'
```

**Reserve Single IP:**
```bash
maas $PROFILE ipaddresses reserve ip_address=192.168.4.210
```

## Manual Static IP Assignment

### Assigning Static IPs from Reserved Range

**Via Web UI:**
1. **Machines** → Select machine → **Network** tab
2. Select the network interface
3. **IP Assignment**: Change from "Auto assign" to "Static assign"
4. **IP Address**: Enter IP from reserved range (e.g., 192.168.4.201)
5. **Save** changes

**Via CLI:**
```bash
# Assign static IP to machine
maas $PROFILE machine update $SYSTEM_ID \
  interface set $INTERFACE_ID ip_assignment=static ip_address=192.168.4.201
```

## Real-World Use Cases

### Case 1: Kubernetes Cluster
**Problem**: K3s nodes need consistent IPs for cluster membership

**Solution**: Use Reserved Range for manual assignment
```
k3s-master-1: 192.168.4.201 (from reserved range)
k3s-worker-1: 192.168.4.202 (from reserved range)  
k3s-worker-2: 192.168.4.203 (from reserved range)
```

**Configuration:**
- Create Reserved Range: 192.168.4.200-210
- Manually assign each node a static IP
- Nodes get consistent IPs via MAAS DHCP

### Case 2: Database Server
**Problem**: Application needs to connect to database by IP

**Solution**: Reserved Range with static assignment
```
postgres-primary: 192.168.4.220 (from reserved range)
postgres-replica: 192.168.4.221 (from reserved range)
```

### Case 3: Mixed Environment
**Problem**: Some machines need static IPs, others can be dynamic

**Solution**: Combined approach
```
# Most machines get dynamic IPs from DHCP pool (50-79)
web-server-01: DHCP → 192.168.4.55 (changes on reboot)
web-server-02: DHCP → 192.168.4.61 (changes on reboot)

# Critical infrastructure gets static IPs from reserved range
database-server: Static → 192.168.4.201 (never changes)
redis-cache: Static → 192.168.4.202 (never changes)
```

## Troubleshooting

### Cannot Manually Assign IP from Dynamic Range
**Problem**: MAAS won't let you assign IP from reserved dynamic range

**Cause**: Reserved dynamic ranges are for MAAS internal use only

**Solution**: 
```bash
# Wrong: Trying to use dynamic range
Reserved Dynamic: 192.168.4.20-49 ❌ Cannot manually assign

# Correct: Use reserved range instead  
Reserved Range: 192.168.4.200-250 ✅ Can manually assign
```

### IP Conflicts with External Services
**Problem**: MAAS assigns IP that conflicts with MetalLB/appliances

**Solution**: Properly reserve external IP ranges
```bash
# Reserve the entire MetalLB range
maas $PROFILE ipranges create type=reserved \
  subnet=192.168.4.0/24 \
  start_ip=192.168.4.80 \
  end_ip=192.168.4.120 \
  comment='MetalLB LoadBalancer pool - external to MAAS'
```

### Machine Won't Get Static IP
**Problem**: Machine assigned to reserved range doesn't get expected IP

**Verification Steps**:
1. **Check range type**: Must be "reserved" (not "dynamic")
2. **Verify assignment**: Machine interface set to "Static assign"  
3. **Confirm IP is available**: Not already assigned to another machine
4. **Check DHCP**: Ensure subnet has DHCP enabled

## Best Practices

### IP Range Planning
1. **Plan before implementation** - changing ranges later affects existing machines
2. **Leave room for growth** - reserve more IPs than currently needed
3. **Document IP assignments** - maintain record of static assignments
4. **Use meaningful names** - clear comments for each range purpose

### Security Considerations
1. **Limit reserved ranges** - don't over-allocate static IP space
2. **Monitor assignments** - track which machines have static IPs
3. **Regular audits** - verify actual IP usage matches MAAS records

### Integration with Other Services

**DNS Integration:**
```bash
# For static infrastructure IPs, add DNS overrides
# OPNsense: Services → Unbound DNS → Overrides
k3s-master.homelab → 192.168.4.201
database.homelab  → 192.168.4.220
```

**MetalLB Integration:**
```yaml
# Reserve range in MAAS to prevent conflicts
# Configure MetalLB to use same range
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: homelab-pool
spec:
  addresses:
    - 192.168.4.80-120  # Reserved in MAAS as external range
```

## Summary

### Key Takeaways
- **Reserved Range**: For user-controlled static IP assignment
- **Reserved Dynamic Range**: For MAAS internal automation only
- **Plan IP layout carefully** to avoid conflicts
- **Use static assignment sparingly** - only for services that need consistency
- **Reserve external service ranges** to prevent MAAS conflicts

### Decision Matrix

| Requirement | Range Type | Example |
|-------------|------------|---------|
| MAAS needs IPs for commissioning | Reserved Dynamic Range | 192.168.4.20-49 |
| Regular machines, dynamic IPs OK | DHCP Pool | 192.168.4.50-79 |
| External services (MetalLB, etc.) | Reserved Range | 192.168.4.80-120 |
| Infrastructure needing static IPs | Reserved Range | 192.168.4.200-250 |

This approach provides operational flexibility while maintaining control where needed, preventing IP conflicts across your entire infrastructure.

## References
- [Official MAAS Documentation: How to manage IP ranges](https://maas.io/docs/how-to-manage-ip-ranges)
- [MAAS IP Ranges CLI Reference](https://maas.io/docs/snap/2.8/cli/ip-ranges)
- [MetalLB Configuration Guide](../metallb-configuration-guide.md)
- [Homelab Network Architecture](../proxmox-infrastructure-guide.md)