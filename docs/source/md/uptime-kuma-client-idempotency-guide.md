# Uptime Kuma Client Idempotency Guide

## Overview

The UptimeKumaClient has been enhanced to be fully idempotent, ensuring that running monitor configuration multiple times produces consistent results without creating duplicates or losing configuration changes.

## Problem Solved

**Before (Non-Idempotent):**
- Running `create_homelab_monitors()` multiple times created duplicate monitors
- Existing monitors were skipped entirely, even if configuration changed
- No way to update monitor configurations programmatically
- Manual cleanup required for duplicate monitors

**After (Idempotent):**
- ✅ **Creates** monitors that don't exist
- ✅ **Updates** monitors when configuration differs  
- ✅ **Skips** monitors that are already up to date
- ✅ **Logs** detailed comparison of configuration fields
- ✅ **Returns** status for each operation

## Implementation Details

### New Methods Added

```python
def get_monitor_by_name(self, name: str) -> Dict[str, Any]:
    """Get monitor details by name for comparison."""
    
def update_monitor(self, monitor_id: int, **config: Any) -> bool:
    """Update an existing monitor configuration."""
```

### Enhanced Monitor Processing

```python
# Create or update monitors (idempotent)
for monitor_config in monitors_config:
    monitor_name = monitor_config["name"]
    
    # Check if monitor already exists
    existing_monitor = self.get_monitor_by_name(monitor_name)
    
    if existing_monitor:
        # Compare configuration and update if needed
        if needs_update:
            self.update_monitor(monitor_id, **config)
            status = "updated"
        else:
            status = "up_to_date"
    else:
        # Create new monitor
        self.api.add_monitor(name=monitor_name, **config)
        status = "created"
```

### Configuration Comparison

The client compares these key fields to detect changes:
- `hostname` - Target host/URL
- `url` - HTTP/HTTPS endpoint  
- `port` - Port number for PORT monitors
- `interval` - Check interval in seconds
- `maxretries` - Maximum retry attempts
- `retryInterval` - Delay between retries
- `type` - Monitor type (PING, HTTP, PORT, DNS)
- `method` - HTTP method (GET, POST, etc.)
- `description` - Monitor description

## Usage Examples

### Basic Idempotent Deployment

```python
from src.homelab.uptime_kuma_client import UptimeKumaClient

client = UptimeKumaClient('http://192.168.4.224:3001')
if client.connect():
    # First run - creates all monitors
    results1 = client.create_homelab_monitors()
    
    # Second run - all monitors show "up_to_date"
    results2 = client.create_homelab_monitors()
    
    client.disconnect()
```

### Configuration Updates

```python
# Change a monitor configuration in uptime_kuma_client.py
{
    "name": "OPNsense Gateway",
    "hostname": "192.168.4.1",
    "interval": 30,  # Changed from 60 to 30
}

# Run client - automatically detects and applies change
client = UptimeKumaClient('http://192.168.4.224:3001')
if client.connect():
    results = client.create_homelab_monitors()
    # Result: OPNsense Gateway shows "updated" status
```

### Status Interpretation

```python
results = client.create_homelab_monitors()
for result in results:
    name = result.get('name')
    status = result.get('status')
    monitor_id = result.get('monitor_id')
    
    if status == 'created':
        print(f"✅ New monitor: {name}")
    elif status == 'updated':
        print(f"🔄 Updated monitor: {name}")
    elif status == 'up_to_date':
        print(f"➡️ No changes: {name}")
    elif status == 'failed':
        print(f"❌ Failed: {name}")
```

## Testing Idempotency

### Verification Script

```python
#!/usr/bin/env python3
"""Test idempotent behavior of UptimeKumaClient."""

from src.homelab.uptime_kuma_client import UptimeKumaClient

def test_idempotency(url: str, instance_name: str):
    client = UptimeKumaClient(url)
    if not client.connect():
        print(f"Failed to connect to {instance_name}")
        return
        
    print(f"Testing {instance_name}...")
    
    # First run
    print("First run:")
    results1 = client.create_homelab_monitors()
    created_count1 = len([r for r in results1 if r.get('status') == 'created'])
    updated_count1 = len([r for r in results1 if r.get('status') == 'updated'])
    
    # Second run (should be idempotent)
    print("Second run:")
    results2 = client.create_homelab_monitors()
    up_to_date_count2 = len([r for r in results2 if r.get('status') == 'up_to_date'])
    
    print(f"First run: {created_count1} created, {updated_count1} updated")
    print(f"Second run: {up_to_date_count2} up to date")
    
    if up_to_date_count2 == len(results2):
        print(f"✅ {instance_name} is idempotent")
    else:
        print(f"❌ {instance_name} is not idempotent")
    
    client.disconnect()

# Test both instances
test_idempotency('http://192.168.4.224:3001', 'fun-bedbug')
test_idempotency('http://192.168.4.194:3001', 'pve')
```

## Logging and Debugging

### Enable Detailed Logging

```python
import logging
logging.basicConfig(level=logging.INFO)

client = UptimeKumaClient('http://192.168.4.224:3001')
# Logs will show:
# - Connection attempts
# - Monitor comparisons  
# - Field differences detected
# - Update operations
# - Success/failure results
```

### Example Log Output

```
INFO:src.homelab.uptime_kuma_client:Connecting to Uptime Kuma at http://192.168.4.224:3001
INFO:src.homelab.uptime_kuma_client:✅ Authentication successful
INFO:src.homelab.uptime_kuma_client:Monitor 'OPNsense Gateway' field 'interval' differs: 60 -> 30
INFO:src.homelab.uptime_kuma_client:Updating monitor: OPNsense Gateway
INFO:src.homelab.uptime_kuma_client:✅ Successfully updated monitor 'OPNsense Gateway' (ID: 1)
INFO:src.homelab.uptime_kuma_client:Monitor 'MAAS Server' is up to date
```

## Benefits

### Operational Benefits
- **Safe to run repeatedly** - No duplicate monitors created
- **Configuration drift detection** - Automatically updates changed monitors
- **Deployment automation** - Can be integrated into CI/CD pipelines
- **Disaster recovery** - Rebuilds exact configuration from code

### Development Benefits  
- **Predictable behavior** - Same input always produces same result
- **Easy testing** - Can run tests multiple times safely
- **Version control** - Monitor configuration managed in code
- **Rollback capability** - Change code and re-run to rollback configurations

## Migration from Non-Idempotent Version

### Cleanup Duplicate Monitors

```python
from src.homelab.uptime_kuma_client import UptimeKumaClient

client = UptimeKumaClient('http://192.168.4.194:3001')
if client.connect():
    monitors = client.api.get_monitors()
    
    # Remove all Secondary monitors (duplicates)
    secondary_monitors = [m for m in monitors if '(Secondary)' in m.get('name', '')]
    
    for monitor in secondary_monitors:
        monitor_id = monitor.get('id')
        client.api.delete_monitor(monitor_id)
        print(f"Removed: {monitor.get('name')}")
    
    client.disconnect()
```

### Verify Clean State

```python
# After cleanup, run idempotent client
client = UptimeKumaClient('http://192.168.4.194:3001')
if client.connect():
    results = client.create_homelab_monitors()
    
    # Should show all monitors as "up_to_date" or minimal "updated"
    for result in results:
        print(f"{result.get('name')}: {result.get('status')}")
```

## Best Practices

### Monitor Configuration Management
1. **Define monitors in code** - Use uptime_kuma_client.py as single source of truth
2. **Version control changes** - Commit monitor configuration changes to git
3. **Test changes** - Use staging instance to test configuration updates
4. **Document changes** - Include monitor changes in commit messages

### Deployment Process
1. **Update configuration** in uptime_kuma_client.py
2. **Test locally** with development instance
3. **Deploy to production** instances via CI/CD or manual execution
4. **Verify results** by checking returned status for each monitor

### Monitoring the Monitors
1. **Log deployment results** for audit trail
2. **Monitor configuration drift** by running client periodically
3. **Alert on failures** when monitor creation/updates fail
4. **Backup configurations** by version controlling the client code

## Related Documentation

- [Complete Uptime Kuma Monitoring Setup Guide](uptime-kuma-monitoring-complete-guide.md)
- [DNS Configuration Guide](dns-configuration-guide.md)
- [Monitoring and Alerting Guide](monitoring-alerting-guide.md)