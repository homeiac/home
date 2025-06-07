# Kubernetes-Hosted Samba Share: A Pyramid Guide

## Summary

- **Use** the official **ghcr.io/servercontainers/samba** image to get all the
  entrypoint hooks.
- **Configure** via Kubernetes Secrets and ConfigMaps (`ACCOUNT_*`,
  `SAMBA_GLOBAL_STANZA`, `SAMBA_VOLUME_CONFIG_*`).
- **Deploy** with `hostNetwork: true`, a hostPath volume plus initContainer to
  set ownership/permissions.
- **Bind** Samba on real interfaces (`lo eth0`) so it listens on
  `0.0.0.0:445/139`.
- **Validate** via `pdbedit -L`, `ss -tnlp`, `testparm -s`, and mount tests on
  Linux, macOS, Windows.

---

## Implementation

```yaml
# samba-full.yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: samba

---
apiVersion: v1
kind: Secret
metadata:
  name: samba-users
  namespace: samba
type: Opaque
stringData:
  ACCOUNT_alice: "<ALICE_PASSWORD>"
  UID_alice:   "10001"
  ACCOUNT_bob:   "<BOB_PASSWORD>"
  UID_bob:     "10002"

---
apiVersion: v1
kind: ConfigMap
metadata:
  name: samba-volumes
  namespace: samba
data:
  SAMBA_VOLUME_CONFIG_secure: >-
    [secure]; path=/shares; browseable=yes; writable=yes;
    valid users=alice,bob; force user=nobody; create mask=0770; directory mask=0770

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: samba
  namespace: samba
spec:
  replicas: 1
  selector:
    matchLabels: { app: samba }
  template:
    metadata:
      labels: { app: samba }
    spec:
      nodeSelector:
        kubernetes.io/hostname: your-node
      hostNetwork: true
      volumes:
        - name: share
          hostPath:
            path: /mnt/smb_data
            type: Directory
      initContainers:
        - name: init-perms
          image: busybox
          command: ["sh","-c","chown nobody:nogroup /mnt/smb_data && chmod 0770 /mnt/smb_data"]
          volumeMounts:
            - name: share
              mountPath: /mnt/smb_data
      containers:
        - name: smbd
          image: ghcr.io/servercontainers/samba:latest
          env:
            - name: SAMBA_GLOBAL_STANZA
              value: >-
                bind interfaces only = yes; interfaces = lo eth0;
                server string = Kubernetes Samba; map to guest = Bad User;
                log level = 3; max log size = 10000
            - name: MODEL
              value: "TimeCapsule"
            - name: AVAHI_NAME
              value: "StorageServer"
          envFrom:
            - secretRef: { name: samba-users }
            - configMapRef: { name: samba-volumes }
          securityContext:
            runAsUser: 0
          volumeMounts:
            - name: share
              mountPath: /shares
          ports:
            - { containerPort: 445, hostPort: 445, protocol: TCP }
            - { containerPort: 139, hostPort: 139, protocol: TCP }
 ```bash

---

## Validation

```bash
POD=$(kubectl -n samba get pods -l app=samba -o jsonpath='{.items[0].metadata.name}')

# Inspect global stanza
kubectl -n samba exec -it $POD -- sed -n '/^\[global\]/,/^\[secure\]/p' /etc/samba/smb.conf

# Check listening ports
sudo ss -tnlp | grep -E ':(445|139)'

# List Samba users
kubectl -n samba exec -it $POD -- pdbedit -L

# Syntax check
kubectl -n samba exec -it $POD -- testparm -s
```

---

## Mount Tests

- **Linux VM** (sudo required)

  ```bash
  sudo mkdir -p /mnt/smb-test && sudo chmod 0777 /mnt/smb-test
  sudo mount -t cifs //127.0.0.1/secure /mnt/smb-test \
    -o username=alice,password=<ALICE_PASSWORD>,vers=3.0
  touch /mnt/smb-test/linux_ok.txt
  ls -l /mnt/smb_data/linux_ok.txt
  ```

- **macOS** (no sudo)

  ```bash
  mkdir -p ~/smb-test
  mount_smbfs "//alice@<NODE_IP>/secure" ~/smb-test
  touch ~/smb-test/mac_ok.txt
  ```

- **Windows**

  ```bat
  net use * /delete /y
  net use Z: \\<NODE_IP>\secure <ALICE_PASSWORD> /user:alice /persistent:yes
  echo hello > Z:\win_ok.txt
  ```

---

## Missteps & Key Errors

1. **Pod-only binding**

   ```bash
   sudo netstat -tulpn | grep :445
   # → only sees 10.42.x.x:445
   ```

2. **Illegal option “-F”**

   ```bash
   /container/scripts/entrypoint.sh: exec: line 311: illegal option -F
   ```

3. **UID collision**

   ```bash
   adduser: uid '65534' in use
   Failed to add entry for user sambauser.
   ```

4. **Backslashes in share env**

   ```bash
      \
   ```

5. **Missing `[secure]` header**

   ```bash
   path=/shares
   browseable=yes
   …
   ```

6. **0.0.0.0/0 binds only first interface**

   ```bash
   interpret_interface: using netmask value 0 … on interface flannel.1
   ```

7. **Windows guest conflict**

   ```bash
   Multiple connections to a server or shared resource by the same user…
   ```

---

**Thanks** to the maintainers of **ServerContainers/samba** for the powerful
image!
