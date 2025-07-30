#!/usr/bin/env python3
"""
Quick script to update all monitor configurations with secondary instance logic
"""

import re

# Read the file
with open('src/homelab/uptime_kuma_client.py', 'r') as f:
    content = f.read()

# Update all monitor names to include suffix
content = re.sub(r'"name": "([^"]+)"', r'"name": f"\1{instance_suffix}"', content)

# Update all intervals to use multiplier  
content = re.sub(r'"interval": (\d+)', r'"interval": \1 * base_interval_multiplier', content)

# Update all retryInterval to use base_retry_delay (with multipliers for longer services)
content = re.sub(r'"retryInterval": 30', r'"retryInterval": base_retry_delay // 2', content)
content = re.sub(r'"retryInterval": 60', r'"retryInterval": base_retry_delay', content) 
content = re.sub(r'"retryInterval": 120', r'"retryInterval": base_retry_delay * 2', content)

# Write back
with open('src/homelab/uptime_kuma_client.py', 'w') as f:
    f.write(content)

print("✅ Updated all monitors with secondary instance logic")