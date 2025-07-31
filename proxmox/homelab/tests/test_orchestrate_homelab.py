#!/usr/bin/env python3
"""
tests/test_orchestrate_homelab.py

Unit tests for orchestrate_homelab.py CLI wrapper script.
"""

import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

# Import the main function from the orchestrate_homelab module
sys.path.insert(0, '/Users/10381054/code/home/proxmox/homelab')
from orchestrate_homelab import main


class TestOrchestrateHomelabCLI:
    """Test orchestrate_homelab.py CLI functionality."""

    @patch('sys.argv', ['orchestrate_homelab.py', '--dry-run'])
    @patch('sys.stdout', new_callable=StringIO)
    def test_dry_run_mode(self, mock_stdout):
        """Test dry-run mode displays correct information."""
        # Call main function
        main()
        
        output = mock_stdout.getvalue()
        
        # Check dry-run output contains expected content
        assert "🔍 DRY RUN MODE - showing what would be done:" in output
        assert "1. 🚀 Provision K3s VMs on all Proxmox nodes" in output
        assert "2. 📝 Register K3s VMs in MAAS for persistent IPs" in output
        assert "3. 🔧 Register critical services (Uptime Kuma) in MAAS" in output
        assert "4. 📊 Update monitoring configuration" in output
        assert "5. 📚 Generate documentation from current state" in output
        assert "To run for real: poetry run python orchestrate_homelab.py" in output

    @patch('sys.argv', ['orchestrate_homelab.py'])
    @patch('orchestrate_homelab.InfrastructureOrchestrator')
    @patch('sys.stdout', new_callable=StringIO)
    def test_successful_orchestration(self, mock_stdout, mock_orchestrator_class):
        """Test successful orchestration execution."""
        # Mock orchestrator instance and results
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.orchestrate.return_value = {
            "orchestration_summary": {
                "status": "success",
                "elapsed_time_seconds": 45.2,
                "total_steps_completed": 5
            }
        }
        
        # Call main function
        exit_code = main()
        
        # Check successful execution
        assert exit_code == 0
        
        output = mock_stdout.getvalue()
        assert "🎯 Homelab Infrastructure Orchestration" in output
        assert "✅ All steps completed successfully!" in output
        assert "Next steps:" in output
        assert "nslookup uptime-kuma-pve.maas" in output
        assert "http://uptime-kuma-pve.maas:3001" in output
        
        # Verify orchestrator was called
        mock_orchestrator_class.assert_called_once()
        mock_orchestrator.orchestrate.assert_called_once()

    @patch('sys.argv', ['orchestrate_homelab.py'])
    @patch('orchestrate_homelab.InfrastructureOrchestrator')
    @patch('sys.stdout', new_callable=StringIO)
    def test_failed_orchestration(self, mock_stdout, mock_orchestrator_class):
        """Test failed orchestration execution."""
        # Mock orchestrator instance with failure
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.orchestrate.return_value = {
            "orchestration_summary": {
                "status": "failed",
                "error": "VM creation failed",
                "elapsed_time_seconds": 10.5
            }
        }
        
        # Call main function
        exit_code = main()
        
        # Check failed execution
        assert exit_code == 1
        
        output = mock_stdout.getvalue()
        assert "❌ Orchestration failed!" in output
        assert "Error: VM creation failed" in output
        assert "Check logs above for details." in output
        
        # Verify orchestrator was called
        mock_orchestrator_class.assert_called_once()
        mock_orchestrator.orchestrate.assert_called_once()

    @patch('sys.argv', ['orchestrate_homelab.py'])
    @patch('orchestrate_homelab.InfrastructureOrchestrator')
    @patch('sys.stdout', new_callable=StringIO)
    def test_orchestration_no_summary(self, mock_stdout, mock_orchestrator_class):
        """Test orchestration with missing summary."""
        # Mock orchestrator instance with missing summary
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.orchestrate.return_value = {}
        
        # Call main function
        exit_code = main()
        
        # Check failed execution due to missing summary
        assert exit_code == 1
        
        output = mock_stdout.getvalue()
        assert "❌ Orchestration failed!" in output
        assert "Error: Unknown error" in output
        
        # Verify orchestrator was called
        mock_orchestrator_class.assert_called_once()
        mock_orchestrator.orchestrate.assert_called_once()

    @patch('sys.argv', ['orchestrate_homelab.py', '--help'])
    def test_help_argument(self):
        """Test --help argument displays help message."""
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # argparse exits with code 0 for help
        assert exc_info.value.code == 0

    @patch('sys.argv', ['orchestrate_homelab.py', '--invalid-arg'])
    def test_invalid_argument(self):
        """Test invalid argument handling."""
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # argparse exits with code 2 for invalid arguments
        assert exc_info.value.code == 2