#!/usr/bin/env python3
"""
Add Uptime Kuma LXC containers as devices in MAAS for persistent hostnames and IPs.
"""

import subprocess
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAAS_HOST = "192.168.4.53"
MAAS_USER = "gshiva"
MAAS_PASSWORD = "REDACTED_MQTT_PASSWORD"

# Uptime Kuma LXC container details
UPTIME_KUMA_DEVICES = [
    {
        "hostname": "uptime-kuma-fun-bedbug",
        "mac_address": "BC:24:11:5F:CD:81",
        "description": "Uptime Kuma monitoring instance on fun-bedbug (LXC 112)",
        "current_ip": "192.168.4.224"
    },
    {
        "hostname": "uptime-kuma-pve", 
        "mac_address": "BC:24:11:B3:D0:40",
        "description": "Uptime Kuma monitoring instance on pve (LXC 100)",
        "current_ip": "192.168.4.194"
    }
]

def run_maas_command(command: str) -> dict:
    """Execute MAAS CLI command via SSH."""
    ssh_cmd = [
        "ssh", f"{MAAS_USER}@{MAAS_HOST}",
        f"echo '{MAAS_PASSWORD}' | {command}"
    ]
    
    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.error(f"MAAS command failed: {result.stderr}")
            return {}
        
        if result.stdout.strip():
            return json.loads(result.stdout)
        return {}
    except subprocess.TimeoutExpired:
        logger.error("SSH command timed out")
        return {}
    except json.JSONDecodeError:
        logger.error(f"Failed to parse JSON response: {result.stdout}")
        return {}
    except Exception as e:
        logger.error(f"SSH command failed: {e}")
        return {}

def check_device_exists(hostname: str) -> bool:
    """Check if device already exists in MAAS."""
    logger.info(f"Checking if device {hostname} exists...")
    
    devices = run_maas_command("maas admin devices read")
    if not devices:
        return False
    
    for device in devices:
        if device.get("hostname") == hostname:
            logger.info(f"Device {hostname} already exists")
            return True
    
    return False

def create_maas_device(device_info: dict) -> bool:
    """Create a device in MAAS."""
    hostname = device_info["hostname"]
    mac_address = device_info["mac_address"]
    description = device_info["description"]
    
    if check_device_exists(hostname):
        logger.info(f"Skipping {hostname} - already exists")
        return True
    
    logger.info(f"Creating MAAS device: {hostname}")
    
    command = (
        f"maas admin devices create "
        f"hostname={hostname} "
        f"mac_addresses={mac_address} "
        f"domain=0"
    )
    
    result = run_maas_command(command)
    
    if result and result.get("hostname") == hostname:
        logger.info(f"✅ Successfully created device: {hostname}")
        logger.info(f"   MAC: {mac_address}")
        logger.info(f"   FQDN: {result.get('fqdn', 'N/A')}")
        logger.info(f"   System ID: {result.get('system_id', 'N/A')}")
        return True
    else:
        logger.error(f"❌ Failed to create device: {hostname}")
        return False

def update_device_description(hostname: str, description: str) -> bool:
    """Update device description (if device already exists)."""
    devices = run_maas_command("maas admin devices read")
    if not devices:
        return False
    
    for device in devices:
        if device.get("hostname") == hostname:
            system_id = device.get("system_id")
            if system_id:
                command = f"maas admin device update {system_id} description='{description}'"
                result = run_maas_command(command)
                if result:
                    logger.info(f"✅ Updated description for {hostname}")
                    return True
    
    return False

def main():
    """Add Uptime Kuma LXC containers as MAAS devices."""
    logger.info("Adding Uptime Kuma containers as MAAS devices...")
    
    success_count = 0
    
    for device_info in UPTIME_KUMA_DEVICES:
        hostname = device_info["hostname"]
        
        try:
            if create_maas_device(device_info):
                success_count += 1
            else:
                # If creation failed, try updating description if device exists
                if check_device_exists(hostname):
                    update_device_description(hostname, device_info["description"])
        
        except Exception as e:
            logger.error(f"Error processing {hostname}: {e}")
    
    logger.info(f"\n=== Summary ===")
    logger.info(f"Successfully processed: {success_count}/{len(UPTIME_KUMA_DEVICES)} devices")
    
    if success_count == len(UPTIME_KUMA_DEVICES):
        logger.info("🎉 All Uptime Kuma devices added to MAAS!")
        logger.info("\nNext steps:")
        logger.info("1. Wait for DHCP renewal or reboot containers")
        logger.info("2. Verify DNS resolution:")
        logger.info("   - nslookup uptime-kuma-fun-bedbug.maas")
        logger.info("   - nslookup uptime-kuma-pve.maas")
        logger.info("3. Update monitoring client URLs to use hostnames")
    else:
        logger.warning("⚠️ Some devices may need manual attention")

if __name__ == "__main__":
    main()