"""Comprehensive tests for Coral TPU detection."""

import subprocess
from unittest import mock

import pytest

from homelab.coral_detection import CoralDetector
from homelab.coral_models import CoralMode, DeviceNotFoundError


class TestCoralDetector:
    """Test cases for CoralDetector class."""

    def test_detect_coral_google_mode(self, lsusb_google_mode):
        """Test detection of Coral in Google mode."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = lsusb_google_mode
            mock_run.return_value.returncode = 0
            
            detector = CoralDetector()
            device = detector.detect_coral()
            
            assert device.mode == CoralMode.GOOGLE
            assert device.bus == "003"
            assert device.device == "004"
            assert device.device_path == "/dev/bus/usb/003/004"
            assert "Google Inc." in device.description
            assert device.is_initialized is True
            assert device.needs_initialization is False

    def test_detect_coral_unichip_mode(self, lsusb_unichip_mode):
        """Test detection of Coral in Unichip mode."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = lsusb_unichip_mode
            mock_run.return_value.returncode = 0
            
            detector = CoralDetector()
            device = detector.detect_coral()
            
            assert device.mode == CoralMode.UNICHIP
            assert device.bus == "003"
            assert device.device == "003"
            assert device.device_path == "/dev/bus/usb/003/003"
            assert "Global Unichip Corp." in device.description
            assert device.is_initialized is False
            assert device.needs_initialization is True

    def test_detect_coral_not_found(self, lsusb_no_coral):
        """Test detection when no Coral device present."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = lsusb_no_coral
            mock_run.return_value.returncode = 0
            
            detector = CoralDetector()
            device = detector.detect_coral()
            
            assert device.mode == CoralMode.NOT_FOUND
            assert device.bus is None
            assert device.device is None
            assert device.device_path is None
            assert device.description is None
            assert device.is_initialized is False
            assert device.needs_initialization is False

    def test_detect_coral_google_priority(self, lsusb_multiple_devices):
        """Test that Google mode takes priority over Unichip when both present."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = lsusb_multiple_devices
            mock_run.return_value.returncode = 0
            
            detector = CoralDetector()
            device = detector.detect_coral()
            
            # Should detect Google mode first
            assert device.mode == CoralMode.GOOGLE
            assert device.device == "004"

    def test_detect_coral_lsusb_failure(self):
        """Test handling of lsusb command failure."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, 'lsusb')
            
            detector = CoralDetector()
            
            with pytest.raises(DeviceNotFoundError, match="Could not execute lsusb command"):
                detector.detect_coral()

    def test_detect_coral_timeout(self):
        """Test handling of lsusb timeout."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired('lsusb', 10)
            
            detector = CoralDetector()
            
            with pytest.raises(DeviceNotFoundError, match="Could not execute lsusb command"):
                detector.detect_coral()

    def test_get_last_detection(self, lsusb_google_mode):
        """Test get_last_detection returns cached result."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = lsusb_google_mode
            mock_run.return_value.returncode = 0
            
            detector = CoralDetector()
            
            # Initially no detection
            assert detector.get_last_detection() is None
            
            # After detection, should cache result
            device = detector.detect_coral()
            cached = detector.get_last_detection()
            
            assert cached == device
            assert cached.mode == CoralMode.GOOGLE

    def test_verify_device_accessible_success(self, coral_device_google):
        """Test device accessibility check success."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = "crw-rw-rw- 1 root plugdev 189, 259"
            mock_run.return_value.returncode = 0
            
            detector = CoralDetector()
            accessible = detector.verify_device_accessible(coral_device_google)
            
            assert accessible is True
            mock_run.assert_called_once_with(
                ["ls", "-l", "/dev/bus/usb/003/004"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )

    def test_verify_device_accessible_failure(self, coral_device_google):
        """Test device accessibility check failure."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, 'ls')
            
            detector = CoralDetector()
            accessible = detector.verify_device_accessible(coral_device_google)
            
            assert accessible is False

    def test_verify_device_accessible_no_path(self, coral_device_not_found):
        """Test device accessibility check with no device path."""
        detector = CoralDetector()
        accessible = detector.verify_device_accessible(coral_device_not_found)
        
        assert accessible is False

    def test_wait_for_mode_change_success(self, lsusb_unichip_mode, lsusb_google_mode):
        """Test waiting for mode change success."""
        with mock.patch('subprocess.run') as mock_run, \
             mock.patch('time.sleep') as mock_sleep:
            
            # First call returns Unichip, second returns Google
            mock_run.side_effect = [
                mock.MagicMock(stdout=lsusb_unichip_mode, returncode=0),
                mock.MagicMock(stdout=lsusb_google_mode, returncode=0)
            ]
            
            detector = CoralDetector()
            device = detector.wait_for_mode_change(CoralMode.GOOGLE, timeout=5)
            
            assert device.mode == CoralMode.GOOGLE
            assert mock_run.call_count == 2
            mock_sleep.assert_called_once_with(1)

    def test_wait_for_mode_change_timeout(self, lsusb_unichip_mode):
        """Test waiting for mode change timeout."""
        with mock.patch('subprocess.run') as mock_run, \
             mock.patch('time.sleep') as mock_sleep, \
             mock.patch('time.time') as mock_time:
            
            # Mock time progression
            mock_time.side_effect = [0, 1, 2, 3, 4, 5, 6]  # Exceed 5 second timeout
            mock_run.return_value.stdout = lsusb_unichip_mode
            mock_run.return_value.returncode = 0
            
            detector = CoralDetector()
            
            with pytest.raises(DeviceNotFoundError, match="did not reach GOOGLE mode within 5 seconds"):
                detector.wait_for_mode_change(CoralMode.GOOGLE, timeout=5)

    @pytest.mark.parametrize("bus,device,expected_path", [
        ("001", "002", "/dev/bus/usb/001/002"),
        ("003", "004", "/dev/bus/usb/003/004"),
        ("010", "020", "/dev/bus/usb/010/020"),
    ])
    def test_device_path_parsing(self, bus, device, expected_path):
        """Test device path parsing for various bus/device combinations."""
        lsusb_output = f"Bus {bus} Device {device}: ID 18d1:9302 Google Inc."
        
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = lsusb_output
            mock_run.return_value.returncode = 0
            
            detector = CoralDetector()
            coral_device = detector.detect_coral()
            
            assert coral_device.device_path == expected_path
            assert coral_device.bus == bus
            assert coral_device.device == device

    def test_parse_usb_line_edge_cases(self):
        """Test USB line parsing edge cases."""
        detector = CoralDetector()
        
        # Test with extra whitespace
        usb_output = "   Bus 003 Device 004: ID 18d1:9302 Google Inc.   \n"
        device = detector._parse_usb_line(usb_output, CoralMode.GOOGLE)
        assert device is not None
        assert device.description == "Google Inc."
        
        # Test with no match
        usb_output = "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub"
        device = detector._parse_usb_line(usb_output, CoralMode.GOOGLE)
        assert device is None
        
        # Test with NOT_FOUND mode
        device = detector._parse_usb_line(usb_output, CoralMode.NOT_FOUND)
        assert device is None

    def test_detection_logging(self, lsusb_google_mode, caplog):
        """Test that detection produces appropriate log messages."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = lsusb_google_mode
            mock_run.return_value.returncode = 0
            
            detector = CoralDetector()
            detector.detect_coral()
            
            assert "Detecting Coral TPU device" in caplog.text
            assert "Coral detected in Google mode" in caplog.text

    def test_concurrent_detection_calls(self, lsusb_google_mode):
        """Test that concurrent detection calls work correctly."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = lsusb_google_mode
            mock_run.return_value.returncode = 0
            
            detector = CoralDetector()
            
            # Multiple concurrent calls should work
            device1 = detector.detect_coral()
            device2 = detector.detect_coral()
            
            assert device1.mode == device2.mode == CoralMode.GOOGLE
            assert device1.device_path == device2.device_path
            assert mock_run.call_count == 2  # Each call runs lsusb