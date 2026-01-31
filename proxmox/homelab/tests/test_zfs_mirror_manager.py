"""Tests for zfs_mirror_manager module."""

import textwrap
from pathlib import Path
from unittest import mock

import pytest
import yaml

from homelab.zfs_mirror_manager import ZfsMirrorManager, load_cluster_config


# -- fixtures --

SAMPLE_CONFIG = {
    "nodes": [
        {
            "name": "still-fawn",
            "ip": "192.168.4.17",
            "fqdn": "still-fawn.maas",
            "enabled": True,
            "zfs_mirrors": [
                {
                    "pool": "rpool",
                    "existing_disk": "ata-T-FORCE_2TB_TPBF2211070040100214",
                    "new_disk": "ata-T-FORCE_2TB_TPBF2509220070101290",
                    "zfs_partition": 3,
                    "efi_partition": 2,
                    "bios_boot_partition": 1,
                }
            ],
        }
    ],
}

EXISTING_DISK = "ata-T-FORCE_2TB_TPBF2211070040100214"
NEW_DISK = "ata-T-FORCE_2TB_TPBF2509220070101290"

ZPOOL_STATUS_SINGLE = textwrap.dedent("""\
    pool: rpool
     state: ONLINE
      scan: scrub repaired 0B in 00:02:30 with 0 errors on Sun Jan 12 00:26:31 2026
    config:

    \tNAME                                                  STATE     READ WRITE CKSUM
    \trpool                                                 ONLINE       0     0     0
    \t  ata-T-FORCE_2TB_TPBF2211070040100214-part3          ONLINE       0     0     0

    errors: No known data errors
""")

ZPOOL_STATUS_MIRROR = textwrap.dedent("""\
    pool: rpool
     state: ONLINE
      scan: resilver in progress since Fri Jan 31 10:00:00 2026
    config:

    \tNAME                                                  STATE     READ WRITE CKSUM
    \trpool                                                 ONLINE       0     0     0
    \t  mirror-0                                            ONLINE       0     0     0
    \t    ata-T-FORCE_2TB_TPBF2211070040100214-part3        ONLINE       0     0     0
    \t    ata-T-FORCE_2TB_TPBF2509220070101290-part3        ONLINE       0     0     0

    errors: No known data errors
""")

ZPOOL_STATUS_MIRROR_COMPLETE = textwrap.dedent("""\
    pool: rpool
     state: ONLINE
      scan: resilver completed on Fri Jan 31 12:00:00 2026
    config:

    \tNAME                                                  STATE     READ WRITE CKSUM
    \trpool                                                 ONLINE       0     0     0
    \t  mirror-0                                            ONLINE       0     0     0
    \t    ata-T-FORCE_2TB_TPBF2211070040100214-part3        ONLINE       0     0     0
    \t    ata-T-FORCE_2TB_TPBF2509220070101290-part3        ONLINE       0     0     0

    errors: No known data errors
""")

SGDISK_EXISTING = textwrap.dedent("""\
    Disk /dev/disk/by-id/ata-T-FORCE_2TB_TPBF2211070040100214: 3907029168 sectors, 1.8 TiB
    Disk identifier (GUID): AAAA1111-2222-3333-4444-555566667777
    Number  Start (sector)    End (sector)  Size       Code  Name
       1            2048         1048575   511.0 MiB   EF02  BIOS boot partition
       2         1048576         2097151   512.0 MiB   EF00  EFI System
       3         2097152      3907029134   1.8 TiB     BF00  zfs
""")

SGDISK_NEW_EMPTY = textwrap.dedent("""\
    Disk /dev/disk/by-id/ata-T-FORCE_2TB_TPBF2509220070101290: 3907029168 sectors, 1.8 TiB
    Disk identifier (GUID): BBBB1111-2222-3333-4444-555566667777
    Number  Start (sector)    End (sector)  Size       Code  Name
""")

SGDISK_NEW_CLONED_SAME_GUID = textwrap.dedent("""\
    Disk /dev/disk/by-id/ata-T-FORCE_2TB_TPBF2509220070101290: 3907029168 sectors, 1.8 TiB
    Disk identifier (GUID): AAAA1111-2222-3333-4444-555566667777
    Number  Start (sector)    End (sector)  Size       Code  Name
       1            2048         1048575   511.0 MiB   EF02  BIOS boot partition
       2         1048576         2097151   512.0 MiB   EF00  EFI System
       3         2097152      3907029134   1.8 TiB     BF00  zfs
""")

SGDISK_NEW_CLONED_DIFF_GUID = textwrap.dedent("""\
    Disk /dev/disk/by-id/ata-T-FORCE_2TB_TPBF2509220070101290: 3907029168 sectors, 1.8 TiB
    Disk identifier (GUID): CCCC1111-2222-3333-4444-555566667777
    Number  Start (sector)    End (sector)  Size       Code  Name
       1            2048         1048575   511.0 MiB   EF02  BIOS boot partition
       2         1048576         2097151   512.0 MiB   EF00  EFI System
       3         2097152      3907029134   1.8 TiB     BF00  zfs
""")

BOOT_TOOL_STATUS_SINGLE = textwrap.dedent("""\
    Re-executing '/usr/sbin/proxmox-boot-tool' in new private mount namespace..
    System currently booted with uefi
    E1AE: /dev/disk/by-id/ata-T-FORCE_2TB_TPBF2211070040100214-part2
""")

BOOT_TOOL_STATUS_BOTH = textwrap.dedent("""\
    Re-executing '/usr/sbin/proxmox-boot-tool' in new private mount namespace..
    System currently booted with uefi
    E1AE: /dev/disk/by-id/ata-T-FORCE_2TB_TPBF2211070040100214-part2
    F2BF: /dev/disk/by-id/ata-T-FORCE_2TB_TPBF2509220070101290-part2
""")


def _make_exec_return(stdout_text: str, stderr_text: str = "", rc: int = 0):
    """Build a mock (stdin, stdout, stderr) tuple for exec_command."""
    stdout = mock.MagicMock()
    stderr = mock.MagicMock()
    stdout.read.return_value.decode.return_value = stdout_text
    stderr.read.return_value.decode.return_value = stderr_text
    stdout.channel.recv_exit_status.return_value = rc
    return (None, stdout, stderr)


@pytest.fixture
def mock_ssh():
    """Patch paramiko.SSHClient so no real SSH happens."""
    with mock.patch("paramiko.SSHClient") as mock_cls:
        client = mock.MagicMock()
        mock_cls.return_value = client
        # Default: succeed with empty output
        client.exec_command.return_value = _make_exec_return("")
        yield client


@pytest.fixture
def manager(mock_ssh):
    """ZfsMirrorManager for still-fawn with mocked SSH."""
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        mgr = ZfsMirrorManager("still-fawn", config=SAMPLE_CONFIG)
        yield mgr
        mgr.cleanup()


@pytest.fixture
def mirror_cfg():
    """Convenience: the single mirror config dict."""
    return SAMPLE_CONFIG["nodes"][0]["zfs_mirrors"][0]


# -- init tests --

def test_init_valid_host(mock_ssh):
    mgr = ZfsMirrorManager("still-fawn", config=SAMPLE_CONFIG)
    assert mgr.hostname == "still-fawn"
    assert len(mgr._mirrors) == 1
    assert mgr._mirrors[0]["pool"] == "rpool"


def test_init_unknown_host(mock_ssh):
    with pytest.raises(ValueError, match="not found in cluster config"):
        ZfsMirrorManager("nonexistent", config=SAMPLE_CONFIG)


def test_init_no_mirrors(mock_ssh):
    config = {"nodes": [{"name": "bare-host", "ip": "1.2.3.4"}]}
    mgr = ZfsMirrorManager("bare-host", config=config)
    assert mgr._mirrors == []


# -- context manager --

def test_context_manager(mock_ssh):
    with mock.patch("socket.gethostbyname", return_value="192.168.4.17"):
        with ZfsMirrorManager("still-fawn", config=SAMPLE_CONFIG) as mgr:
            assert mgr.hostname == "still-fawn"


# -- state detection --

def test_get_pool_topology_single(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_SINGLE)
    topo = manager.get_pool_topology("rpool")
    assert topo["state"] == "ONLINE"
    assert topo["is_mirror"] is False
    assert EXISTING_DISK + "-part3" in topo["vdev_disks"][0]


def test_get_pool_topology_mirror(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_MIRROR)
    topo = manager.get_pool_topology("rpool")
    assert topo["state"] == "ONLINE"
    assert topo["is_mirror"] is True
    assert len(topo["vdev_disks"]) == 2


def test_get_pool_topology_missing(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return("", "no such pool", 1)
    topo = manager.get_pool_topology("rpool")
    assert topo["state"] == "MISSING"


def test_is_already_mirror_false(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_SINGLE)
    assert manager.is_already_mirror("rpool") is False


def test_is_already_mirror_true(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_MIRROR)
    assert manager.is_already_mirror("rpool") is True


def test_disk_exists_true(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return("", "", 0)
    assert manager.disk_exists(EXISTING_DISK) is True


def test_disk_exists_false(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return("", "not found", 1)
    assert manager.disk_exists("ata-nonexistent") is False


def test_partitions_match_true(manager, mock_ssh):
    def side_effect(cmd):
        if EXISTING_DISK in cmd:
            return _make_exec_return(SGDISK_EXISTING)
        return _make_exec_return(SGDISK_NEW_CLONED_DIFF_GUID)
    mock_ssh.exec_command.side_effect = side_effect
    assert manager.partitions_match(EXISTING_DISK, NEW_DISK) is True


def test_partitions_match_false(manager, mock_ssh):
    def side_effect(cmd):
        if EXISTING_DISK in cmd:
            return _make_exec_return(SGDISK_EXISTING)
        return _make_exec_return(SGDISK_NEW_EMPTY)
    mock_ssh.exec_command.side_effect = side_effect
    assert manager.partitions_match(EXISTING_DISK, NEW_DISK) is False


def test_guids_differ_true(manager, mock_ssh):
    def side_effect(cmd):
        if EXISTING_DISK in cmd:
            return _make_exec_return(SGDISK_EXISTING)
        return _make_exec_return(SGDISK_NEW_CLONED_DIFF_GUID)
    mock_ssh.exec_command.side_effect = side_effect
    assert manager.guids_differ(EXISTING_DISK, NEW_DISK) is True


def test_guids_differ_false_same(manager, mock_ssh):
    def side_effect(cmd):
        if EXISTING_DISK in cmd:
            return _make_exec_return(SGDISK_EXISTING)
        return _make_exec_return(SGDISK_NEW_CLONED_SAME_GUID)
    mock_ssh.exec_command.side_effect = side_effect
    assert manager.guids_differ(EXISTING_DISK, NEW_DISK) is False


def test_boot_configured_false(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return(BOOT_TOOL_STATUS_SINGLE)
    assert manager.boot_configured(NEW_DISK, 2) is False


def test_boot_configured_true(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return(BOOT_TOOL_STATUS_BOTH)
    assert manager.boot_configured(NEW_DISK, 2) is True


def test_pool_is_resilvering(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_MIRROR)
    assert manager.pool_is_resilvering("rpool") is True

    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_MIRROR_COMPLETE)
    assert manager.pool_is_resilvering("rpool") is False


def test_disk_in_any_pool(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_SINGLE)
    assert manager.disk_in_any_pool(EXISTING_DISK) is True
    assert manager.disk_in_any_pool(NEW_DISK) is False


def test_required_tools_present(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return("/usr/sbin/sgdisk", "", 0)
    tools = manager.required_tools_present()
    assert tools["sgdisk"] is True
    assert tools["proxmox-boot-tool"] is True
    assert tools["zpool"] is True


# -- pre-flight --

def test_preflight_all_pass(manager, mock_ssh, mirror_cfg):
    calls = []

    def side_effect(cmd):
        calls.append(cmd)
        if cmd.startswith("zpool status rpool"):
            return _make_exec_return(ZPOOL_STATUS_SINGLE)
        if cmd.startswith("test -e"):
            return _make_exec_return("", "", 0)
        if cmd.startswith("zpool status -L"):
            # new disk not in any pool output
            return _make_exec_return(ZPOOL_STATUS_SINGLE)
        if cmd.startswith("lsblk"):
            return _make_exec_return("2000398934016")
        if cmd.startswith("which"):
            return _make_exec_return("/usr/sbin/tool", "", 0)
        return _make_exec_return("")

    mock_ssh.exec_command.side_effect = side_effect
    checks = manager.preflight(mirror_cfg)
    assert checks["pool_online"]["passed"] is True
    assert checks["existing_disk_present"]["passed"] is True
    assert checks["new_disk_present"]["passed"] is True
    assert checks["required_tools"]["passed"] is True


def test_preflight_pool_missing(manager, mock_ssh, mirror_cfg):
    def side_effect(cmd):
        if cmd.startswith("zpool status rpool"):
            return _make_exec_return("", "no such pool", 1)
        if cmd.startswith("test -e"):
            return _make_exec_return("", "", 0)
        if cmd.startswith("zpool status -L"):
            return _make_exec_return("", "no such pool", 1)
        if cmd.startswith("lsblk"):
            return _make_exec_return("2000398934016")
        if cmd.startswith("which"):
            return _make_exec_return("/usr/sbin/tool", "", 0)
        return _make_exec_return("")

    mock_ssh.exec_command.side_effect = side_effect
    checks = manager.preflight(mirror_cfg)
    assert checks["pool_online"]["passed"] is False


# -- operation tests --

def test_clone_partitions_skipped(manager, mock_ssh, mirror_cfg):
    """Skip if partitions already match."""
    def side_effect(cmd):
        if EXISTING_DISK in cmd:
            return _make_exec_return(SGDISK_EXISTING)
        return _make_exec_return(SGDISK_NEW_CLONED_DIFF_GUID)
    mock_ssh.exec_command.side_effect = side_effect
    result = manager.clone_partitions(mirror_cfg)
    assert result["status"] == "skipped"


def test_clone_partitions_dry_run(manager, mock_ssh, mirror_cfg):
    def side_effect(cmd):
        if EXISTING_DISK in cmd:
            return _make_exec_return(SGDISK_EXISTING)
        return _make_exec_return(SGDISK_NEW_EMPTY)
    mock_ssh.exec_command.side_effect = side_effect
    result = manager.clone_partitions(mirror_cfg, dry_run=True)
    assert result["status"] == "would_execute"
    assert "sgdisk -R" in result["cmd"]


def test_clone_partitions_execute(manager, mock_ssh, mirror_cfg):
    call_count = [0]

    def side_effect(cmd):
        call_count[0] += 1
        if "sgdisk -p" in cmd:
            if EXISTING_DISK in cmd:
                return _make_exec_return(SGDISK_EXISTING)
            return _make_exec_return(SGDISK_NEW_EMPTY)
        if "sgdisk -R" in cmd:
            return _make_exec_return("OK", "", 0)
        return _make_exec_return("")

    mock_ssh.exec_command.side_effect = side_effect
    result = manager.clone_partitions(mirror_cfg)
    assert result["status"] == "done"


def test_randomize_guids_skipped(manager, mock_ssh, mirror_cfg):
    def side_effect(cmd):
        if EXISTING_DISK in cmd:
            return _make_exec_return(SGDISK_EXISTING)
        return _make_exec_return(SGDISK_NEW_CLONED_DIFF_GUID)
    mock_ssh.exec_command.side_effect = side_effect
    result = manager.randomize_guids(mirror_cfg)
    assert result["status"] == "skipped"


def test_randomize_guids_execute(manager, mock_ssh, mirror_cfg):
    def side_effect(cmd):
        if "sgdisk -p" in cmd:
            if EXISTING_DISK in cmd:
                return _make_exec_return(SGDISK_EXISTING)
            return _make_exec_return(SGDISK_NEW_CLONED_SAME_GUID)
        if "sgdisk -G" in cmd:
            return _make_exec_return("OK", "", 0)
        return _make_exec_return("")

    mock_ssh.exec_command.side_effect = side_effect
    result = manager.randomize_guids(mirror_cfg)
    assert result["status"] == "done"


def test_setup_boot_skipped(manager, mock_ssh, mirror_cfg):
    mock_ssh.exec_command.return_value = _make_exec_return(BOOT_TOOL_STATUS_BOTH)
    result = manager.setup_boot(mirror_cfg)
    assert result["status"] == "skipped"


def test_setup_boot_dry_run(manager, mock_ssh, mirror_cfg):
    mock_ssh.exec_command.return_value = _make_exec_return(BOOT_TOOL_STATUS_SINGLE)
    result = manager.setup_boot(mirror_cfg, dry_run=True)
    assert result["status"] == "would_execute"
    assert len(result["cmds"]) == 2


def test_setup_boot_execute(manager, mock_ssh, mirror_cfg):
    def side_effect(cmd):
        if "proxmox-boot-tool status" in cmd:
            return _make_exec_return(BOOT_TOOL_STATUS_SINGLE)
        return _make_exec_return("", "", 0)

    mock_ssh.exec_command.side_effect = side_effect
    result = manager.setup_boot(mirror_cfg)
    assert result["status"] == "done"


def test_attach_mirror_skipped(manager, mock_ssh, mirror_cfg):
    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_MIRROR_COMPLETE)
    result = manager.attach_mirror(mirror_cfg)
    assert result["status"] == "skipped"


def test_attach_mirror_dry_run(manager, mock_ssh, mirror_cfg):
    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_SINGLE)
    result = manager.attach_mirror(mirror_cfg, dry_run=True)
    assert result["status"] == "would_execute"
    assert "zpool attach" in result["cmd"]


def test_attach_mirror_execute(manager, mock_ssh, mirror_cfg):
    def side_effect(cmd):
        if cmd.startswith("zpool status"):
            return _make_exec_return(ZPOOL_STATUS_SINGLE)
        if cmd.startswith("zpool attach"):
            return _make_exec_return("", "", 0)
        return _make_exec_return("")

    mock_ssh.exec_command.side_effect = side_effect
    result = manager.attach_mirror(mirror_cfg)
    assert result["status"] == "done"


def test_check_resilver(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_MIRROR)
    result = manager.check_resilver("rpool")
    assert result["is_mirror"] is True
    assert "resilver in progress" in result["scan"]


# -- apply orchestration --

def test_apply_dry_run(manager, mock_ssh, mirror_cfg):
    """Full dry-run: all steps should say would_execute or skipped."""
    def side_effect(cmd):
        # pool status => single
        if cmd.startswith("zpool status"):
            if "-L" in cmd:
                return _make_exec_return(ZPOOL_STATUS_SINGLE)
            return _make_exec_return(ZPOOL_STATUS_SINGLE)
        # disk exists
        if cmd.startswith("test -e"):
            return _make_exec_return("", "", 0)
        # lsblk sizes
        if cmd.startswith("lsblk"):
            return _make_exec_return("2000398934016")
        # which tools
        if cmd.startswith("which"):
            return _make_exec_return("/usr/sbin/tool", "", 0)
        # sgdisk -p for partition checks
        if "sgdisk -p" in cmd:
            if EXISTING_DISK in cmd:
                return _make_exec_return(SGDISK_EXISTING)
            return _make_exec_return(SGDISK_NEW_EMPTY)
        # proxmox-boot-tool status
        if "proxmox-boot-tool status" in cmd:
            return _make_exec_return(BOOT_TOOL_STATUS_SINGLE)
        return _make_exec_return("")

    mock_ssh.exec_command.side_effect = side_effect
    result = manager.apply(dry_run=True)
    assert result["success"] is True
    assert len(result["mirrors"]) == 1
    m = result["mirrors"][0]
    assert m["status"] == "dry_run"
    assert len(m["steps"]) == 4
    for step in m["steps"]:
        assert step["status"] in ("would_execute", "skipped")


def test_apply_already_mirrored(manager, mock_ssh):
    """If both disks already in mirror, everything is skipped."""
    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_MIRROR_COMPLETE)
    result = manager.apply()
    assert result["success"] is True
    m = result["mirrors"][0]
    assert m["status"] == "already_mirrored"


# -- status --

def test_status(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_SINGLE)
    s = manager.status()
    assert s["hostname"] == "still-fawn"
    assert len(s["mirrors"]) == 1
    assert s["mirrors"][0]["pool"] == "rpool"
    assert s["mirrors"][0]["is_mirror"] is False


def test_status_mirror(manager, mock_ssh):
    mock_ssh.exec_command.return_value = _make_exec_return(ZPOOL_STATUS_MIRROR_COMPLETE)
    s = manager.status()
    assert s["mirrors"][0]["is_mirror"] is True


# -- load_cluster_config --

def test_load_cluster_config_not_found():
    with pytest.raises(FileNotFoundError):
        load_cluster_config(Path("/nonexistent/cluster.yaml"))


def test_load_cluster_config_valid(tmp_path):
    cfg = tmp_path / "cluster.yaml"
    cfg.write_text(yaml.dump(SAMPLE_CONFIG))
    result = load_cluster_config(cfg)
    assert result["nodes"][0]["name"] == "still-fawn"
