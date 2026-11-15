# My K3s Cluster Restarted 1,200 Times in One Evening. Restarting It Again Didn't Help.

**Date:** 2026-11-15
**Tags:** k3s, etcd, ipv6, power-outage, rca, homelab, kubernetes, lessons-learned

> After a power cut, every K3s server in my homelab sat in `activating` and restarted about once a
> minute — for hours. etcd looked fine. The API server looked fine. A coordinated restart of all
> servers *looked* like it worked, then fell over again. The real cause was a file K3s wrote during
> the minutes my network had IPv6 but no IPv4, and never rewrote.

## TL;DR

- **Symptom:** `systemctl status k3s` → `activating`, `NRestarts` in the hundreds on every server.
  `kubectl` → `ServiceUnavailable` / `connection refused`. The journal ends each cycle with:
  ```
  Shutdown request received: controller-manager exited: unable to load configmap based
  request-header-client-ca-file: Get "https://[::1]:6444/...": connect: connection refused
  ```
- **Cause:** the servers booted while the router was handing out **IPv6 but not IPv4** (my DHCP
  server is a VM that was still booting). No `node-ip` was configured, so K3s auto-detected an
  **IPv6-only** node and wrote its internal kubeconfigs (`/var/lib/rancher/k3s/server/cred/*.kubeconfig`)
  with `server: https://[::1]:6444`. K3s does **not** regenerate those files on restart. Every later
  boot had IPv4, so the API server listened on `127.0.0.1:6444`, while the controller-manager kept
  dialing `[::1]:6444`, got refused, and took K3s down with it.
- **Fix:** stop K3s on all servers → pin `node-ip` to IPv4 → rewrite `[::1]` → `127.0.0.1` in the
  `cred/*.kubeconfig` files → start all servers together.
- **Tell:** the one server that *didn't* loop was the one whose `controller.kubeconfig` said `127.0.0.1`.

Everything is in one idempotent script: [`scripts/k3s/restart-all-servers.sh`](../../scripts/k3s/restart-all-servers.sh).

## The setup (aliases)

| Alias | What it is |
|---|---|
| `<server-1..4>` | K3s **server** nodes (embedded etcd), each a VM on a different Proxmox host |
| `<pve-host-N>` | Proxmox host running `<server-N>` |
| `<dhcp-vm>` | The DHCP/DNS server for the LAN — itself a VM on one of the Proxmox hosts |
| `<isp-router>` | Upstream router that sends IPv6 router advertisements (RA) on the same LAN |

Four servers with embedded etcd means quorum is 3. Nothing exotic: stock K3s, `config.yaml` with
`tls-san` and `disable: servicelb`, **no `node-ip`**.

## What it looked like

```text
$ ./restart-all-servers.sh --check
  <server-1>: activating restarts=386 loopback=https://[::1]:6444     node-ip=
  <server-2>: active     restarts=185 loopback=https://127.0.0.1:6444 node-ip=
  <server-3>: activating restarts=450 loopback=https://[::1]:6444     node-ip=
  <server-4>: activating restarts=199 loopback=https://[::1]:6444     node-ip=
```

About 1,200 restarts across the cluster in under five hours. Each one: etcd starts, the API
server starts, the controller-manager tries to load its config from the API server, fails, and the
K3s supervisor shuts everything down. systemd restarts it. Repeat.

## Red herrings I chased first

1. **"It's an etcd quorum problem."** The logs are full of etcd noise: `starting a new election`,
   `prober detected unhealthy status`, `rejected connection on peer endpoint`. That's real, but it's
   a *consequence*: when every server restarts every ~60 s on its own schedule, the members are
   never up together long enough to elect a leader.
2. **"A coordinated restart will fix it."** I stopped K3s on all four and started them together. etcd
   formed a quorum, `kubectl get nodes` even showed all four `Ready` (stale heartbeats!) — and then
   three of them fell back into the loop. A restart can't fix a file that's wrong on disk.
3. **"Delete the bad kubeconfigs and K3s will regenerate them."** It won't. K3s only writes
   `cred/*.kubeconfig` when it (re)generates the client certs. With the files gone it exits
   immediately: `stat .../cred/supervisor.kubeconfig: no such file or directory`.

## The actual clue

The controller-manager was refused on `[::1]:6444`. So what *was* listening?

```bash
ss -ltnp | grep 6444      # -> 127.0.0.1:6444 (k3s-server)
grep -h server: /var/lib/rancher/k3s/server/cred/*.kubeconfig | sort | uniq -c
#      6     server: https://[::1]:6444
journalctl -u k3s -b | grep -m1 cluster-cidr
#   Running kube-proxy --cluster-cidr=fd00:42::/56 ...   <- IPv6-only at boot!
```

`fd00:42::/56` is K3s's default **IPv6** pod CIDR. At boot, the VM had a global IPv6 address from
router advertisements and *no* IPv4 lease, because the DHCP server is a VM that hadn't started yet.
K3s picked IPv6 as the node's family, picked `[::1]` as its loopback, and baked that into the
kubeconfigs. Once the DHCP server came up IPv4 arrived, and every subsequent start used `127.0.0.1` for
the API server — but the files still said `[::1]`.

The one server that didn't loop had its K3s restarted later, after DHCP was back. Its files said `127.0.0.1`.

## Step by step: the fix

Run everything from a machine that can SSH to the Proxmox hosts. In my setup K3s VMs are reached
via `qm guest exec` on their Proxmox host; replace `guest <server> '<cmd>'` with however you get a
root shell on your servers.

### 1. Confirm it's this bug (read-only)

On each server:

```bash
systemctl show k3s -p NRestarts --value                                      # large number
grep server: /var/lib/rancher/k3s/server/cred/controller.kubeconfig          # https://[::1]:6444 ?
ss -ltn | grep 6444                                                          # 127.0.0.1:6444 ?
journalctl -u k3s --since -5min | grep -m1 'Shutdown request'                # [::1]:6444 refused ?
```

All four yes → this post is for you. If the kubeconfig already says `127.0.0.1`, it's a different
problem (see "If it's not this" below).

### 2. Stop K3s on **all** servers

```bash
for s in <server-1> <server-2> <server-3> <server-4>; do guest $s 'systemctl stop k3s' & done; wait
```

Running pods keep running (K3s leaves the containerd shims alone), so this is less scary than it sounds.

### 3. Pin `node-ip` to IPv4 (prevents a repeat)

On each server, with its own IPv4 address:

```bash
cp -a /etc/rancher/k3s/config.yaml /etc/rancher/k3s/config.yaml.bak-$(date +%s)
echo "node-ip: <server-ipv4>" >> /etc/rancher/k3s/config.yaml
```

With `node-ip` set, K3s no longer guesses the address family from whatever the network happens to
offer at boot.

### 4. Rewrite the loopback in the internal kubeconfigs

```bash
CRED=/var/lib/rancher/k3s/server/cred
mkdir -p $CRED/backup-ipv6 && cp -a $CRED/*.kubeconfig $CRED/backup-ipv6/
sed -i 's#https://\[::1\]:6444#https://127.0.0.1:6444#' $CRED/*.kubeconfig
```

Only the `server:` URL changes; the client cert paths inside stay valid.

### 5. Start all servers **together**

```bash
for s in <server-1> <server-2> <server-3> <server-4>; do guest $s 'systemctl reset-failed k3s; systemctl start --no-block k3s' & done; wait
```

Together matters with embedded etcd: one server alone can't reach quorum and will time out.

### 6. Verify — properly

`kubectl get nodes` showing `Ready` is **not** proof; node status is the last heartbeat and can be
minutes stale. Check every server:

```bash
systemctl is-active k3s                        # active (not activating)
systemctl show k3s -p NRestarts --value        # stays at 0
k3s kubectl get --raw /readyz                  # ok
```

### Or: one script

```bash
./scripts/k3s/restart-all-servers.sh --check              # read-only diagnosis
./scripts/k3s/restart-all-servers.sh --yes --pin-ipv4     # steps 2-6; no-op if already healthy
```

The script is idempotent (does nothing if every server is healthy, only fixes what's still wrong),
runs the steps in parallel, prints per-server state every 15 s plus the last K3s error every
minute, and logs every run to `~/.local/state/homelab/k3s/`.

## If it's not this

| You see | Likely cause | Where to look |
|---|---|---|
| kubeconfigs say `127.0.0.1`, etcd `connection refused` to peers, only 2 of 4 servers up | Lost quorum: a server VM isn't running | Start it; check `onboot` |
| `tls: certificate required` / member unknown on one server | Stale etcd member after a long outage | `docs/runbooks/k3s-etcd-node-rejoin-after-outage.md` |
| Whole cluster gone | Rebuild | `docs/runbooks/k3s-cluster-recovery-2026-01.md` |

## Lessons

1. **Always set `node-ip`** on K3s nodes that live on a network with IPv6 router advertisements.
   "Auto-detect" means "whatever the network looked like for the first few seconds of boot".
2. **Infrastructure that boots before your DHCP server can boot into a different world.** When the
   DHCP server is a VM in the same cluster, the first minutes after a power cut are the most
   unusual network conditions your nodes ever see.
3. **Not every K3s file is regenerated on restart.** `cred/*.kubeconfig` is written once (or when
   certs change). Generated config that is wrong stays wrong.
4. **Compare the healthy node with the broken ones.** The one server that didn't loop had the
   answer in its `controller.kubeconfig` all along.
5. **`Ready` is a heartbeat, not a health check.** Use `/readyz` on every server.

## Timeline (Pacific, 2026-11-14)

| Time | Event |
|---|---|
| before 18:12 | Power cut (exact time unknown). Proxmox hosts boot when power returns; the DHCP VM is slower |
| 18:12–18:14 | K3s server VMs boot; K3s starts with IPv6 (RA) only → IPv6-only node, kubeconfigs get `[::1]` |
| evening | Restart loop on three servers. The fourth was restarted later, after DHCP was back, and is fine |
| 22:59 | Noticed while deploying an unrelated app: K3s API `ServiceUnavailable` |
| 23:03 | Coordinated restart of all servers: looks healthy briefly, loop resumes |
| 23:05 | Found `[::1]:6444` refused vs `127.0.0.1:6444` listening; `cluster-cidr=fd00:42::/56` at boot |
| 23:07 | Tried deleting `cred/*.kubeconfig`: K3s won't regenerate them (`no such file`) |
| 23:14 | Restored + rewrote `[::1]` → `127.0.0.1`, pinned `node-ip`, started all together |
| 23:15 | `restarts=0` and `127.0.0.1` loopback on every server |
