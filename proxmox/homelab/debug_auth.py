#!/usr/bin/env python3
"""
Debug authentication with Uptime Kuma
"""

import logging
import socketio
import time
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def debug_auth(base_url: str):
    """Debug authentication flow."""
    
    sio = socketio.Client()
    events_received = []
    
    @sio.on('*')
    def catch_all(event, data):
        logger.info(f"📨 Event: {event}")
        logger.info(f"📦 Data: {data}")
        events_received.append((event, data))
        
        # Handle specific auth events
        if event in ['loginRequired', 'auth', 'needSetup']:
            logger.info(f"🔐 Auth event: {event}")
            
    try:
        logger.info(f"🔌 Connecting to {base_url}")
        sio.connect(f"{base_url}/socket.io/")
        
        # Wait for initial events
        time.sleep(2)
        
        # Try to login
        username = os.getenv('UPTIME_KUMA_USERNAME', 'admin')
        password = os.getenv('UPTIME_KUMA_PASSWORD', '')
        
        if not password:
            logger.error("❌ No password in environment")
            return
            
        logger.info(f"🔑 Attempting login as: {username}")
        
        auth_data = {
            "username": username,
            "password": password,
            "token": ""
        }
        
        sio.emit("login", auth_data)
        
        # Wait for auth response
        time.sleep(5)
        
        logger.info("📋 All events received:")
        for i, (event, data) in enumerate(events_received):
            logger.info(f"  {i+1}. {event}: {data}")
            
    except Exception as e:
        logger.error(f"💥 Error: {e}")
        
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    # Test both instances
    instances = [
        os.getenv('UPTIME_KUMA_PVE_URL', 'http://192.168.1.123:3001'),
        os.getenv('UPTIME_KUMA_FUNBEDBUG_URL', 'http://192.168.4.220:3001')
    ]
    
    for instance in instances:
        print(f"\n{'='*60}")
        print(f"🔍 Debugging {instance}")
        print('='*60)
        debug_auth(instance)
        time.sleep(2)