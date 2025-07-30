#!/usr/bin/env python3
"""
Test login with callback to see exact response
"""

import logging
import socketio
import time
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_login_with_callback(base_url: str):
    """Test login with explicit callback handling."""
    
    sio = socketio.Client()
    login_response = None
    
    @sio.event
    def connect():
        logger.info(f"✅ Connected to {base_url}")
        
    @sio.event 
    def disconnect():
        logger.info("Disconnected")
        
    @sio.on('*')
    def catch_all(event, data):
        logger.info(f"📨 Event: {event}, Data: {data}")
        
    def login_callback(response):
        nonlocal login_response
        logger.info(f"🔐 Login callback: {response}")
        login_response = response
        
    try:
        # Connect
        sio.connect(f"{base_url}/socket.io/")
        time.sleep(1)
        
        # Get credentials
        username = os.getenv('UPTIME_KUMA_USERNAME', 'admin')
        password = os.getenv('UPTIME_KUMA_PASSWORD', '')
        
        logger.info(f"🔑 Logging in as: {username}")
        logger.info(f"🔒 Password length: {len(password)}")
        
        # Try login with callback
        auth_data = {
            "username": username,
            "password": password,
            "token": ""
        }
        
        sio.emit("login", auth_data, callback=login_callback)
        
        # Wait for response
        timeout = 10
        start = time.time()
        while login_response is None and (time.time() - start) < timeout:
            time.sleep(0.5)
            
        if login_response:
            logger.info(f"✅ Login response received: {login_response}")
            
            # If successful, try to get monitor list
            if login_response.get('ok'):
                logger.info("🎯 Login successful, requesting monitor list...")
                sio.emit("getMonitorList")
                time.sleep(2)
            else:
                logger.error(f"❌ Login failed: {login_response.get('msg', 'Unknown error')}")
        else:
            logger.error("❌ No login response received")
            
    except Exception as e:
        logger.error(f"💥 Error: {e}")
        
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    # Test first instance only
    instance = os.getenv('UPTIME_KUMA_PVE_URL', 'http://192.168.1.123:3001')
    
    print("🧪 Testing authentication with callback...")
    print(f"Instance: {instance}")
    print(f"Username: {os.getenv('UPTIME_KUMA_USERNAME', 'admin')}")
    print(f"Password: {'*' * len(os.getenv('UPTIME_KUMA_PASSWORD', ''))}")
    print()
    
    test_login_with_callback(instance)