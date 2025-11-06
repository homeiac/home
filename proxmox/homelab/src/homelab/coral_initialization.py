"""Coral TPU initialization and safety management."""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from .coral_detection import CoralDetector
from .coral_models import CoralDevice, CoralMode, InitializationError, SafetyViolationError

logger = logging.getLogger(__name__)


class CoralInitializer:
    """Handles Coral TPU initialization with safety checks."""

    def __init__(self, coral_init_dir: Path = Path("/root/code"), python_cmd: str = "python3"):
        """
        Initialize the Coral initializer.

        Args:
            coral_init_dir: Directory containing coral repos
            python_cmd: Python command to use
        """
        self.coral_init_dir = coral_init_dir
        self.python_cmd = python_cmd
        self.detector = CoralDetector()

        # Required files for initialization
        self.init_script = coral_init_dir / "coral/pycoral/examples/classify_image.py"
        self.model_file = coral_init_dir / "test_data/mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite"
        self.labels_file = coral_init_dir / "test_data/inat_bird_labels.txt"
        self.input_file = coral_init_dir / "test_data/parrot.jpg"

    def can_initialize_safely(self, current_device: Optional[CoralDevice] = None) -> tuple[bool, str]:
        """
        Check if initialization can be performed safely.

        Args:
            current_device: Current device state (will detect if None)

        Returns:
            Tuple of (can_initialize, reason)
        """
        if current_device is None:
            current_device = self.detector.detect_coral()

        # CRITICAL SAFETY CHECK: Never initialize if already in Google mode
        if current_device.mode == CoralMode.GOOGLE:
            return False, (
                "SAFETY VIOLATION: Coral already in Google mode (18d1:9302). "
                "Running initialization would break Frigate's access to TPU! "
                "Reboot first if reinitialization is needed."
            )

        # Only allow initialization if in Unichip mode
        if current_device.mode != CoralMode.UNICHIP:
            return False, f"Coral not in Unichip mode. Current state: {current_device.mode}"

        # Check if required files exist
        missing_files = []
        for file_path, name in [
            (self.init_script, "initialization script"),
            (self.model_file, "model file"),
            (self.labels_file, "labels file"),
            (self.input_file, "input image"),
        ]:
            if not file_path.exists():
                missing_files.append(f"{name} ({file_path})")

        if missing_files:
            return False, f"Missing required files: {', '.join(missing_files)}"

        return True, "Safe to initialize"

    def initialize_coral(self, dry_run: bool = False, timeout: int = 60) -> CoralDevice:
        """
        Initialize Coral TPU device.

        Args:
            dry_run: If True, only validate without executing
            timeout: Timeout for initialization in seconds

        Returns:
            CoralDevice after initialization

        Raises:
            SafetyViolationError: If initialization is not safe
            InitializationError: If initialization fails
        """
        logger.info(f"Initializing Coral TPU (dry_run={dry_run})")

        # Pre-initialization safety check
        current_device = self.detector.detect_coral()
        can_init, reason = self.can_initialize_safely(current_device)

        if not can_init:
            logger.error(f"Initialization blocked: {reason}")
            raise SafetyViolationError(reason)

        logger.info(f"✓ Safety check passed: {reason}")
        logger.info(f"Current device: {current_device.description}")

        if dry_run:
            logger.info("DRY RUN: Would execute initialization script")
            logger.info(f"Command: {self._build_init_command()}")
            # Return simulated Google mode device
            return CoralDevice(
                mode=CoralMode.GOOGLE,
                bus="003",
                device="005",
                device_path="/dev/bus/usb/003/005",
                description="Google Inc. (simulated)",
            )

        # Execute initialization
        try:
            logger.info("Running Coral initialization script...")
            result = subprocess.run(
                self._build_init_command(),
                cwd=self.coral_init_dir,
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
            )

            logger.info("Initialization script completed successfully")
            logger.debug(f"Script output: {result.stdout}")

        except subprocess.TimeoutExpired as e:
            raise InitializationError(f"Initialization timed out after {timeout} seconds") from e
        except subprocess.CalledProcessError as e:
            raise InitializationError(f"Initialization script failed (exit code {e.returncode}): {e.stderr}") from e

        # Wait for device to switch to Google mode
        try:
            new_device = self.detector.wait_for_mode_change(CoralMode.GOOGLE, timeout=30)
            logger.info(f"Coral successfully initialized: {new_device.description}")
            return new_device
        except Exception as e:
            raise InitializationError(f"Device did not switch to Google mode after initialization: {e}") from e

    def _build_init_command(self) -> list[str]:
        """Build the initialization command."""
        return [
            self.python_cmd,
            str(self.init_script),
            "--model",
            str(self.model_file),
            "--labels",
            str(self.labels_file),
            "--input",
            str(self.input_file),
        ]

    def verify_prerequisites(self) -> tuple[bool, list[str]]:
        """
        Verify that all prerequisites for initialization are met.

        Returns:
            Tuple of (all_good, list_of_issues)
        """
        issues = []

        # Check if coral directory exists
        if not self.coral_init_dir.exists():
            issues.append(f"Coral init directory not found: {self.coral_init_dir}")
            return False, issues

        # Check individual files
        for file_path, description in [
            (self.init_script, "PyCoral initialization script"),
            (self.model_file, "MobileNet model file"),
            (self.labels_file, "Labels file"),
            (self.input_file, "Test input image"),
        ]:
            if not file_path.exists():
                issues.append(f"{description} not found: {file_path}")

        # Check if python command is available
        try:
            result = subprocess.run(
                [self.python_cmd, "--version"], capture_output=True, text=True, check=True, timeout=5
            )
            logger.debug(f"Python version: {result.stdout.strip()}")
        except subprocess.SubprocessError:
            issues.append(f"Python command not available: {self.python_cmd}")

        # Check if PyCoral is importable
        try:
            subprocess.run([self.python_cmd, "-c", "import pycoral"], capture_output=True, check=True, timeout=5)
        except subprocess.SubprocessError:
            issues.append("PyCoral library not available")

        return len(issues) == 0, issues

    def get_initialization_status(self) -> dict[str, any]:
        """
        Get comprehensive initialization status.

        Returns:
            Dictionary with status information
        """
        current_device = self.detector.detect_coral()
        can_init, reason = self.can_initialize_safely(current_device)
        prereqs_ok, prereq_issues = self.verify_prerequisites()

        return {
            "device_detected": current_device.mode != CoralMode.NOT_FOUND,
            "device_mode": current_device.mode.name if current_device.mode else "NOT_FOUND",
            "device_description": current_device.description,
            "device_path": current_device.device_path,
            "can_initialize": can_init,
            "initialization_reason": reason,
            "prerequisites_ok": prereqs_ok,
            "prerequisite_issues": prereq_issues,
            "required_files": {
                "init_script": str(self.init_script),
                "model_file": str(self.model_file),
                "labels_file": str(self.labels_file),
                "input_file": str(self.input_file),
            },
        }
