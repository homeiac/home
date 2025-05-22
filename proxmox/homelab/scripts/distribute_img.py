#!/usr/bin/env python3
import os
import sys
import paramiko

from homelab.config import Config  # assumes Config loads .env itself

# ─── Configuration ───────────────────────────────────────────────────────────
pve_ips = Config.PVE_IPS
if len(pve_ips) < 2:
    print("❌ ERROR: PVE_IPS must contain at least two comma-separated entries.", file=sys.stderr)
    sys.exit(1)

PRIMARY_IP = pve_ips[1]  # jump/primary host (e.g. 192.168.1.122)
SSH_USER   = os.getenv("SSH_USER", "root")
SSH_KEY    = os.path.expanduser(os.getenv("SSH_KEY_PATH", "~/.ssh/id_rsa"))

ISO_URL     = Config.ISO_URL
IMAGE_NAME  = Config.ISO_NAME
REMOTE_DIR  = "/var/lib/vz/template/iso"
REMOTE_PATH = f"{REMOTE_DIR}/{IMAGE_NAME}"

# ─── Helper Functions ─────────────────────────────────────────────────────────
def ssh_connect(host):
    print(f"🔑 SSH → {host} as {SSH_USER}")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=SSH_USER, key_filename=SSH_KEY)
    return client

def exec_on(ssh, cmd):
    peer = ssh.get_transport().getpeername()[0]
    print(f"[{peer}]$ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
    return out, err

# ─── Main Flow ────────────────────────────────────────────────────────────────
def main():
    # 1) Connect to primary/jump host
    ssh = ssh_connect(PRIMARY_IP)

    # 2) Ensure ISO directory exists
    exec_on(ssh, f"mkdir -p {REMOTE_DIR}")

    # 3) Download ISO on primary if missing
    status, _ = exec_on(ssh, f"test -f {REMOTE_PATH} && echo exists || echo missing")
    if "missing" in status:
        print(f"⬇️  Downloading {IMAGE_NAME} on {PRIMARY_IP}")
        exec_on(ssh, f"curl -L {ISO_URL} -o {REMOTE_PATH}")
    else:
        print(f"ℹ️  {IMAGE_NAME} already present on {PRIMARY_IP}; skipping download.")

    # 4) Distribute to every host in Config.get_nodes()
    for node in Config.get_nodes():
        host = node["name"]
        print(f"➡️  SCP → {host}:{REMOTE_DIR}")
        scp_cmd = (
            f"scp -o StrictHostKeyChecking=no "
            f"{REMOTE_PATH} "
            f"{SSH_USER}@{host}:{REMOTE_DIR}/"
        )
        exec_on(ssh, scp_cmd)

    ssh.close()
    print("✅ All hosts have the cloud-init image.")

if __name__ == "__main__":
    main()
