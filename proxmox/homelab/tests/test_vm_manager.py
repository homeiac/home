from unittest import mock

import pytest


def import_vm_manager(monkeypatch, tmp_path):
    ssh_key = tmp_path / "id_rsa.pub"
    ssh_key.write_text("ssh-rsa AAAA")
    monkeypatch.setenv("SSH_PUBKEY_PATH", str(ssh_key))
    monkeypatch.setenv("API_TOKEN", "user!token=abc")
    from homelab.vm_manager import VMManager
    return VMManager


def test_get_next_available_vmid(monkeypatch, tmp_path):
    VMManager = import_vm_manager(monkeypatch, tmp_path)

    proxmox = mock.MagicMock()
    proxmox.nodes.get.return_value = [{"node": "pve1"}, {"node": "pve2"}]
    proxmox.nodes.return_value.qemu.get.side_effect = [[{"vmid": 100}, {"vmid": 101}], [{"vmid": 200}]]
    proxmox.nodes.return_value.lxc.get.side_effect = [[], []]

    vmid = VMManager.get_next_available_vmid(proxmox)
    assert vmid not in {100, 101, 200}
