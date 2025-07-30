#!/usr/bin/env python3
"""
Simple test script for Uptime Kuma Socket.io connection
"""

import logging
import socketio
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_uptime_kuma_connection(base_url: str):
    """Test basic connection to Uptime Kuma."""
    
    sio = socketio.Client()
    connected = False
    authenticated = False
    
    @sio.event
    def connect():
        nonlocal connected
        logger.info(f"Connected to {base_url}")
        connected = True
        
    @sio.event  
    def disconnect():
        logger.info("Disconnected")
        
    @sio.event
    def info(data):
        logger.info(f"Server info: {data}")
        
    try:
        # Connect to Socket.io
        logger.info(f"Attempting to connect to {base_url}")
        sio.connect(f"{base_url}/socket.io/")
        
        # Wait a bit for connection
        time.sleep(2)
        
        if connected:
            logger.info("✅ Connection successful!")
            
            # Try to get server info (this usually works without auth)
            sio.emit('info')
            time.sleep(1)
            
        else:
            logger.error("❌ Connection failed")
            
    except Exception as e:
        logger.error(f"Connection error: {e}")
        
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    # Test both discovered instances
    instances = [
        "http://192.168.1.123:3001",
        "http://192.168.4.220:3001"
    ]
    
    for instance in instances:
        print(f"\n=== Testing {instance} ===")
        test_uptime_kuma_connection(instance)