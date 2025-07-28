# k3s IP Allocation & etcd TLS Troubleshooting Runbook

## Overview

A k3s node became stuck in "activating" state with etcd errors:

```
etcdserver: request timed out
transport: authentication handshake failed: context deadline exceeded
ClientURLs: [https://192.168.4.220:2379](https://192.168.4.220:2379) (vs. intended 192.168.4.237)
```

**Root cause**: IP/SAN mismatch in etcd certificates and/or DHCP lease drift.

## Prerequisites

- SSH or console access to the node
- sudo/root privileges

## Troubleshooting Steps

### 1. Collect k3s logs

```bash
sudo journalctl -u k3s -b --no-pager -n 300
sudo journalctl -fu k3s
```

### 2. Inspect etcd certificate SANs

```bash
sudo openssl x509 \
  -in /var/lib/rancher/k3s/server/tls/etcd/server-client.crt \
  -text -noout | grep -A1 "Subject Alternative Name"
```

### 3. Rotate etcd certificates

```bash
sudo systemctl stop k3s
sudo k3s certificate rotate --service etcd
sudo systemctl start k3s
```

### 4. Configure a static IP via netplan

1. Create `/etc/netplan/99-k3s-static.yaml`:

   ```yaml
   network:
     version: 2
     renderer: networkd
     ethernets:
       eth0:
         match:
           macaddress: "bc:24:11:1a:38:07"
         addresses:
           - "192.168.4.237/24"
         nameservers:
           addresses: [192.168.4.1, 1.1.1.1]
         dhcp4: false
         routes:
           - to: default
             via: 192.168.4.1
   ```

2. Secure the file:

   ```bash
   sudo chown root:root /etc/netplan/99-k3s-static.yaml
   sudo chmod 600 /etc/netplan/99-k3s-static.yaml
   ```

3. Apply:

   ```bash
   sudo netplan apply
   ```

### 5. (Alternative) Use MAAS DHCP reservation

1. In MAAS UI, under Subnets → 192.168.4.0/24 → Reserved ranges, edit the dynamic pool end to `.236`.
2. In Devices, add or edit the node with MAC `bc:24:11:1a:38:07`, assign static IP `192.168.4.237`.
3. On the node: `sudo netplan apply` (or install/run `dhclient`) to renew the lease.

### 6. Verify resolution

```bash
k3s etcdctl endpoint status -w table
ip -4 addr show dev eth0
kubectl get nodes
```

Node should show `Ready`.

## Related Documentation

- [K3s Certificate Management](https://docs.k3s.io/advanced#certificate-rotation)
- [Netplan Configuration](https://netplan.io/examples/)
- [MAAS DHCP Configuration](https://maas.io/docs/how-to-enable-dhcp)

## Common Issues

### Certificate rotation fails

If certificate rotation fails, check:
- k3s service is stopped: `sudo systemctl is-active k3s`
- Sufficient disk space: `df -h /var/lib/rancher/k3s`
- File permissions: `ls -la /var/lib/rancher/k3s/server/tls/etcd/`

### Static IP configuration not working

Verify:
- MAC address matches: `ip link show`
- No conflicting netplan files: `ls -la /etc/netplan/`
- NetworkManager disabled: `sudo systemctl is-active NetworkManager`

### MAAS reservation not taking effect

Check:
- Node is properly enlisted in MAAS
- Subnet configuration is correct
- DHCP service is running: check MAAS logs