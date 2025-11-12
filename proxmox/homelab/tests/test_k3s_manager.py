"""Tests for k3s_manager module."""
import pytest
from unittest import mock
import subprocess
from homelab.k3s_manager import K3sManager


class TestK3sManager:
    def test_get_cluster_token_from_existing_node(self):
        """Should retrieve token via SSH from existing node."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=0,
                stdout=b'K10abc123::server:def456\n'
            )

            manager = K3sManager()
            token = manager.get_cluster_token("192.168.4.212")

            assert token == "K10abc123::server:def456"
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "ssh" in cmd
            assert "ubuntu@192.168.4.212" in ' '.join(cmd)
            assert "/var/lib/rancher/k3s/server/node-token" in ' '.join(cmd)

    def test_get_cluster_token_handles_ssh_failure(self):
        """Should raise RuntimeError on SSH failure."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                255, "ssh", stderr=b"Permission denied"
            )

            manager = K3sManager()

            with pytest.raises(RuntimeError, match="Failed to get k3s token"):
                manager.get_cluster_token("192.168.4.212")

    def test_node_in_cluster_returns_true_when_exists(self):
        """Should return True when node is in cluster."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=0,
                stdout='{"items": [{"metadata": {"name": "k3s-vm-test"}}]}'
            )

            manager = K3sManager()
            result = manager.node_in_cluster("k3s-vm-test")

            assert result is True

    def test_node_in_cluster_returns_false_when_not_exists(self):
        """Should return False when node not in cluster."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=0,
                stdout='{"items": [{"metadata": {"name": "other-node"}}]}'
            )

            manager = K3sManager()
            result = manager.node_in_cluster("k3s-vm-test")

            assert result is False

    def test_get_cluster_token_handles_timeout(self):
        """Should raise RuntimeError on SSH timeout."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("ssh", 30)

            manager = K3sManager()

            with pytest.raises(RuntimeError, match="Timeout getting k3s token"):
                manager.get_cluster_token("192.168.4.212")

    def test_node_in_cluster_handles_kubectl_error(self):
        """Should return False when kubectl fails."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=1,
                stderr="connection refused"
            )

            manager = K3sManager()
            result = manager.node_in_cluster("k3s-vm-test")

            assert result is False

    def test_node_in_cluster_handles_timeout(self):
        """Should return False on kubectl timeout."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("kubectl", 30)

            manager = K3sManager()
            result = manager.node_in_cluster("k3s-vm-test")

            assert result is False

    def test_node_in_cluster_handles_json_decode_error(self):
        """Should return False on invalid JSON response."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=0,
                stdout='not valid json'
            )

            manager = K3sManager()
            result = manager.node_in_cluster("k3s-vm-test")

            assert result is False

    def test_node_in_cluster_handles_missing_items_key(self):
        """Should return False when items key missing."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=0,
                stdout='{"metadata": {}}'
            )

            manager = K3sManager()
            result = manager.node_in_cluster("k3s-vm-test")

            assert result is False

    def test_install_k3s_on_new_node(self):
        """Should install k3s and join cluster."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0)

            manager = K3sManager()
            result = manager.install_k3s(
                vm_hostname="k3s-vm-test",
                token="K10abc::server:def",
                server_url="https://192.168.4.212:6443"
            )

            assert result is True
            # Verify curl | sh command was executed
            cmd_str = ' '.join(mock_run.call_args[0][0])
            assert "ssh" in cmd_str
            assert "ubuntu@k3s-vm-test" in cmd_str
            assert "curl -sfL https://get.k3s.io" in cmd_str
            assert "K3S_TOKEN" in cmd_str
            assert "K3S_URL" in cmd_str
            assert "https://192.168.4.212:6443" in cmd_str

    def test_install_k3s_handles_failure(self):
        """Should raise RuntimeError on installation failure."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "ssh", stderr=b"Installation failed"
            )

            manager = K3sManager()

            with pytest.raises(RuntimeError, match="Failed to install k3s"):
                manager.install_k3s("k3s-vm-test", "token", "https://server:6443")

    def test_install_k3s_handles_timeout(self):
        """Should raise RuntimeError on installation timeout."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("ssh", 300)

            manager = K3sManager()

            with pytest.raises(RuntimeError, match="K3s installation timeout"):
                manager.install_k3s("k3s-vm-test", "token", "https://server:6443")
