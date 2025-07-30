#!/usr/bin/env python3
"""
Simple working version of UptimeKumaClient for testing
"""

import logging
import socketio
import time
import json
import os
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleUptimeKumaClient:
    """Simple client for testing Uptime Kuma Socket.io API."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.socket = socketio.Client()
        self.authenticated = False
        self.monitors = {}
        self._setup_handlers()
    
    def _setup_handlers(self):
        @self.socket.event
        def connect():
            logger.info(f"Connected to {self.base_url}")
            
        @self.socket.event
        def disconnect():
            logger.info("Disconnected")
            self.authenticated = False
            
        @self.socket.event
        def info(data):
            logger.info(f"Server info: {data}")
            
        @self.socket.event
        def monitorList(data):
            logger.info(f"Received monitor list: {len(data)} monitors")
            self.monitors = data
            
        @self.socket.event
        def result(data):
            logger.info(f"Operation result: {data}")
            
        @self.socket.on('*')
        def catch_all(event, data):
            logger.debug(f"Event: {event}, Data: {data}")
    
    def connect(self):
        try:
            self.socket.connect(f"{self.base_url}/socket.io/")
            time.sleep(1)
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def login(self, username: str, password: str):
        """Attempt to login with username/password."""
        if not self.socket.connected:
            logger.error("Not connected")
            return False
            
        try:
            auth_data = {
                "username": username,
                "password": password,
                "token": ""
            }
            
            logger.info(f"Attempting login as {username}")
            self.socket.emit("login", auth_data)
            
            # Wait for response
            time.sleep(3)
            
            # Check if we can get monitor list (indicates success)
            self.socket.emit("getMonitorList")
            time.sleep(2)
            
            if self.monitors:
                logger.info("✅ Login successful - received monitor list")
                self.authenticated = True
                return True
            else:
                logger.warning("⚠️ Login status unclear - no monitor list received")
                return False
                
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def list_monitors(self):
        """List current monitors."""
        if not self.authenticated:
            logger.error("Not authenticated")
            return
            
        print("\nCurrent monitors:")
        for monitor_id, monitor_data in self.monitors.items():
            name = monitor_data.get('name', 'Unknown')
            type_val = monitor_data.get('type', 'Unknown')
            url = monitor_data.get('url', monitor_data.get('hostname', 'N/A'))
            print(f"  ID {monitor_id}: {name} ({type_val}) - {url}")
    
    def add_simple_monitor(self, name: str, url: str):
        """Add a simple HTTP monitor for testing."""
        if not self.authenticated:
            logger.error("Not authenticated")
            return False
            
        monitor_config = {
            "name": name,
            "type": "http",
            "url": url,
            "interval": 300,
            "maxretries": 2,
            "retryInterval": 60,
            "method": "GET"
        }
        
        logger.info(f"Adding monitor: {name}")
        self.socket.emit("add", monitor_config)
        time.sleep(3)
        
        # Refresh monitor list
        self.socket.emit("getMonitorList") 
        time.sleep(2)
        
        # Check if monitor was added
        for monitor_data in self.monitors.values():
            if monitor_data.get('name') == name:
                logger.info(f"✅ Monitor '{name}' added successfully")
                return True
                
        logger.error(f"❌ Failed to add monitor '{name}'")
        return False
    
    def disconnect(self):
        if self.socket.connected:
            self.socket.disconnect()

def test_client():
    """Test the client with both instances using .env credentials."""
    
    # Get credentials from environment
    username = os.getenv('UPTIME_KUMA_USERNAME', 'admin')
    password = os.getenv('UPTIME_KUMA_PASSWORD')
    
    if not password:
        print("❌ UPTIME_KUMA_PASSWORD not set in .env file")
        return
    
    # Get instance URLs from environment or use defaults
    instances = [
        os.getenv('UPTIME_KUMA_PVE_URL', 'http://192.168.1.123:3001'),
        os.getenv('UPTIME_KUMA_FUNBEDBUG_URL', 'http://192.168.4.220:3001')
    ]
    
    print(f"Using credentials: {username} / {'*' * len(password)}")
    print(f"Testing instances: {instances}")
    
    for base_url in instances:
        print(f"\n{'='*50}")
        print(f"Testing {base_url}")
        print('='*50)
        
        client = SimpleUptimeKumaClient(base_url)
        
        if not client.connect():
            print("❌ Connection failed")
            continue
            
        print("✅ Connected successfully")
            
        if client.login(username, password):
            print("✅ Login successful")
            
            # List existing monitors
            client.list_monitors()
            
            # Test adding a simple monitor
            test_monitor_name = "Test - Google"
            
            # Check if test monitor already exists
            exists = any(m.get('name') == test_monitor_name for m in client.monitors.values())
            
            if not exists:
                print(f"\nAdding test monitor: {test_monitor_name}")
                if client.add_simple_monitor(test_monitor_name, "https://google.com"):
                    print("✅ Test monitor added")
                    
                    # List monitors again to see the new one
                    client.list_monitors()
                else:
                    print("❌ Failed to add test monitor")
            else:
                print(f"ℹ️ Test monitor '{test_monitor_name}' already exists")
        else:
            print("❌ Login failed")
            
        client.disconnect()
        print(f"✅ Disconnected from {base_url}")

if __name__ == "__main__":
    test_client()