#!/usr/bin/env python3
"""
tests/test_infrastructure_orchestrator.py

Comprehensive unit tests for InfrastructureOrchestrator with 100% coverage.
Tests all MAAS registration, monitoring integration, and orchestration logic.
"""

import json
import os
import subprocess
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

from homelab.infrastructure_orchestrator import InfrastructureOrchestrator


class TestInfrastructureOrchestrator:
    """Test InfrastructureOrchestrator class."""

    @pytest.fixture
    def mock_env(self, monkeypatch):
        """Set up test environment variables."""
        monkeypatch.setenv("MAAS_USER", "testuser")
        monkeypatch.setenv("MAAS_PASSWORD", "testpass")
        monkeypatch.setenv("CRITICAL_SERVICE_UPTIME_KUMA_PVE_NAME", "test-uptime-pve")
        monkeypatch.setenv("CRITICAL_SERVICE_UPTIME_KUMA_PVE_MAC", "AA:BB:CC:DD:EE:FF")
        monkeypatch.setenv("CRITICAL_SERVICE_UPTIME_KUMA_PVE_HOST_NODE", "test-pve")
        monkeypatch.setenv("CRITICAL_SERVICE_UPTIME_KUMA_PVE_LXC_ID", "100")
        monkeypatch.setenv("CRITICAL_SERVICE_UPTIME_KUMA_PVE_CURRENT_IP", "192.168.1.100")
        monkeypatch.setenv("CRITICAL_SERVICE_UPTIME_KUMA_PVE_PORT", "3001")
        monkeypatch.setenv("CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_NAME", "test-uptime-bedbug")
        monkeypatch.setenv("CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_MAC", "11:22:33:44:55:66")
        monkeypatch.setenv("CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_HOST_NODE", "test-bedbug")
        monkeypatch.setenv("CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_LXC_ID", "101")
        monkeypatch.setenv("CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_CURRENT_IP", "192.168.1.101")
        monkeypatch.setenv("CRITICAL_SERVICE_UPTIME_KUMA_FUN_BEDBUG_PORT", "3001")

    @pytest.fixture
    def orchestrator(self, mock_env):
        """Create InfrastructureOrchestrator instance for testing."""
        return InfrastructureOrchestrator()

    def test_init(self, orchestrator, mock_env):
        """Test InfrastructureOrchestrator initialization."""
        assert orchestrator.maas_host == "192.168.4.53"
        assert orchestrator.maas_user == "testuser"
        assert orchestrator.maas_password == "testpass"
        assert len(orchestrator.critical_services) == 2
        
        # Check first service
        service1 = orchestrator.critical_services[0]
        assert service1["name"] == "test-uptime-pve"
        assert service1["mac"] == "AA:BB:CC:DD:EE:FF"
        assert service1["host_node"] == "test-pve"
        assert service1["type"] == "uptime_kuma"
        
        # Check second service
        service2 = orchestrator.critical_services[1]
        assert service2["name"] == "test-uptime-bedbug"
        assert service2["mac"] == "11:22:33:44:55:66"
        assert service2["host_node"] == "test-bedbug"
        assert service2["type"] == "uptime_kuma"

    def test_load_critical_services_from_env_defaults(self, monkeypatch):
        """Test loading critical services with default values when env vars not set."""
        # Clear all CRITICAL_SERVICE env vars
        for var in os.environ.copy():
            if var.startswith("CRITICAL_SERVICE_"):
                monkeypatch.delenv(var, raising=False)
        
        monkeypatch.setenv("MAAS_USER", "testuser")
        monkeypatch.setenv("MAAS_PASSWORD", "testpass")
        
        orchestrator = InfrastructureOrchestrator()
        
        assert len(orchestrator.critical_services) == 2
        assert orchestrator.critical_services[0]["name"] == "uptime-kuma-pve"
        assert orchestrator.critical_services[0]["mac"] == "BC:24:11:B3:D0:40"
        assert orchestrator.critical_services[1]["name"] == "uptime-kuma-fun-bedbug"
        assert orchestrator.critical_services[1]["mac"] == "BC:24:11:5F:CD:81"

    @patch('subprocess.run')
    def test_run_maas_command_success(self, mock_subprocess, orchestrator):
        """Test successful MAAS command execution."""
        # Mock successful command execution
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"hostname": "test-host", "system_id": "abc123"}'
        mock_subprocess.return_value = mock_result
        
        result = orchestrator._run_maas_command("maas admin devices read")
        
        expected_cmd = [
            "ssh", "testuser@192.168.4.53",
            "echo 'testpass' | maas admin devices read"
        ]
        mock_subprocess.assert_called_once_with(
            expected_cmd, capture_output=True, text=True, timeout=30
        )
        
        assert result == {"hostname": "test-host", "system_id": "abc123"}

    @patch('subprocess.run')
    def test_run_maas_command_failure(self, mock_subprocess, orchestrator):
        """Test MAAS command execution failure."""
        # Mock failed command execution
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Command failed"
        mock_subprocess.return_value = mock_result
        
        result = orchestrator._run_maas_command("maas admin devices read")
        
        assert result == {}

    @patch('subprocess.run')
    def test_run_maas_command_exception(self, mock_subprocess, orchestrator):
        """Test MAAS command execution with exception."""
        # Mock exception during command execution
        mock_subprocess.side_effect = subprocess.TimeoutExpired("ssh", 30)
        
        result = orchestrator._run_maas_command("maas admin devices read")
        
        assert result == {}

    @patch('subprocess.run')
    def test_run_maas_command_empty_output(self, mock_subprocess, orchestrator):
        """Test MAAS command with empty output."""
        # Mock successful command with empty output
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_subprocess.return_value = mock_result
        
        result = orchestrator._run_maas_command("maas admin devices read")
        
        assert result == {}

    @patch('subprocess.run')
    def test_get_vm_mac_address_success(self, mock_subprocess, orchestrator):
        """Test successful VM MAC address retrieval."""
        # Mock successful MAC address retrieval
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "aa:bb:cc:dd:ee:ff"
        mock_subprocess.return_value = mock_result
        
        mac = orchestrator._get_vm_mac_address("test-node", "test-vm")
        
        expected_cmd = [
            "ssh", "root@test-node.maas",
            "qm config $(qm list | grep 'test-vm' | awk '{print $1}') | grep 'net0:' | grep -o 'macaddr=[^,]*' | cut -d'=' -f2"
        ]
        mock_subprocess.assert_called_once_with(
            expected_cmd, capture_output=True, text=True, timeout=15
        )
        
        assert mac == "AA:BB:CC:DD:EE:FF"

    @patch('subprocess.run')
    def test_get_vm_mac_address_failure(self, mock_subprocess, orchestrator):
        """Test VM MAC address retrieval failure."""
        # Mock failed MAC address retrieval
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_subprocess.return_value = mock_result
        
        mac = orchestrator._get_vm_mac_address("test-node", "test-vm")
        
        assert mac is None

    @patch('subprocess.run')
    def test_get_vm_mac_address_exception(self, mock_subprocess, orchestrator):
        """Test VM MAC address retrieval with exception."""
        # Mock exception during MAC address retrieval
        mock_subprocess.side_effect = Exception("SSH connection failed")
        
        mac = orchestrator._get_vm_mac_address("test-node", "test-vm")
        
        assert mac is None

    def test_check_maas_device_exists_true(self, orchestrator):
        """Test checking if device exists in MAAS (exists)."""
        with patch.object(orchestrator, '_run_maas_command') as mock_maas:
            mock_maas.return_value = [
                {"hostname": "existing-device", "system_id": "abc123"},
                {"hostname": "test-host", "system_id": "def456"}
            ]
            
            exists = orchestrator._check_maas_device_exists("test-host")
            
            assert exists is True
            mock_maas.assert_called_once_with("maas admin devices read")

    def test_check_maas_device_exists_false(self, orchestrator):
        """Test checking if device exists in MAAS (does not exist)."""
        with patch.object(orchestrator, '_run_maas_command') as mock_maas:
            mock_maas.return_value = [
                {"hostname": "existing-device", "system_id": "abc123"}
            ]
            
            exists = orchestrator._check_maas_device_exists("test-host")
            
            assert exists is False

    def test_check_maas_device_exists_empty_response(self, orchestrator):
        """Test checking if device exists when MAAS returns empty response."""
        with patch.object(orchestrator, '_run_maas_command') as mock_maas:
            mock_maas.return_value = {}
            
            exists = orchestrator._check_maas_device_exists("test-host")
            
            assert exists is False

    def test_register_device_in_maas_already_exists(self, orchestrator):
        """Test registering device that already exists in MAAS."""
        with patch.object(orchestrator, '_check_maas_device_exists') as mock_check:
            mock_check.return_value = True
            
            result = orchestrator._register_device_in_maas("test-host", "AA:BB:CC:DD:EE:FF")
            
            assert result is True
            mock_check.assert_called_once_with("test-host")

    def test_register_device_in_maas_success(self, orchestrator):
        """Test successful device registration in MAAS."""
        with patch.object(orchestrator, '_check_maas_device_exists') as mock_check, \
             patch.object(orchestrator, '_run_maas_command') as mock_maas:
            
            mock_check.return_value = False
            mock_maas.return_value = {"hostname": "test-host", "system_id": "abc123"}
            
            result = orchestrator._register_device_in_maas("test-host", "AA:BB:CC:DD:EE:FF", "Test device")
            
            assert result is True
            mock_check.assert_called_once_with("test-host")
            
            # Check device creation command
            expected_create_cmd = (
                "maas admin devices create "
                "hostname=test-host "
                "mac_addresses=AA:BB:CC:DD:EE:FF "
                "domain=0"
            )
            
            # Check description update command
            expected_desc_cmd = "maas admin device update abc123 description='Test device'"
            
            assert mock_maas.call_count == 2
            mock_maas.assert_any_call(expected_create_cmd)
            mock_maas.assert_any_call(expected_desc_cmd)

    def test_register_device_in_maas_failure(self, orchestrator):
        """Test failed device registration in MAAS."""
        with patch.object(orchestrator, '_check_maas_device_exists') as mock_check, \
             patch.object(orchestrator, '_run_maas_command') as mock_maas:
            
            mock_check.return_value = False
            mock_maas.return_value = {"hostname": "different-host"}  # Wrong hostname
            
            result = orchestrator._register_device_in_maas("test-host", "AA:BB:CC:DD:EE:FF")
            
            assert result is False

    @patch('homelab.infrastructure_orchestrator.VMManager')
    @patch('homelab.infrastructure_orchestrator.Config')
    def test_step1_provision_k3s_vms_success(self, mock_config, mock_vm_manager, orchestrator):
        """Test successful K3s VM provisioning."""
        # Mock configuration
        mock_config.get_nodes.return_value = [
            {"name": "test-node1"},
            {"name": "test-node2"}
        ]
        mock_config.VM_NAME_TEMPLATE = "k3s-vm-{node}"
        
        # Mock VMManager
        mock_vm_manager.create_or_update_vm.return_value = None
        
        result = orchestrator.step1_provision_k3s_vms()
        
        assert result["status"] == "success"
        assert len(result["k3s_vms"]) == 2
        assert result["k3s_vms"][0]["name"] == "k3s-vm-test-node1"
        assert result["k3s_vms"][1]["name"] == "k3s-vm-test-node2"
        
        mock_vm_manager.create_or_update_vm.assert_called_once()

    @patch('homelab.infrastructure_orchestrator.VMManager')
    def test_step1_provision_k3s_vms_failure(self, mock_vm_manager, orchestrator):
        """Test failed K3s VM provisioning."""
        # Mock VMManager to raise exception
        mock_vm_manager.create_or_update_vm.side_effect = Exception("VM creation failed")
        
        result = orchestrator.step1_provision_k3s_vms()
        
        assert result["status"] == "failed"
        assert result["error"] == "VM creation failed"

    def test_step2_register_k3s_vms_in_maas_success(self, orchestrator):
        """Test successful K3s VM registration in MAAS."""
        k3s_vms = [
            {"name": "k3s-vm-node1", "node": "node1", "hostname": "k3s-vm-node1"},
            {"name": "k3s-vm-node2", "node": "node2", "hostname": "k3s-vm-node2"}
        ]
        
        with patch.object(orchestrator, '_get_vm_mac_address') as mock_get_mac, \
             patch.object(orchestrator, '_register_device_in_maas') as mock_register:
            
            mock_get_mac.side_effect = ["AA:BB:CC:DD:EE:F1", "AA:BB:CC:DD:EE:F2"]
            mock_register.side_effect = [True, True]
            
            result = orchestrator.step2_register_k3s_vms_in_maas(k3s_vms)
            
            assert result["status"] == "success"
            assert result["registered"] == 2
            assert result["failed"] == 0
            
            # Check MAC address retrieval calls
            mock_get_mac.assert_any_call("node1", "k3s-vm-node1")
            mock_get_mac.assert_any_call("node2", "k3s-vm-node2")
            
            # Check device registration calls
            mock_register.assert_any_call("k3s-vm-node1", "AA:BB:CC:DD:EE:F1", "K3s VM on node1 node (auto-registered)")
            mock_register.assert_any_call("k3s-vm-node2", "AA:BB:CC:DD:EE:F2", "K3s VM on node2 node (auto-registered)")

    def test_step2_register_k3s_vms_in_maas_partial_failure(self, orchestrator):
        """Test K3s VM registration with some failures."""
        k3s_vms = [
            {"name": "k3s-vm-node1", "node": "node1", "hostname": "k3s-vm-node1"},
            {"name": "k3s-vm-node2", "node": "node2", "hostname": "k3s-vm-node2"}
        ]
        
        with patch.object(orchestrator, '_get_vm_mac_address') as mock_get_mac, \
             patch.object(orchestrator, '_register_device_in_maas') as mock_register:
            
            mock_get_mac.side_effect = [None, "AA:BB:CC:DD:EE:F2"]  # First VM fails to get MAC
            mock_register.return_value = True
            
            result = orchestrator.step2_register_k3s_vms_in_maas(k3s_vms)
            
            assert result["status"] == "success"
            assert result["registered"] == 1
            assert result["failed"] == 1

    def test_step2_register_k3s_vms_in_maas_registration_failure(self, orchestrator):
        """Test K3s VM registration when MAAS registration fails."""
        k3s_vms = [
            {"name": "k3s-vm-node1", "node": "node1", "hostname": "k3s-vm-node1"}
        ]
        
        with patch.object(orchestrator, '_get_vm_mac_address') as mock_get_mac, \
             patch.object(orchestrator, '_register_device_in_maas') as mock_register:
            
            mock_get_mac.return_value = "AA:BB:CC:DD:EE:F1"
            mock_register.return_value = False  # Registration fails
            
            result = orchestrator.step2_register_k3s_vms_in_maas(k3s_vms)
            
            assert result["status"] == "success"
            assert result["registered"] == 0
            assert result["failed"] == 1

    def test_step3_register_critical_services_in_maas_success(self, orchestrator):
        """Test successful critical services registration in MAAS."""
        with patch.object(orchestrator, '_register_device_in_maas') as mock_register:
            mock_register.return_value = True
            
            result = orchestrator.step3_register_critical_services_in_maas()
            
            assert result["status"] == "success"
            assert result["registered"] == 2
            assert result["failed"] == 0
            
            # Check registration calls for both services
            mock_register.assert_any_call("test-uptime-pve", "AA:BB:CC:DD:EE:FF", "Uptime_Kuma service on test-pve (auto-registered)")
            mock_register.assert_any_call("test-uptime-bedbug", "11:22:33:44:55:66", "Uptime_Kuma service on test-bedbug (auto-registered)")

    def test_step3_register_critical_services_in_maas_failure(self, orchestrator):
        """Test critical services registration with failures."""
        with patch.object(orchestrator, '_register_device_in_maas') as mock_register:
            mock_register.side_effect = [False, True]  # First service fails
            
            result = orchestrator.step3_register_critical_services_in_maas()
            
            assert result["status"] == "success"
            assert result["registered"] == 1
            assert result["failed"] == 1

    @patch('homelab.infrastructure_orchestrator.UptimeKumaClient')
    def test_step4_update_monitoring_success(self, mock_uptime_client, orchestrator):
        """Test successful monitoring configuration update."""
        # Mock UptimeKumaClient
        mock_client_instance = MagicMock()
        mock_uptime_client.return_value = mock_client_instance
        mock_client_instance.connect.return_value = True
        mock_client_instance.create_homelab_monitors.return_value = [
            {"status": "created"},
            {"status": "updated"},
            {"status": "up_to_date"}
        ]
        
        result = orchestrator.step4_update_monitoring()
        
        assert result["status"] == "success"
        assert result["updated"] == 2  # Both instances
        assert result["failed"] == 0
        
        # Check client creation and method calls
        expected_urls = [
            "http://test-uptime-pve.maas:3001",
            "http://test-uptime-bedbug.maas:3001"
        ]
        
        assert mock_uptime_client.call_count == 2
        for url in expected_urls:
            mock_uptime_client.assert_any_call(url)
        
        assert mock_client_instance.connect.call_count == 2
        assert mock_client_instance.create_homelab_monitors.call_count == 2
        assert mock_client_instance.disconnect.call_count == 2

    @patch('homelab.infrastructure_orchestrator.UptimeKumaClient')
    def test_step4_update_monitoring_connection_failure(self, mock_uptime_client, orchestrator):
        """Test monitoring update with connection failures."""
        # Mock UptimeKumaClient connection failure
        mock_client_instance = MagicMock()
        mock_uptime_client.return_value = mock_client_instance
        mock_client_instance.connect.return_value = False
        
        result = orchestrator.step4_update_monitoring()
        
        assert result["status"] == "success"
        assert result["updated"] == 0
        assert result["failed"] == 2

    @patch('homelab.infrastructure_orchestrator.UptimeKumaClient')
    def test_step4_update_monitoring_exception(self, mock_uptime_client, orchestrator):
        """Test monitoring update with exceptions."""
        # Mock UptimeKumaClient to raise exception
        mock_uptime_client.side_effect = Exception("Connection error")
        
        result = orchestrator.step4_update_monitoring()
        
        assert result["status"] == "success"
        assert result["updated"] == 0
        assert result["failed"] == 2

    def test_step5_generate_documentation(self, orchestrator):
        """Test documentation generation (placeholder implementation)."""
        result = orchestrator.step5_generate_documentation()
        
        assert result["status"] == "success"
        assert result["generated_docs"] == 0

    @patch.object(InfrastructureOrchestrator, 'step1_provision_k3s_vms')
    @patch.object(InfrastructureOrchestrator, 'step2_register_k3s_vms_in_maas')
    @patch.object(InfrastructureOrchestrator, 'step3_register_critical_services_in_maas')
    @patch.object(InfrastructureOrchestrator, 'step4_update_monitoring')
    @patch.object(InfrastructureOrchestrator, 'step5_generate_documentation')
    def test_orchestrate_success(self, mock_step5, mock_step4, mock_step3, mock_step2, mock_step1, orchestrator):
        """Test successful full orchestration."""
        # Mock all steps to succeed
        mock_step1.return_value = {
            "status": "success",
            "k3s_vms": [{"name": "test-vm", "node": "test-node", "hostname": "test-vm"}]
        }
        mock_step2.return_value = {"status": "success", "registered": 1, "failed": 0}
        mock_step3.return_value = {"status": "success", "registered": 2, "failed": 0}
        mock_step4.return_value = {"status": "success", "updated": 2, "failed": 0}
        mock_step5.return_value = {"status": "success", "generated_docs": 1}
        
        result = orchestrator.orchestrate()
        
        assert result["orchestration_summary"]["status"] == "success"
        assert result["orchestration_summary"]["total_steps_completed"] == 5
        assert "elapsed_time_seconds" in result["orchestration_summary"]
        
        # Verify all steps were called
        mock_step1.assert_called_once()
        mock_step2.assert_called_once_with([{"name": "test-vm", "node": "test-node", "hostname": "test-vm"}])
        mock_step3.assert_called_once()
        mock_step4.assert_called_once()
        mock_step5.assert_called_once()

    @patch.object(InfrastructureOrchestrator, 'step1_provision_k3s_vms')
    def test_orchestrate_step1_failure(self, mock_step1, orchestrator):
        """Test orchestration with step 1 failure."""
        # Mock step 1 to fail
        mock_step1.return_value = {"status": "failed", "error": "VM creation failed"}
        
        result = orchestrator.orchestrate()
        
        assert result["step1_k3s_provisioning"]["status"] == "failed"
        assert "step2_k3s_maas_registration" not in result  # Should stop after step 1
        
        mock_step1.assert_called_once()

    @patch.object(InfrastructureOrchestrator, 'step1_provision_k3s_vms')
    def test_orchestrate_exception(self, mock_step1, orchestrator):
        """Test orchestration with unexpected exception."""
        # Mock step 1 to raise exception
        mock_step1.side_effect = Exception("Unexpected error")
        
        result = orchestrator.orchestrate()
        
        assert result["orchestration_summary"]["status"] == "failed"
        assert result["orchestration_summary"]["error"] == "Unexpected error"
        assert "elapsed_time_seconds" in result["orchestration_summary"]


class TestOrchestratorMain:
    """Test main() function in infrastructure_orchestrator.py."""

    @patch('homelab.infrastructure_orchestrator.sys.argv', ['orchestrate.py', '--dry-run'])
    @patch('homelab.infrastructure_orchestrator.logger')
    def test_main_dry_run(self, mock_logger):
        """Test main function with dry-run argument."""
        from homelab.infrastructure_orchestrator import main
        
        result = main()
        
        assert result is None
        mock_logger.info.assert_called_once_with("🔍 DRY RUN MODE - would execute orchestration")

    @patch('homelab.infrastructure_orchestrator.sys.argv', ['orchestrate.py'])
    @patch('homelab.infrastructure_orchestrator.InfrastructureOrchestrator')
    def test_main_success(self, mock_orchestrator_class):
        """Test main function with successful orchestration."""
        from homelab.infrastructure_orchestrator import main
        
        # Mock successful orchestration
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.orchestrate.return_value = {
            "orchestration_summary": {"status": "success"}
        }
        
        result = main()
        
        assert result is None
        mock_orchestrator_class.assert_called_once()
        mock_orchestrator.orchestrate.assert_called_once()

    @patch('homelab.infrastructure_orchestrator.sys.argv', ['orchestrate.py'])
    @patch('homelab.infrastructure_orchestrator.InfrastructureOrchestrator')
    @patch('homelab.infrastructure_orchestrator.sys.exit')
    def test_main_failure(self, mock_exit, mock_orchestrator_class):
        """Test main function with failed orchestration."""
        from homelab.infrastructure_orchestrator import main
        
        # Mock failed orchestration
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.orchestrate.return_value = {
            "orchestration_summary": {"status": "failed"}
        }
        
        main()
        
        mock_exit.assert_called_once_with(1)
        mock_orchestrator_class.assert_called_once()
        mock_orchestrator.orchestrate.assert_called_once()

    @patch('homelab.infrastructure_orchestrator.sys.argv', ['orchestrate.py'])
    @patch('homelab.infrastructure_orchestrator.InfrastructureOrchestrator')
    @patch('homelab.infrastructure_orchestrator.sys.exit')
    def test_main_no_summary(self, mock_exit, mock_orchestrator_class):
        """Test main function with missing orchestration summary."""
        from homelab.infrastructure_orchestrator import main
        
        # Mock orchestration with no summary
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.orchestrate.return_value = {}
        
        main()
        
        mock_exit.assert_called_once_with(1)
        mock_orchestrator_class.assert_called_once()
        mock_orchestrator.orchestrate.assert_called_once()