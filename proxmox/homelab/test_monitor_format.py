#!/usr/bin/env python3
"""
Test proper monitor format using the official uptime-kuma-api library
"""

import os
from dotenv import load_dotenv
from uptime_kuma_api import UptimeKumaApi, MonitorType

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

def test_monitor_creation():
    username = os.getenv('UPTIME_KUMA_USERNAME')
    password = os.getenv('UPTIME_KUMA_PASSWORD')
    pve_url = os.getenv('UPTIME_KUMA_PVE_URL')
    
    print(f"Testing with: {username} at {pve_url}")
    
    api = UptimeKumaApi(pve_url)
    api.login(username, password)
    
    # Test creating a simple ping monitor
    try:
        result = api.add_monitor(
            type=MonitorType.PING,
            name="Test - Google DNS",
            hostname="8.8.8.8",
            interval=60
        )
        print(f"✅ Successfully created monitor: {result}")
        
        # Get all monitors to see the format
        monitors = api.get_monitors()
        print(f"\nExisting monitors:")
        for monitor in monitors:
            print(f"  ID: {monitor['id']}, Name: {monitor['name']}, Type: {monitor['type']}")
            print(f"    Config: {monitor}")
            break  # Just show first one for format reference
            
    except Exception as e:
        print(f"❌ Error: {e}")
        
    finally:
        api.disconnect()

if __name__ == "__main__":
    test_monitor_creation()