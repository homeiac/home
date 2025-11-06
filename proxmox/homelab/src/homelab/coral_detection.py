"""Coral TPU device detection and monitoring."""

import logging
import re
import subprocess
from typing import Optional

from .coral_models import CoralDevice, CoralMode, DeviceNotFoundError

logger = logging.getLogger(__name__)


class CoralDetector:
    """Detects and monitors Coral TPU devices."""

    def __init__(self) -> None:
        """Initialize the detector."""
        self._last_detection: Optional[CoralDevice] = None

    def detect_coral(self) -> CoralDevice:
        """
        Detect current Coral TPU device state.

        Returns:
            CoralDevice with current state

        Raises:
            DeviceNotFoundError: If no Coral device is detected
        """
        logger.debug("Detecting Coral TPU device")

        try:
            result = subprocess.run(["lsusb"], capture_output=True, text=True, check=True, timeout=10)
            usb_output = result.stdout
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to run lsusb: {e}")
            raise DeviceNotFoundError("Could not execute lsusb command") from e

        # Look for Google mode (initialized)
        google_device = self._parse_usb_line(usb_output, CoralMode.GOOGLE)
        if google_device:
            logger.info(f"Coral detected in Google mode: {google_device.description}")
            self._last_detection = google_device
            return google_device

        # Look for Unichip mode (needs initialization)
        unichip_device = self._parse_usb_line(usb_output, CoralMode.UNICHIP)
        if unichip_device:
            logger.info(f"Coral detected in Unichip mode: {unichip_device.description}")
            self._last_detection = unichip_device
            return unichip_device

        # No Coral device found
        no_device = CoralDevice(mode=CoralMode.NOT_FOUND)
        logger.warning("No Coral TPU device detected")
        self._last_detection = no_device
        return no_device

    def _parse_usb_line(self, usb_output: str, mode: CoralMode) -> Optional[CoralDevice]:
        """
        Parse lsusb output for specific device mode.

        Args:
            usb_output: Full lsusb command output
            mode: CoralMode to search for

        Returns:
            CoralDevice if found, None otherwise
        """
        if mode == CoralMode.NOT_FOUND:
            return None

        pattern = rf"Bus (\d+) Device (\d+): ID {mode.value} (.+)"

        for line in usb_output.splitlines():
            match = re.search(pattern, line.strip())
            if match:
                bus, device, description = match.groups()
                device_path = f"/dev/bus/usb/{bus}/{device}"

                return CoralDevice(
                    mode=mode, bus=bus, device=device, device_path=device_path, description=description.strip()
                )

        return None

    def get_last_detection(self) -> Optional[CoralDevice]:
        """Get the last detected device state."""
        return self._last_detection

    def verify_device_accessible(self, device: CoralDevice) -> bool:
        """
        Verify that the detected device is actually accessible.

        Args:
            device: CoralDevice to verify

        Returns:
            True if device file exists and is accessible
        """
        if not device.device_path:
            return False

        try:
            result = subprocess.run(
                ["ls", "-l", device.device_path], capture_output=True, text=True, check=True, timeout=5
            )
            logger.debug(f"Device accessible: {result.stdout.strip()}")
            return True
        except subprocess.SubprocessError:
            logger.warning(f"Device not accessible: {device.device_path}")
            return False

    def wait_for_mode_change(self, expected_mode: CoralMode, timeout: int = 30) -> CoralDevice:
        """
        Wait for device to change to expected mode.

        Args:
            expected_mode: Mode to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            CoralDevice in expected mode

        Raises:
            DeviceNotFoundError: If device doesn't reach expected mode within timeout
        """
        import time

        logger.info(f"Waiting for Coral to enter {expected_mode.name} mode (timeout: {timeout}s)")

        start_time = time.time()
        while time.time() - start_time < timeout:
            current = self.detect_coral()
            if current.mode == expected_mode:
                logger.info(f"Device reached {expected_mode.name} mode")
                return current

            time.sleep(1)

        raise DeviceNotFoundError(f"Device did not reach {expected_mode.name} mode within {timeout} seconds")
