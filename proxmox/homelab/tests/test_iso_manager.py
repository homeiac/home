from unittest import mock

import pytest


def import_modules(monkeypatch, tmp_path):
    ssh_key = tmp_path / "id_rsa.pub"
    ssh_key.write_text("ssh-rsa AAAA")
    monkeypatch.setenv("SSH_PUBKEY_PATH", str(ssh_key))
    monkeypatch.setenv("API_TOKEN", "user!token=abc")
    from homelab.iso_manager import IsoManager
    from homelab.config import Config
    return IsoManager, Config


def test_download_iso(monkeypatch, tmp_path):
    IsoManager, Config = import_modules(monkeypatch, tmp_path)

    iso_path = tmp_path / "image.iso"
    monkeypatch.setattr(Config, "ISO_NAME", str(iso_path))
    monkeypatch.setattr(Config, "ISO_URL", "http://example.com/test.iso")

    fake_resp = mock.Mock()
    fake_resp.iter_content.return_value = [b"data"]

    with mock.patch("os.path.isfile", return_value=False):
        with mock.patch("requests.get", return_value=fake_resp) as m_get:
            IsoManager.download_iso()
            m_get.assert_called_once_with("http://example.com/test.iso", stream=True)
            assert iso_path.read_bytes() == b"data"


def test_upload_iso_to_nodes(monkeypatch, tmp_path):
    IsoManager, Config = import_modules(monkeypatch, tmp_path)

    node = {"name": "pve", "storage": "local", "img_storage": "local"}
    monkeypatch.setattr(Config, "get_nodes", lambda: [node])

    client = mock.MagicMock()
    client.get_storage_content.return_value = []
    monkeypatch.setattr("homelab.iso_manager.ProxmoxClient", lambda name: client)

    IsoManager.upload_iso_to_nodes()
    client.upload_iso.assert_called_once_with("local", Config.ISO_NAME)
