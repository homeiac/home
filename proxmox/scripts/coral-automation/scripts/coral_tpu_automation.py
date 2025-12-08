#!/usr/bin/env python3
"""Coral TPU automation CLI script."""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from homelab.coral_automation import CoralAutomationEngine


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # Try to add file handler if we have permissions
    try:
        handlers.append(logging.FileHandler("/var/log/coral-tpu-automation.log"))
    except PermissionError:
        # Fallback to local log file
        handlers.append(logging.FileHandler("coral-tpu-automation.log"))
    
    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=handlers
    )


def main() -> int:
    """Main CLI function."""
    parser = argparse.ArgumentParser(description="Coral TPU Automation")
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--container-id", 
        default="113", 
        help="LXC container ID (default: 113)"
    )
    parser.add_argument(
        "--coral-dir", 
        type=Path, 
        default=Path.home() / "code",
        help="Directory containing coral repos (default: ~/code)"
    )
    parser.add_argument(
        "--config-path", 
        type=Path,
        help="Path to LXC config file (default: /etc/pve/lxc/{container_id}.conf or ~/lxc_configs/{container_id}.conf)"
    )
    parser.add_argument(
        "--backup-dir", 
        type=Path,
        default=Path.home() / "coral-backups",
        help="Directory for config backups (default: ~/coral-backups)"
    )
    parser.add_argument(
        "--verbose", "-v", 
        action="store_true", 
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--status-only", 
        action="store_true",
        help="Only show current system status"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize automation engine
        engine = CoralAutomationEngine(
            container_id=args.container_id,
            coral_init_dir=args.coral_dir,
            config_path=args.config_path,
            backup_dir=args.backup_dir
        )
        
        if args.status_only:
            # Just show status
            logger.info("=== Coral TPU System Status ===")
            state = engine.analyze_system_state()
            plan = engine.create_automation_plan(state)
            
            print("\n🔍 Current System State:")
            print(f"  Coral Mode: {state.coral.mode.name if state.coral.mode else 'NOT_FOUND'}")
            print(f"  Device Path: {state.coral.device_path or 'N/A'}")
            print(f"  Config Path: {state.lxc.current_dev0 or 'N/A'}")
            print(f"  Config Matches: {'✅' if state.config_matches_device else '❌'}")
            print(f"  Container Status: {state.lxc.status.value}")
            print(f"  USB Permissions: {'✅' if state.lxc.has_usb_permissions else '❌'}")
            print(f"  Frigate Using TPU: {'⚠️' if state.frigate_using_tpu else '✅'}")
            
            print(f"\n📋 Automation Plan:")
            print(f"  Actions: {[action.value for action in plan.actions]}")
            print(f"  Reason: {plan.reason}")
            print(f"  Safe: {'✅' if plan.safe else '❌'}")
            
            return 0
        
        # Run automation
        results = engine.run_automation(dry_run=args.dry_run)
        
        if results['success']:
            print("\n✅ Coral TPU automation completed successfully!")
            if args.dry_run:
                print("🔍 This was a dry run - no changes were made")
            
            if 'plan' in results:
                actions = results['plan'].get('actions', [])
                if actions == ['no_action']:
                    print("🎯 System was already optimal - no changes needed")
                else:
                    print(f"🔧 Actions taken: {', '.join(actions)}")
            
            return 0
        else:
            print(f"\n❌ Coral TPU automation failed: {results.get('error', 'Unknown error')}")
            return 1
            
    except KeyboardInterrupt:
        logger.info("Automation interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\n💥 Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())