"""Main Coral TPU automation logic with decision making."""

import logging
from pathlib import Path
from typing import Optional

from .coral_config import LXCConfigManager
from .coral_detection import CoralDetector
from .coral_initialization import CoralInitializer
from .coral_models import (
    ActionType,
    AutomationPlan,
    CoralAutomationError,
    CoralMode,
    ContainerStatus,
    SystemState,
)

logger = logging.getLogger(__name__)


class CoralAutomationEngine:
    """Main automation engine for Coral TPU management."""

    def __init__(
        self,
        container_id: str = "113",
        coral_init_dir: Optional[Path] = None,
        config_path: Optional[Path] = None,
        backup_dir: Optional[Path] = None,
        python_cmd: str = "python3"
    ):
        """
        Initialize the automation engine.
        
        Args:
            container_id: LXC container ID for Frigate
            coral_init_dir: Directory containing coral repos
            config_path: Path to LXC config file
            backup_dir: Directory for config backups
            python_cmd: Python command to use
        """
        self.container_id = container_id
        
        # Initialize components
        self.detector = CoralDetector()
        self.initializer = CoralInitializer(
            coral_init_dir=coral_init_dir or Path.home() / "code",
            python_cmd=python_cmd
        )
        self.config_manager = LXCConfigManager(
            container_id=container_id,
            config_path=config_path,
            backup_dir=backup_dir
        )

    def analyze_system_state(self) -> SystemState:
        """
        Analyze complete system state.
        
        Returns:
            SystemState with current conditions
        """
        logger.info("Analyzing system state...")
        
        # Detect Coral device
        coral_device = self.detector.detect_coral()
        logger.info(f"Coral state: {coral_device.mode.name if coral_device.mode else 'NOT_FOUND'}")
        
        # Read LXC configuration
        lxc_config = self.config_manager.read_config()
        logger.info(f"Container state: {lxc_config.status.value}")
        logger.info(f"Current dev0: {lxc_config.current_dev0}")
        
        # Check if Frigate is actively using TPU
        frigate_using_tpu = self._is_frigate_using_tpu(lxc_config)
        
        state = SystemState(
            coral=coral_device,
            lxc=lxc_config,
            frigate_using_tpu=frigate_using_tpu
        )
        
        logger.info(f"System analysis complete:")
        logger.info(f"  - Coral mode: {coral_device.mode.name if coral_device.mode else 'NOT_FOUND'}")
        logger.info(f"  - Device path: {coral_device.device_path}")
        logger.info(f"  - Config path: {lxc_config.current_dev0}")
        logger.info(f"  - Config matches: {state.config_matches_device}")
        logger.info(f"  - Container status: {lxc_config.status.value}")
        logger.info(f"  - Frigate using TPU: {frigate_using_tpu}")
        
        return state

    def _is_frigate_using_tpu(self, lxc_config) -> bool:
        """
        Check if Frigate is actively using the TPU.
        
        This is a conservative check - if container is running and has TPU access,
        we assume Frigate might be using it.
        """
        return (
            lxc_config.status == ContainerStatus.RUNNING and
            lxc_config.current_dev0 is not None
        )

    def create_automation_plan(self, state: SystemState) -> AutomationPlan:
        """
        Create automation plan based on system state.
        
        Args:
            state: Current system state
            
        Returns:
            AutomationPlan with required actions
        """
        logger.info("Creating automation plan...")
        
        # Error conditions first
        if state.coral.mode == CoralMode.NOT_FOUND:
            return AutomationPlan(
                actions=[ActionType.ERROR_ABORT],
                reason="No Coral TPU device detected",
                safe=False
            )

        # Optimal state - no action needed
        if (state.coral.is_initialized and 
            state.config_matches_device and 
            state.lxc.has_usb_permissions):
            return AutomationPlan(
                actions=[ActionType.NO_ACTION],
                reason="System is optimal - Coral initialized and config correct"
            )

        actions = []
        reasons = []

        # Device needs initialization
        if state.coral.needs_initialization:
            if not state.safe_to_initialize:
                return AutomationPlan(
                    actions=[ActionType.ERROR_ABORT],
                    reason="Coral needs initialization but it's not safe (container running or Frigate using TPU)",
                    safe=False
                )
            actions.append(ActionType.INITIALIZE_CORAL)
            reasons.append("initialize Coral from Unichip to Google mode")

        # Configuration needs updating
        if (state.coral.is_initialized and 
            (not state.config_matches_device or not state.lxc.has_usb_permissions)):
            
            if not state.safe_to_update_config:
                return AutomationPlan(
                    actions=[ActionType.ERROR_ABORT],
                    reason="Config needs updating but Frigate is using TPU",
                    safe=False
                )
            
            actions.append(ActionType.UPDATE_CONFIG)
            reasons.append("update LXC config with correct device path")
            
            # Container restart needed after config change
            if state.lxc.status == ContainerStatus.RUNNING:
                actions.append(ActionType.RESTART_CONTAINER)
                reasons.append("restart container to apply config changes")

        # Container needs starting (but only if config is correct)
        if (state.coral.is_initialized and 
            state.config_matches_device and 
            state.lxc.status == ContainerStatus.STOPPED):
            actions.append(ActionType.RESTART_CONTAINER)
            reasons.append("start container")

        reason_text = ", ".join(reasons) if reasons else "no actions required"
        
        plan = AutomationPlan(
            actions=actions,
            reason=f"Plan: {reason_text}",
            backup_required=ActionType.UPDATE_CONFIG in actions
        )
        
        logger.info(f"Automation plan created: {len(actions)} actions")
        for action in actions:
            logger.info(f"  - {action.value}")
        
        return plan

    def execute_plan(self, plan: AutomationPlan, dry_run: bool = False) -> bool:
        """
        Execute the automation plan.
        
        Args:
            plan: AutomationPlan to execute
            dry_run: If True, only simulate execution
            
        Returns:
            True if execution succeeded
            
        Raises:
            CoralAutomationError: If execution fails
        """
        if not plan.safe:
            raise CoralAutomationError(f"Unsafe plan cannot be executed: {plan.reason}")

        if ActionType.NO_ACTION in plan.actions:
            logger.info("✓ No actions required - system is optimal")
            return True

        if ActionType.ERROR_ABORT in plan.actions:
            raise CoralAutomationError(f"Execution aborted: {plan.reason}")

        logger.info(f"Executing automation plan (dry_run={dry_run})")
        logger.info(f"Plan: {plan.reason}")

        backup_path = None

        try:
            # Create backup if needed
            if plan.backup_required and not dry_run:
                backup_path = self.config_manager.backup_config()
                logger.info(f"Configuration backed up to {backup_path}")

            # Execute actions in order
            for action in plan.actions:
                if not self._execute_action(action, dry_run):
                    raise CoralAutomationError(f"Action failed: {action.value}")

            logger.info("✓ Automation plan executed successfully")
            return True

        except Exception as e:
            logger.error(f"Automation execution failed: {e}")
            
            # Attempt rollback if we have a backup
            if backup_path and not dry_run:
                logger.warning("Attempting to restore configuration backup...")
                try:
                    import shutil
                    shutil.copy2(backup_path, self.config_manager.config_path)
                    logger.info("Configuration restored from backup")
                except Exception as rollback_error:
                    logger.error(f"Failed to restore backup: {rollback_error}")
            
            raise

    def _execute_action(self, action: ActionType, dry_run: bool) -> bool:
        """Execute a single action."""
        logger.info(f"Executing action: {action.value}")

        if action == ActionType.INITIALIZE_CORAL:
            try:
                new_device = self.initializer.initialize_coral(dry_run=dry_run)
                logger.info(f"Coral initialized: {new_device.device_path}")
                return True
            except Exception as e:
                logger.error(f"Coral initialization failed: {e}")
                return False

        elif action == ActionType.UPDATE_CONFIG:
            try:
                # Get current device state
                current_device = self.detector.detect_coral()
                if not current_device.device_path:
                    logger.error("Cannot update config - no device path available")
                    return False
                
                success = self.config_manager.update_config(
                    device_path=current_device.device_path,
                    dry_run=dry_run
                )
                if success:
                    logger.info(f"Config updated with device: {current_device.device_path}")
                return success
            except Exception as e:
                logger.error(f"Config update failed: {e}")
                return False

        elif action == ActionType.RESTART_CONTAINER:
            try:
                # Stop container
                if not self.config_manager.stop_container():
                    logger.error("Failed to stop container")
                    return False
                
                # Start container
                if not self.config_manager.start_container():
                    logger.error("Failed to start container")
                    return False
                
                # Verify Coral access
                if not dry_run:
                    current_device = self.detector.detect_coral()
                    if current_device.device_path:
                        coral_accessible = self.config_manager.verify_coral_access(
                            current_device.device_path
                        )
                        if coral_accessible:
                            logger.info("✓ Coral TPU verified accessible in container")
                        else:
                            logger.warning("⚠ Coral TPU not accessible in container")
                
                return True
            except Exception as e:
                logger.error(f"Container restart failed: {e}")
                return False

        else:
            logger.error(f"Unknown action: {action}")
            return False

    def run_automation(self, dry_run: bool = False) -> dict:
        """
        Run complete automation cycle.
        
        Args:
            dry_run: If True, only simulate changes
            
        Returns:
            Dictionary with automation results
        """
        logger.info(f"=== Coral TPU Automation Starting (dry_run={dry_run}) ===")
        
        try:
            # Analyze system state
            state = self.analyze_system_state()
            
            # Create automation plan
            plan = self.create_automation_plan(state)
            
            # Execute plan
            success = self.execute_plan(plan, dry_run=dry_run)
            
            # Final verification
            if success and not dry_run:
                final_state = self.analyze_system_state()
                logger.info("=== Final System State ===")
                logger.info(f"Coral mode: {final_state.coral.mode.name if final_state.coral.mode else 'NOT_FOUND'}")
                logger.info(f"Config matches: {final_state.config_matches_device}")
                logger.info(f"Container status: {final_state.lxc.status.value}")
            
            logger.info("=== Coral TPU Automation Complete ===")
            
            return {
                "success": success,
                "initial_state": {
                    "coral_mode": state.coral.mode.name if state.coral.mode else "NOT_FOUND",
                    "device_path": state.coral.device_path,
                    "config_path": state.lxc.current_dev0,
                    "config_matches": state.config_matches_device,
                    "container_status": state.lxc.status.value
                },
                "plan": {
                    "actions": [action.value for action in plan.actions],
                    "reason": plan.reason,
                    "safe": plan.safe
                },
                "dry_run": dry_run
            }
            
        except Exception as e:
            logger.error(f"Automation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "dry_run": dry_run
            }