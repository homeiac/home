#!/usr/bin/env python3
"""
Debug the correct monitor format by examining successful creation
"""

import logging
import socketio
import time
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def debug_monitor_creation(base_url: str):
    """Debug monitor creation with minimal config."""
    
    sio = socketio.Client()
    login_response = None
    add_response = None
    
    @sio.event
    def connect():
        logger.info(f"Connected to {base_url}")
        
    @sio.event 
    def disconnect():
        logger.info("Disconnected")
        
    @sio.on('*')
    def catch_all(event, data):
        logger.debug(f"Event: {event}, Data: {data}")
        
    def login_callback(response):
        nonlocal login_response
        login_response = response
        
    def add_callback(response):
        nonlocal add_response
        logger.info(f"Add monitor response: {response}")
        add_response = response
        
    try:
        # Connect and login
        sio.connect(f"{base_url}/socket.io/")
        time.sleep(1)
        
        username = os.getenv('UPTIME_KUMA_USERNAME')
        password = os.getenv('UPTIME_KUMA_PASSWORD')
        
        auth_data = {
            "username": username,
            "password": password,
            "token": ""
        }
        
        sio.emit("login", auth_data, callback=login_callback)
        
        # Wait for login
        timeout = 10
        start = time.time()
        while login_response is None and (time.time() - start) < timeout:
            time.sleep(0.5)
            
        if not login_response or not login_response.get('ok'):
            logger.error("Login failed")
            return
            
        logger.info("✅ Login successful")
        
        # Try very minimal monitor config
        minimal_config = {
            "name": "Test - Minimal Google",
            "type": "ping",
            "hostname": "8.8.8.8"
        }
        
        logger.info(f"Testing minimal config: {minimal_config}")
        sio.emit("add", minimal_config, callback=add_callback)
        
        # Wait for response
        start = time.time()
        while add_response is None and (time.time() - start) < timeout:
            time.sleep(0.5)
            
        if add_response:
            if add_response.get('ok'):
                logger.info(f"✅ Minimal config worked: {add_response}")
            else:
                logger.error(f"❌ Minimal config failed: {add_response}")
        else:
            logger.error("❌ No response to add monitor")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    pve_url = "http://192.168.1.123:3001"
    print(f"Testing minimal monitor config at {pve_url}")
    debug_monitor_creation(pve_url)