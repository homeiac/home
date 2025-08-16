"""Comprehensive tests for Coral TPU automation engine."""

import pytest
from unittest import mock
from pathlib import Path

from homelab.coral_automation import CoralAutomationEngine
from homelab.coral_models import (
    ActionType, 
    CoralMode, 
    ContainerStatus, 
    CoralAutomationError,
    SafetyViolationError
)


class TestCoralAutomationEngine:
    """Test cases for CoralAutomationEngine with decision matrix validation."""

    @pytest.fixture
    def automation_engine(self, tmp_path):
        """Create automation engine with test paths."""
        return CoralAutomationEngine(
            container_id="113",
            coral_init_dir=tmp_path / "coral",
            config_path=tmp_path / "113.conf",
            backup_dir=tmp_path / "backups"
        )

    @pytest.mark.parametrize("scenario_name", [
        "optimal_no_action",
        "coral_needs_init", 
        "config_mismatch",
        "unsafe_init_running_container",
        "no_coral_detected",
        "container_stopped_correct_config",
        "missing_usb_permissions"
    ])
    def test_decision_matrix_scenarios(self, automation_engine, mock_scenarios, mock_file_system, scenario_name):
        """Test all decision matrix scenarios."""
        scenario = mock_scenarios[scenario_name]
        paths = mock_file_system(scenario_name)
        
        # Setup automation engine with test paths
        automation_engine.config_manager.config_path = paths['config_path']
        automation_engine.config_manager.backup_dir = paths['backup_dir']
        automation_engine.initializer.coral_init_dir = paths['coral_dir']
        
        with mock.patch('subprocess.run') as mock_run:
            # Setup mock responses based on scenario
            def mock_subprocess(cmd, **kwargs):
                result = mock.MagicMock()
                result.returncode = 0
                
                cmd_str = ' '.join(cmd) if isinstance(cmd, list) else str(cmd)
                
                if 'lsusb' in cmd_str:
                    result.stdout = scenario['lsusb_output']
                elif 'pct status' in cmd_str:
                    result.stdout = scenario['pct_status']
                elif 'classify_image.py' in cmd_str:
                    result.stdout = "Mock successful init"
                else:
                    result.stdout = "mock output"
                
                result.stderr = ""
                return result
            
            mock_run.side_effect = mock_subprocess
            
            # Analyze system state
            state = automation_engine.analyze_system_state()
            
            # Create automation plan
            plan = automation_engine.create_automation_plan(state)
            
            # Validate decision matrix
            assert plan.actions == scenario['expected_actions'], f"Scenario {scenario_name}: Wrong actions"
            assert plan.safe == scenario['expected_safe'], f"Scenario {scenario_name}: Wrong safety assessment"

    def test_optimal_state_no_action(self, automation_engine, system_state_optimal):
        """Test that optimal state requires no action."""
        with mock.patch.object(automation_engine, 'analyze_system_state', return_value=system_state_optimal):
            plan = automation_engine.create_automation_plan(system_state_optimal)
            
            assert plan.actions == [ActionType.NO_ACTION]
            assert plan.safe is True
            assert "optimal" in plan.reason.lower()

    def test_coral_needs_initialization_safe(self, automation_engine, system_state_needs_init):
        """Test Coral initialization when safe."""
        with mock.patch.object(automation_engine, 'analyze_system_state', return_value=system_state_needs_init):
            plan = automation_engine.create_automation_plan(system_state_needs_init)
            
            assert ActionType.INITIALIZE_CORAL in plan.actions
            assert plan.safe is True

    def test_coral_needs_initialization_unsafe(self, automation_engine, system_state_unsafe_init):
        """Test Coral initialization when unsafe (container running)."""
        with mock.patch.object(automation_engine, 'analyze_system_state', return_value=system_state_unsafe_init):
            plan = automation_engine.create_automation_plan(system_state_unsafe_init)
            
            assert plan.actions == [ActionType.ERROR_ABORT]
            assert plan.safe is False
            assert "not safe" in plan.reason.lower()

    def test_config_mismatch_requires_update(self, automation_engine, system_state_config_mismatch):
        """Test that config mismatch triggers update and restart."""
        with mock.patch.object(automation_engine, 'analyze_system_state', return_value=system_state_config_mismatch):
            plan = automation_engine.create_automation_plan(system_state_config_mismatch)
            
            assert ActionType.UPDATE_CONFIG in plan.actions
            assert ActionType.RESTART_CONTAINER in plan.actions
            assert plan.backup_required is True

    def test_safety_violation_error(self, automation_engine):
        """Test safety violation when trying to initialize Google mode device."""
        with mock.patch('subprocess.run') as mock_run, \
             mock.patch.object(automation_engine.config_manager.config_path, 'exists', return_value=True), \
             mock.patch.object(automation_engine.config_manager.config_path, 'read_text', return_value="dev0: /dev/bus/usb/003/004\nlxc.cgroup2.devices.allow: c 189:* rwm"):
            
            # Mock Google mode device
            mock_run.return_value.stdout = "Bus 003 Device 004: ID 18d1:9302 Google Inc."
            mock_run.return_value.returncode = 0
            
            # Force initialization attempt
            with pytest.raises(SafetyViolationError, match="SAFETY VIOLATION"):
                automation_engine.initializer.initialize_coral(dry_run=False)

    def test_execute_plan_dry_run(self, automation_engine, system_state_needs_init, tmp_path):
        """Test plan execution in dry run mode."""
        # Setup test files
        init_script = tmp_path / "coral" / "pycoral" / "examples" / "classify_image.py"
        init_script.parent.mkdir(parents=True)
        init_script.write_text("# mock script")
        
        test_data = tmp_path / "test_data"
        test_data.mkdir()
        (test_data / "mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite").write_text("mock model")
        (test_data / "inat_bird_labels.txt").write_text("mock labels")
        (test_data / "parrot.jpg").write_text("mock image")
        
        automation_engine.initializer.coral_init_dir = tmp_path
        
        plan = automation_engine.create_automation_plan(system_state_needs_init)
        
        # Execute in dry run mode
        result = automation_engine.execute_plan(plan, dry_run=True)
        
        assert result is True

    def test_execute_plan_unsafe_abort(self, automation_engine):
        """Test that unsafe plans cannot be executed."""
        from homelab.coral_models import AutomationPlan
        
        unsafe_plan = AutomationPlan(
            actions=[ActionType.ERROR_ABORT],
            reason="Test unsafe plan",
            safe=False
        )
        
        with pytest.raises(CoralAutomationError, match="Unsafe plan cannot be executed"):
            automation_engine.execute_plan(unsafe_plan, dry_run=True)

    def test_backup_and_rollback(self, automation_engine, tmp_path):
        """Test backup creation and rollback on failure."""
        config_file = tmp_path / "113.conf"
        config_file.write_text("original config")
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        
        automation_engine.config_manager.config_path = config_file
        automation_engine.config_manager.backup_dir = backup_dir
        
        # Mock plan that will fail
        from homelab.coral_models import AutomationPlan
        plan = AutomationPlan(
            actions=[ActionType.UPDATE_CONFIG],
            reason="Test backup",
            backup_required=True
        )
        
        with mock.patch.object(automation_engine, '_execute_action', return_value=False):
            with pytest.raises(CoralAutomationError):
                automation_engine.execute_plan(plan, dry_run=False)
        
        # Verify backup was created
        backups = list(backup_dir.glob("lxc_113_*.conf"))
        assert len(backups) >= 1
        assert backups[0].read_text() == "original config"

    def test_frigate_tpu_usage_detection(self, automation_engine, lxc_config_optimal):
        """Test detection of Frigate using TPU."""
        # Running container with dev0 should be considered "using TPU"
        is_using = automation_engine._is_frigate_using_tpu(lxc_config_optimal)
        assert is_using is True
        
        # Stopped container should not be using TPU
        lxc_config_optimal.status = ContainerStatus.STOPPED
        is_using = automation_engine._is_frigate_using_tpu(lxc_config_optimal)
        assert is_using is False

    def test_complete_automation_cycle_success(self, automation_engine, mock_file_system, tmp_path):
        """Test complete automation cycle end-to-end."""
        paths = mock_file_system("coral_needs_init")
        
        automation_engine.config_manager.config_path = paths['config_path']
        automation_engine.config_manager.backup_dir = paths['backup_dir']
        automation_engine.initializer.coral_init_dir = paths['coral_dir']
        
        with mock.patch('subprocess.run') as mock_run:
            # Setup progressive mock responses
            call_count = 0
            def mock_subprocess(cmd, **kwargs):
                nonlocal call_count
                call_count += 1
                
                result = mock.MagicMock()
                result.returncode = 0
                
                cmd_str = ' '.join(cmd) if isinstance(cmd, list) else str(cmd)
                
                if 'lsusb' in cmd_str:
                    if call_count <= 2:
                        # First calls show Unichip mode
                        result.stdout = "Bus 003 Device 003: ID 1a6e:089a Global Unichip Corp."
                    else:
                        # After init, show Google mode
                        result.stdout = "Bus 003 Device 004: ID 18d1:9302 Google Inc."
                elif 'pct status' in cmd_str:
                    result.stdout = "status: stopped"
                elif 'classify_image.py' in cmd_str:
                    result.stdout = "Mock successful init"
                else:
                    result.stdout = "mock output"
                
                result.stderr = ""
                return result
            
            mock_run.side_effect = mock_subprocess
            
            # Run complete automation
            results = automation_engine.run_automation(dry_run=False)
            
            assert results['success'] is True
            assert 'initial_state' in results
            assert 'plan' in results

    def test_complete_automation_cycle_dry_run(self, automation_engine, mock_file_system):
        """Test complete automation cycle in dry run mode."""
        paths = mock_file_system("config_mismatch")
        
        automation_engine.config_manager.config_path = paths['config_path']
        automation_engine.config_manager.backup_dir = paths['backup_dir']
        automation_engine.initializer.coral_init_dir = paths['coral_dir']
        
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = "Bus 003 Device 004: ID 18d1:9302 Google Inc."
            mock_run.return_value.returncode = 0
            
            # Run in dry run mode
            results = automation_engine.run_automation(dry_run=True)
            
            assert results['success'] is True
            assert results['dry_run'] is True

    def test_error_handling_and_reporting(self, automation_engine):
        """Test error handling and reporting."""
        with mock.patch.object(automation_engine, 'analyze_system_state', side_effect=Exception("Test error")):
            results = automation_engine.run_automation(dry_run=True)
            
            assert results['success'] is False
            assert 'error' in results
            assert "Test error" in results['error']

    @pytest.mark.parametrize("action_type,mock_setup,expected_success", [
        (ActionType.INITIALIZE_CORAL, lambda ae: mock.patch.object(ae.initializer, 'initialize_coral', return_value=mock.MagicMock()), True),
        (ActionType.UPDATE_CONFIG, lambda ae: mock.patch.object(ae.config_manager, 'update_config', return_value=True), True),
        (ActionType.RESTART_CONTAINER, lambda ae: mock.patch.object(ae.config_manager, 'stop_container', return_value=True), True),
    ])
    def test_individual_action_execution(self, automation_engine, action_type, mock_setup, expected_success):
        """Test individual action execution."""
        with mock_setup(automation_engine) as mock_action, \
             mock.patch.object(automation_engine.detector, 'detect_coral') as mock_detect:
            
            mock_detect.return_value.device_path = "/dev/bus/usb/003/004"
            
            if action_type == ActionType.RESTART_CONTAINER:
                with mock.patch.object(automation_engine.config_manager, 'start_container', return_value=True), \
                     mock.patch.object(automation_engine.config_manager, 'verify_coral_access', return_value=True):
                    result = automation_engine._execute_action(action_type, dry_run=False)
            else:
                result = automation_engine._execute_action(action_type, dry_run=False)
            
            assert result == expected_success

    def test_coral_accessibility_verification(self, automation_engine):
        """Test Coral accessibility verification after container restart."""
        with mock.patch.object(automation_engine.config_manager, 'stop_container', return_value=True), \
             mock.patch.object(automation_engine.config_manager, 'start_container', return_value=True), \
             mock.patch.object(automation_engine.config_manager, 'verify_coral_access', return_value=True), \
             mock.patch.object(automation_engine.detector, 'detect_coral') as mock_detect:
            
            mock_detect.return_value.device_path = "/dev/bus/usb/003/004"
            
            result = automation_engine._execute_action(ActionType.RESTART_CONTAINER, dry_run=False)
            
            assert result is True
            automation_engine.config_manager.verify_coral_access.assert_called_once_with("/dev/bus/usb/003/004")

    def test_unknown_action_handling(self, automation_engine):
        """Test handling of unknown action types."""
        # Create a mock action that doesn't exist
        unknown_action = mock.MagicMock()
        unknown_action.value = "unknown_action"
        
        result = automation_engine._execute_action(unknown_action, dry_run=False)
        
        assert result is False