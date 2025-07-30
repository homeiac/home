#!/usr/bin/env python3
"""
tests/test_uptime_kuma_client.py

Tests for UptimeKumaClient class
"""

import os
import pytest
from unittest import mock
from unittest.mock import MagicMock, patch

from src.homelab.uptime_kuma_client import UptimeKumaClient, setup_monitoring_for_instance, setup_monitoring_for_all_instances


@pytest.fixture
def mock_uptime_kuma_api():
    """Mock UptimeKumaApi for testing."""
    with mock.patch('src.homelab.uptime_kuma_client.UptimeKumaApi') as mock_api:
        api_instance = MagicMock()
        mock_api.return_value = api_instance
        yield api_instance


@pytest.fixture
def uptime_kuma_client():
    """Create UptimeKumaClient instance for testing."""
    with mock.patch('src.homelab.uptime_kuma_client.UptimeKumaApi'):
        client = UptimeKumaClient("http://test:3001", "testuser", "testpass")
        client.authenticated = True  # Skip actual authentication for tests
        return client


def test_uptime_kuma_client_init():
    """Test UptimeKumaClient initialization."""
    with mock.patch('src.homelab.uptime_kuma_client.UptimeKumaApi') as mock_api:
        client = UptimeKumaClient("http://test:3001", "user", "pass")
        
        assert client.base_url == "http://test:3001"
        assert client.username == "user"  
        assert client.password == "pass"
        assert client.authenticated is False
        mock_api.assert_called_once_with("http://test:3001")


def test_uptime_kuma_client_init_with_env_vars(monkeypatch):
    """Test UptimeKumaClient initialization with environment variables."""
    monkeypatch.setenv("UPTIME_KUMA_USERNAME", "envuser")
    monkeypatch.setenv("UPTIME_KUMA_PASSWORD", "envpass")
    
    with mock.patch('src.homelab.uptime_kuma_client.UptimeKumaApi'):
        client = UptimeKumaClient("http://test:3001")
        
        assert client.username == "envuser"
        assert client.password == "envpass"


def test_connect_success(uptime_kuma_client, mock_uptime_kuma_api):
    """Test successful connection."""
    mock_uptime_kuma_api.login.return_value = None
    
    result = uptime_kuma_client.connect()
    
    assert result is True
    assert uptime_kuma_client.authenticated is True
    mock_uptime_kuma_api.login.assert_called_once_with("testuser", "testpass")


def test_connect_failure(uptime_kuma_client, mock_uptime_kuma_api):
    """Test connection failure."""
    mock_uptime_kuma_api.login.side_effect = Exception("Connection failed")
    
    result = uptime_kuma_client.connect()
    
    assert result is False
    assert uptime_kuma_client.authenticated is False


def test_disconnect(uptime_kuma_client, mock_uptime_kuma_api):
    """Test disconnect."""
    uptime_kuma_client.disconnect()
    
    mock_uptime_kuma_api.disconnect.assert_called_once()
    assert uptime_kuma_client.authenticated is False


def test_monitor_exists_true(uptime_kuma_client, mock_uptime_kuma_api):
    """Test monitor exists returns True when monitor found."""
    mock_uptime_kuma_api.get_monitors.return_value = [
        {"name": "Test Monitor", "id": 1},
        {"name": "Another Monitor", "id": 2}
    ]
    
    result = uptime_kuma_client.monitor_exists("Test Monitor")
    
    assert result is True


def test_monitor_exists_false(uptime_kuma_client, mock_uptime_kuma_api):
    """Test monitor exists returns False when monitor not found."""
    mock_uptime_kuma_api.get_monitors.return_value = [
        {"name": "Other Monitor", "id": 1}
    ]
    
    result = uptime_kuma_client.monitor_exists("Test Monitor")
    
    assert result is False


def test_monitor_exists_not_authenticated():
    """Test monitor exists when not authenticated."""
    with mock.patch('src.homelab.uptime_kuma_client.UptimeKumaApi'):
        client = UptimeKumaClient("http://test:3001", "user", "pass")
        # Don't set authenticated = True
        
        result = client.monitor_exists("Test Monitor")
        
        assert result is False


def test_create_homelab_monitors_not_authenticated():
    """Test create homelab monitors when not authenticated."""
    with mock.patch('src.homelab.uptime_kuma_client.UptimeKumaApi'):
        client = UptimeKumaClient("http://test:3001", "user", "pass")
        # Don't set authenticated = True
        
        result = client.create_homelab_monitors()
        
        assert result == []


def test_create_homelab_monitors_primary_instance(uptime_kuma_client, mock_uptime_kuma_api):
    """Test creating monitors for primary instance."""
    # Mock monitor doesn't exist
    mock_uptime_kuma_api.get_monitors.return_value = []
    
    # Mock successful monitor creation
    mock_uptime_kuma_api.add_monitor.return_value = {"monitorID": 123}
    
    result = uptime_kuma_client.create_homelab_monitors(is_secondary_instance=False)
    
    # Should create all monitors
    assert len(result) == 12  # Total number of monitors configured
    assert all(r["status"] == "created" for r in result)
    assert all("(Secondary)" not in r["name"] for r in result)


def test_create_homelab_monitors_secondary_instance(uptime_kuma_client, mock_uptime_kuma_api):
    """Test creating monitors for secondary instance."""
    # Mock monitor doesn't exist
    mock_uptime_kuma_api.get_monitors.return_value = []
    
    # Mock successful monitor creation
    mock_uptime_kuma_api.add_monitor.return_value = {"monitorID": 123}
    
    result = uptime_kuma_client.create_homelab_monitors(is_secondary_instance=True)
    
    # Should create all monitors with secondary suffix
    assert len(result) == 12
    assert all(r["status"] == "created" for r in result)
    assert all("(Secondary)" in r["name"] for r in result)


def test_create_homelab_monitors_already_exists(uptime_kuma_client, mock_uptime_kuma_api):
    """Test creating monitors when they already exist."""
    # Mock monitor already exists
    mock_uptime_kuma_api.get_monitors.return_value = [
        {"name": "OPNsense Gateway", "id": 1}
    ]
    
    result = uptime_kuma_client.create_homelab_monitors()
    
    # First monitor should be marked as already_exists
    assert result[0]["status"] == "already_exists"
    assert result[0]["name"] == "OPNsense Gateway"


def test_create_homelab_monitors_creation_failure(uptime_kuma_client, mock_uptime_kuma_api):
    """Test monitor creation failure."""
    # Mock monitor doesn't exist
    mock_uptime_kuma_api.get_monitors.return_value = []
    
    # Mock failed monitor creation
    mock_uptime_kuma_api.add_monitor.return_value = {"error": "Creation failed"}
    
    result = uptime_kuma_client.create_homelab_monitors()
    
    # All monitors should fail
    assert all(r["status"] == "failed" for r in result)


def test_context_manager_success(mock_uptime_kuma_api):
    """Test context manager success."""
    with mock.patch('src.homelab.uptime_kuma_client.UptimeKumaApi'):
        with mock.patch.object(UptimeKumaClient, 'connect', return_value=True):
            with mock.patch.object(UptimeKumaClient, 'disconnect') as mock_disconnect:
                with UptimeKumaClient("http://test:3001") as client:
                    assert client is not None
                mock_disconnect.assert_called_once()


def test_context_manager_connection_failure(mock_uptime_kuma_api):
    """Test context manager with connection failure."""
    with mock.patch('src.homelab.uptime_kuma_client.UptimeKumaApi'):
        with mock.patch.object(UptimeKumaClient, 'connect', return_value=False):
            with pytest.raises(RuntimeError, match="Failed to connect to Uptime Kuma"):
                with UptimeKumaClient("http://test:3001") as client:
                    pass


def test_setup_monitoring_for_instance_success():
    """Test setup monitoring for single instance success."""
    with mock.patch.object(UptimeKumaClient, '__enter__') as mock_enter:
        with mock.patch.object(UptimeKumaClient, '__exit__'):
            mock_client = MagicMock()
            mock_client.create_homelab_monitors.return_value = [
                {"name": "Test Monitor", "status": "created", "monitor_id": 1}
            ]
            mock_enter.return_value = mock_client
            
            result = setup_monitoring_for_instance("http://test:3001")
            
            assert len(result) == 1
            assert result[0]["status"] == "created"


def test_setup_monitoring_for_instance_secondary():
    """Test setup monitoring for secondary instance."""
    with mock.patch.object(UptimeKumaClient, '__enter__') as mock_enter:
        with mock.patch.object(UptimeKumaClient, '__exit__'):
            mock_client = MagicMock()
            mock_client.create_homelab_monitors.return_value = []
            mock_enter.return_value = mock_client
            
            setup_monitoring_for_instance("http://test:3001", is_secondary=True)
            
            # Verify secondary flag was passed
            mock_client.create_homelab_monitors.assert_called_once_with(is_secondary_instance=True)


def test_setup_monitoring_for_instance_failure():
    """Test setup monitoring failure."""
    with mock.patch.object(UptimeKumaClient, '__enter__', side_effect=Exception("Connection failed")):
        result = setup_monitoring_for_instance("http://test:3001")
        
        assert result == []


def test_setup_monitoring_for_all_instances_success(monkeypatch):
    """Test setup monitoring for all instances."""
    monkeypatch.setenv("UPTIME_KUMA_PVE_URL", "http://pve:3001")
    monkeypatch.setenv("UPTIME_KUMA_FUNBEDBUG_URL", "http://funbedbug:3001")
    
    with mock.patch('src.homelab.uptime_kuma_client.setup_monitoring_for_instance') as mock_setup:
        mock_setup.return_value = [{"name": "Test", "status": "created"}]
        
        result = setup_monitoring_for_all_instances()
        
        assert len(result) == 2
        assert "pve" in result
        assert "fun-bedbug" in result
        
        # Verify secondary flag passed correctly
        calls = mock_setup.call_args_list
        assert calls[0][0] == ("http://pve:3001",)
        assert calls[0][1] == {"is_secondary": False}
        assert calls[1][0] == ("http://funbedbug:3001",)
        assert calls[1][1] == {"is_secondary": True}


def test_setup_monitoring_for_all_instances_no_env_vars(monkeypatch):
    """Test setup monitoring with no environment variables."""
    # Clear any existing env vars
    monkeypatch.delenv("UPTIME_KUMA_PVE_URL", raising=False)
    monkeypatch.delenv("UPTIME_KUMA_FUNBEDBUG_URL", raising=False)
    
    result = setup_monitoring_for_all_instances()
    
    assert result == {}


def test_setup_monitoring_for_all_instances_partial_env_vars(monkeypatch):
    """Test setup monitoring with only one instance configured."""
    monkeypatch.setenv("UPTIME_KUMA_PVE_URL", "http://pve:3001")
    monkeypatch.delenv("UPTIME_KUMA_FUNBEDBUG_URL", raising=False)
    
    with mock.patch('src.homelab.uptime_kuma_client.setup_monitoring_for_instance') as mock_setup:
        mock_setup.return_value = [{"name": "Test", "status": "created"}]
        
        result = setup_monitoring_for_all_instances()
        
        assert len(result) == 1
        assert "pve" in result
        assert "fun-bedbug" not in result