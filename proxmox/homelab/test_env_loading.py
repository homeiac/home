#!/usr/bin/env python3
"""
Test environment variable loading
"""

import os
from dotenv import load_dotenv

print("Before load_dotenv:")
print(f"UPTIME_KUMA_USERNAME: {os.getenv('UPTIME_KUMA_USERNAME', 'NOT_SET')}")
print(f"UPTIME_KUMA_PASSWORD: {os.getenv('UPTIME_KUMA_PASSWORD', 'NOT_SET')}")

# Load .env file
load_dotenv()

print("\nAfter load_dotenv:")
print(f"UPTIME_KUMA_USERNAME: {os.getenv('UPTIME_KUMA_USERNAME', 'NOT_SET')}")
print(f"UPTIME_KUMA_PASSWORD: {'*' * len(os.getenv('UPTIME_KUMA_PASSWORD', ''))}")
print(f"UPTIME_KUMA_PVE_URL: {os.getenv('UPTIME_KUMA_PVE_URL', 'NOT_SET')}")
print(f"UPTIME_KUMA_PVE_API_KEY: {os.getenv('UPTIME_KUMA_PVE_API_KEY', 'NOT_SET')}")

# Test the actual file exists
print(f"\n.env file exists: {os.path.exists('.env')}")
print(f"Current directory: {os.getcwd()}")

if os.path.exists('.env'):
    print("\n.env file contents:")
    with open('.env', 'r') as f:
        for i, line in enumerate(f, 1):
            if 'UPTIME_KUMA' in line:
                print(f"  {i}: {line.rstrip()}")