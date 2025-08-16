"""Test fixtures for Coral TPU automation."""

from pathlib import Path
from typing import Dict, Any
from unittest import mock

import pytest

from homelab.coral_models import (
    CoralDevice, 
    CoralMode, 
    ContainerStatus, 
    LXCConfig,
    SystemState,
    ActionType,
    AutomationPlan
)


# USB Output Fixtures
@pytest.fixture
def lsusb_google_mode() -> str:
    """lsusb output with Coral in Google mode."""
    return """Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
Bus 001 Device 003: ID 8087:0aaa Intel Corp. Bluetooth 9460/9560 Jefferson Peak (JfP)
Bus 003 Device 004: ID 18d1:9302 Google Inc. 
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub"""


@pytest.fixture
def lsusb_unichip_mode() -> str:
    """lsusb output with Coral in Unichip mode."""
    return """Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
Bus 001 Device 003: ID 8087:0aaa Intel Corp. Bluetooth 9460/9560 Jefferson Peak (JfP)
Bus 003 Device 003: ID 1a6e:089a Global Unichip Corp.
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub"""


@pytest.fixture
def lsusb_no_coral() -> str:
    """lsusb output without Coral device."""
    return """Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
Bus 001 Device 003: ID 8087:0aaa Intel Corp. Bluetooth 9460/9560 Jefferson Peak (JfP)
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub"""


@pytest.fixture
def lsusb_multiple_devices() -> str:
    """lsusb output with multiple Coral devices (error condition)."""
    return """Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
Bus 003 Device 003: ID 1a6e:089a Global Unichip Corp.
Bus 003 Device 004: ID 18d1:9302 Google Inc. 
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub"""


# Container Status Fixtures
@pytest.fixture
def pct_status_running() -> str:
    """pct status output for running container."""
    return "status: running"


@pytest.fixture
def pct_status_stopped() -> str:
    """pct status output for stopped container."""
    return "status: stopped"


@pytest.fixture
def pct_status_error() -> str:
    """pct status output for error condition."""
    return "status: error"


# LXC Config Fixtures
@pytest.fixture
def lxc_config_correct() -> str:
    """LXC config with correct Coral device configuration."""
    return """arch: amd64
cores: 4
hostname: frigate
memory: 4096
mp0: local-1TB-backup:subvol-113-disk-0,mp=/media,backup=1,size=200G
net0: name=eth0,bridge=vmbr0,hwaddr=BC:24:11:1F:05:27,ip=dhcp,type=veth
onboot: 1
ostype: debian
rootfs: local:113/vm-113-disk-0.raw,size=20G
swap: 512
tags: community-script;nvr
dev0: /dev/bus/usb/003/004
lxc.cgroup2.devices.allow: c 189:* rwm
lxc.cap.drop: 
lxc.cgroup2.devices.allow: c 188:* rwm
lxc.cgroup2.devices.allow: c 189:* rwm"""


@pytest.fixture
def lxc_config_wrong_device() -> str:
    """LXC config with wrong device path."""
    return """arch: amd64
cores: 4
hostname: frigate
memory: 4096
net0: name=eth0,bridge=vmbr0,hwaddr=BC:24:11:1F:05:27,ip=dhcp,type=veth
onboot: 1
ostype: debian
rootfs: local:113/vm-113-disk-0.raw,size=20G
swap: 512
dev0: /dev/bus/usb/003/005
lxc.cgroup2.devices.allow: c 189:* rwm"""


@pytest.fixture
def lxc_config_missing_dev0() -> str:
    """LXC config missing dev0 line."""
    return """arch: amd64
cores: 4
hostname: frigate
memory: 4096
net0: name=eth0,bridge=vmbr0,hwaddr=BC:24:11:1F:05:27,ip=dhcp,type=veth
onboot: 1
ostype: debian
rootfs: local:113/vm-113-disk-0.raw,size=20G
swap: 512
lxc.cgroup2.devices.allow: c 189:* rwm"""


@pytest.fixture
def lxc_config_missing_usb_perms() -> str:
    """LXC config missing USB permissions."""
    return """arch: amd64
cores: 4
hostname: frigate
memory: 4096
net0: name=eth0,bridge=vmbr0,hwaddr=BC:24:11:1F:05:27,ip=dhcp,type=veth
onboot: 1
ostype: debian
rootfs: local:113/vm-113-disk-0.raw,size=20G
swap: 512
dev0: /dev/bus/usb/003/004"""


# CoralDevice Fixtures
@pytest.fixture
def coral_device_google() -> CoralDevice:
    """Coral device in Google mode."""
    return CoralDevice(
        mode=CoralMode.GOOGLE,
        bus="003",
        device="004",
        device_path="/dev/bus/usb/003/004",
        description="Google Inc."
    )


@pytest.fixture
def coral_device_unichip() -> CoralDevice:
    """Coral device in Unichip mode."""
    return CoralDevice(
        mode=CoralMode.UNICHIP,
        bus="003",
        device="003",
        device_path="/dev/bus/usb/003/003",
        description="Global Unichip Corp."
    )


@pytest.fixture
def coral_device_not_found() -> CoralDevice:
    """No Coral device detected."""
    return CoralDevice(mode=CoralMode.NOT_FOUND)


# LXCConfig Fixtures
@pytest.fixture
def lxc_config_optimal() -> LXCConfig:
    """Optimal LXC configuration."""
    return LXCConfig(
        container_id="113",
        config_path=Path("/etc/pve/lxc/113.conf"),
        current_dev0="/dev/bus/usb/003/004",
        has_usb_permissions=True,
        status=ContainerStatus.RUNNING
    )


@pytest.fixture
def lxc_config_wrong_path() -> LXCConfig:
    """LXC config with wrong device path."""
    return LXCConfig(
        container_id="113",
        config_path=Path("/etc/pve/lxc/113.conf"),
        current_dev0="/dev/bus/usb/003/005",
        has_usb_permissions=True,
        status=ContainerStatus.RUNNING
    )


@pytest.fixture
def lxc_config_stopped() -> LXCConfig:
    """LXC config with stopped container."""
    return LXCConfig(
        container_id="113",
        config_path=Path("/etc/pve/lxc/113.conf"),
        current_dev0="/dev/bus/usb/003/004",
        has_usb_permissions=True,
        status=ContainerStatus.STOPPED
    )


# SystemState Fixtures
@pytest.fixture
def system_state_optimal(coral_device_google, lxc_config_optimal) -> SystemState:
    """Optimal system state - no action needed."""
    return SystemState(
        coral=coral_device_google,
        lxc=lxc_config_optimal,
        frigate_using_tpu=True
    )


@pytest.fixture
def system_state_needs_init(coral_device_unichip, lxc_config_stopped) -> SystemState:
    """System state where Coral needs initialization."""
    return SystemState(
        coral=coral_device_unichip,
        lxc=lxc_config_stopped,
        frigate_using_tpu=False
    )


@pytest.fixture
def system_state_config_mismatch(coral_device_google, lxc_config_wrong_path) -> SystemState:
    """System state where config doesn't match device."""
    return SystemState(
        coral=coral_device_google,
        lxc=lxc_config_wrong_path,
        frigate_using_tpu=False
    )


@pytest.fixture
def system_state_unsafe_init(coral_device_unichip, lxc_config_optimal) -> SystemState:
    """System state where initialization would be unsafe."""
    return SystemState(
        coral=coral_device_unichip,
        lxc=lxc_config_optimal,
        frigate_using_tpu=True
    )


# Mock Scenarios for Parametric Testing
@pytest.fixture
def mock_scenarios() -> Dict[str, Dict[str, Any]]:
    """Complete set of mock scenarios for parametric testing."""
    return {
        "optimal_no_action": {
            "lsusb_output": "Bus 003 Device 004: ID 18d1:9302 Google Inc.",
            "pct_status": "status: running",
            "config_content": "dev0: /dev/bus/usb/003/004\nlxc.cgroup2.devices.allow: c 189:* rwm",
            "expected_actions": [ActionType.NO_ACTION],
            "expected_safe": True
        },
        "coral_needs_init": {
            "lsusb_output": "Bus 003 Device 003: ID 1a6e:089a Global Unichip Corp.",
            "pct_status": "status: stopped",
            "config_content": "# empty config",
            "expected_actions": [ActionType.INITIALIZE_CORAL, ActionType.UPDATE_CONFIG],
            "expected_safe": True
        },
        "config_mismatch": {
            "lsusb_output": "Bus 003 Device 004: ID 18d1:9302 Google Inc.",
            "pct_status": "status: running",
            "config_content": "dev0: /dev/bus/usb/003/005\nlxc.cgroup2.devices.allow: c 189:* rwm",
            "expected_actions": [ActionType.UPDATE_CONFIG, ActionType.RESTART_CONTAINER],
            "expected_safe": True
        },
        "unsafe_init_running_container": {
            "lsusb_output": "Bus 003 Device 003: ID 1a6e:089a Global Unichip Corp.",
            "pct_status": "status: running",
            "config_content": "dev0: /dev/bus/usb/003/004\nlxc.cgroup2.devices.allow: c 189:* rwm",
            "expected_actions": [ActionType.ERROR_ABORT],
            "expected_safe": False
        },
        "safety_violation_google_mode": {
            "lsusb_output": "Bus 003 Device 004: ID 18d1:9302 Google Inc.",
            "pct_status": "status: running",
            "config_content": "dev0: /dev/bus/usb/003/004\nlxc.cgroup2.devices.allow: c 189:* rwm",
            "force_init": True,
            "expected_actions": [ActionType.ERROR_ABORT],
            "expected_safe": False
        },
        "no_coral_detected": {
            "lsusb_output": "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub",
            "pct_status": "status: stopped",
            "config_content": "# empty config",
            "expected_actions": [ActionType.ERROR_ABORT],
            "expected_safe": False
        },
        "container_stopped_correct_config": {
            "lsusb_output": "Bus 003 Device 004: ID 18d1:9302 Google Inc.",
            "pct_status": "status: stopped",
            "config_content": "dev0: /dev/bus/usb/003/004\nlxc.cgroup2.devices.allow: c 189:* rwm",
            "expected_actions": [ActionType.RESTART_CONTAINER],
            "expected_safe": True
        },
        "missing_usb_permissions": {
            "lsusb_output": "Bus 003 Device 004: ID 18d1:9302 Google Inc.",
            "pct_status": "status: running",
            "config_content": "dev0: /dev/bus/usb/003/004",
            "expected_actions": [ActionType.UPDATE_CONFIG, ActionType.RESTART_CONTAINER],
            "expected_safe": True
        }
    }


# Mock Subprocess Results
@pytest.fixture
def mock_successful_init_output() -> str:
    """Mock output from successful Coral initialization."""
    return """----INFERENCE TIME----
Note: The first inference on Edge TPU is slow because it includes
loading the model into Edge TPU memory.
13.6ms
3.0ms
2.8ms
2.9ms
2.9ms
-------RESULTS--------
Ara macao (Scarlet Macaw): 0.77734"""


@pytest.fixture
def mock_failed_init_output() -> str:
    """Mock output from failed Coral initialization."""
    return "RuntimeError: Failed to load model on Edge TPU"


# Comprehensive Mock Fixture for subprocess.run
@pytest.fixture
def mock_subprocess(mock_scenarios):
    """Comprehensive mock for subprocess.run with scenario-based responses."""
    def _mock_run(cmd, **kwargs):
        result = mock.MagicMock()
        result.returncode = 0
        
        # Determine current scenario from test context
        scenario = getattr(_mock_run, 'current_scenario', 'optimal_no_action')
        scenario_data = mock_scenarios.get(scenario, mock_scenarios['optimal_no_action'])
        
        cmd_str = ' '.join(cmd) if isinstance(cmd, list) else str(cmd)
        
        if 'lsusb' in cmd_str:
            result.stdout = scenario_data['lsusb_output']
        elif 'pct status' in cmd_str:
            result.stdout = scenario_data['pct_status']
        elif 'classify_image.py' in cmd_str:
            result.stdout = """----INFERENCE TIME----
13.6ms
-------RESULTS--------
Ara macao (Scarlet Macaw): 0.77734"""
        else:
            result.stdout = "mock output"
        
        result.stderr = ""
        return result
    
    with mock.patch('subprocess.run', side_effect=_mock_run) as mock_run:
        mock_run.current_scenario = 'optimal_no_action'
        yield mock_run


# File System Mocks
@pytest.fixture
def mock_file_system(tmp_path, mock_scenarios):
    """Mock file system with scenario-based config files."""
    def _setup_scenario(scenario_name: str):
        scenario_data = mock_scenarios[scenario_name]
        
        # Create config file
        config_file = tmp_path / "113.conf"
        config_file.write_text(scenario_data['config_content'])
        
        # Create required directories
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        coral_dir = tmp_path / "coral"
        coral_dir.mkdir(exist_ok=True)
        
        # Create required coral files
        (coral_dir / "pycoral" / "examples").mkdir(parents=True)
        (coral_dir / "pycoral" / "examples" / "classify_image.py").write_text("# mock script")
        
        test_data_dir = tmp_path / "test_data"
        test_data_dir.mkdir(exist_ok=True)
        (test_data_dir / "mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite").write_text("mock model")
        (test_data_dir / "inat_bird_labels.txt").write_text("mock labels")
        (test_data_dir / "parrot.jpg").write_text("mock image")
        
        return {
            'config_path': config_file,
            'backup_dir': backup_dir,
            'coral_dir': coral_dir
        }
    
    return _setup_scenario