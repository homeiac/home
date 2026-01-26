#!/usr/bin/env python3
"""
Camera IP Sync - discovers Reolink cameras by MAC and writes to file.
Run from HAOS: python3 /config/scripts/camera-ip-sync.py

Output: /config/camera_ips.json with current camera IPs
HA can read this file via file sensor or command_line sensor.
"""
import subprocess
import re
import json
import sys
import os
from datetime import datetime

# Camera MAC addresses (from nmap scan)
CAMERAS = {
    "hall": "0C:79:55:4B:D4:2A",
    "living_room": "14:EA:63:A9:04:08",
}

# Scan a smaller range for speed (cameras are usually in .130-.150)
SCAN_RANGE = os.environ.get("SCAN_RANGE", "192.168.1.130-150")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "/config/camera_ips.json")


def scan_network(scan_range):
    """Run nmap and return MAC->IP mapping."""
    print(f"Running nmap on {scan_range}...")
    result = subprocess.run(
        ["nmap", "-sn", scan_range],
        capture_output=True,
        text=True,
        timeout=120
    )

    # Parse nmap output
    mac_to_ip = {}
    current_ip = None

    for line in result.stdout.split('\n'):
        ip_match = re.search(r'Nmap scan report for .*?(\d+\.\d+\.\d+\.\d+)', line)
        if ip_match:
            current_ip = ip_match.group(1)

        mac_match = re.search(r'MAC Address: ([0-9A-Fa-f:]+)', line)
        if mac_match and current_ip:
            mac = mac_match.group(1).upper()
            mac_to_ip[mac] = current_ip

    return mac_to_ip


def main():
    print("=== Camera IP Sync ===")
    print(f"Time: {datetime.now().isoformat()}")

    # First try narrow scan
    mac_to_ip = scan_network(SCAN_RANGE)

    # Find our cameras
    camera_ips = {}
    for camera_name, mac in CAMERAS.items():
        if mac in mac_to_ip:
            camera_ips[camera_name] = mac_to_ip[mac]

    # If not all found, try wider scan
    if len(camera_ips) != len(CAMERAS):
        print("Not all cameras found in narrow range, scanning full subnet...")
        mac_to_ip = scan_network("192.168.1.0/24")
        for camera_name, mac in CAMERAS.items():
            if mac in mac_to_ip:
                camera_ips[camera_name] = mac_to_ip[mac]

    # Report status
    print("\n=== Camera Status ===")
    for camera_name, mac in CAMERAS.items():
        if camera_name in camera_ips:
            print(f"  {camera_name}: {camera_ips[camera_name]}")
        else:
            print(f"  {camera_name}: NOT FOUND (MAC: {mac})")

    # Write output
    output = {
        "timestamp": datetime.now().isoformat(),
        "cameras": camera_ips,
        "all_found": len(camera_ips) == len(CAMERAS),
    }

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {OUTPUT_FILE}")

    # Also print JSON for command_line sensor
    print(f"\nJSON: {json.dumps(camera_ips)}")

    if len(camera_ips) != len(CAMERAS):
        sys.exit(1)


if __name__ == "__main__":
    main()
