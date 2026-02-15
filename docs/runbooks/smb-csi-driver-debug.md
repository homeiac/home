# SMB CSI Driver Debug Runbook

**Date:** 2026-02-15
**Status:** Active
**Objective:** Debug and fix SMB mount issues before re-enabling for claudecodeui

---

## Background

The SMB CSI driver was added to provide session log backup to the samba share. Initial deployment failed with mount errors. This runbook documents the debug process.

## Current State

- SMB CSI driver: Installed (HelmRelease `csi-driver-smb` in kube-system)
- Samba server: Running at 192.168.4.120 (K8s service `samba-lb`)
- Share: `secure` (path=/shares, valid users=gshiva,alice)
- Credentials: `samba-credentials` secret in kube-system
- claudecodeui: SMB mount **disabled** pending debug

## Debug Steps

### 1. Deploy Debug Pod

```bash
kubectl apply -f gitops/clusters/homelab/infrastructure/smb-csi-driver/debug-smb-pod.yaml
```

### 2. Check Pod Status

```bash
kubectl get pod -n kube-system smb-debug-pod
kubectl describe pod -n kube-system smb-debug-pod
```

### 3. Check CSI Driver Logs

```bash
# Controller logs
kubectl logs -n kube-system -l app.kubernetes.io/name=csi-driver-smb -c smb --tail=50

# Node logs (on specific node)
kubectl logs -n kube-system -l app.kubernetes.io/name=csi-driver-smb -c smb --tail=50 | grep -i error
```

### 4. Verify Samba Server Reachable

```bash
# From inside debug pod
kubectl exec -it -n kube-system smb-debug-pod -- sh
ping -c 3 192.168.4.120
```

### 5. Test Manual Mount (if pod stuck)

```bash
# From K3s node (SSH or qm guest exec)
# Install cifs-utils if needed
apt-get install -y cifs-utils

# Test mount
mount -t cifs -o username=gshiva,password=<PASSWORD> //192.168.4.120/secure /mnt/test
ls /mnt/test
umount /mnt/test
```

### 6. Check Credentials Secret

```bash
kubectl get secret samba-credentials -n kube-system -o jsonpath='{.data.username}' | base64 -d
# Should output: gshiva (or alice)
```

### 7. Cleanup

```bash
kubectl delete -f gitops/clusters/homelab/infrastructure/smb-csi-driver/debug-smb-pod.yaml
```

---

## Known Issues

### Issue 1: Share path doesn't exist

**Symptom:**
```
mount error(112): Host is down
mount error: Server abruptly closed the connection
```

**Cause:** The PV referenced `//192.168.4.120/secure/claude-sessions` but samba only has `secure` share at root.

**Fix:** Use `//192.168.4.120/secure` and create subdirectory via subPath or manual mkdir.

### Issue 2: HelmRepository namespace mismatch

**Symptom:**
```
HelmChart 'flux-system/kube-system-csi-driver-smb' is not ready: failed to get source
```

**Cause:** Kustomization had `namespace: kube-system` override which moved HelmRepository to wrong namespace.

**Fix:** Remove namespace override from kustomization, let resources declare their own namespaces.

### Issue 3: Node can't access secret

**Symptom:**
```
fetching NodeStageSecretRef kube-system/samba-credentials failed: User "system:node:k3s-vm-..." cannot get resource "secrets"
```

**Cause:** K3s node RBAC doesn't allow reading secrets from kube-system by default.

**Fix:** May need to add RBAC or use different secret namespace.

---

## Success Criteria

1. Debug pod starts and mounts successfully
2. Can read/write files to `/mnt/smb-test/`
3. CSI driver logs show "mount succeeded"
4. Re-enable in claudecodeui with confidence

---

## Related Files

- `gitops/clusters/homelab/infrastructure/smb-csi-driver/debug-smb-pod.yaml` - Debug pod
- `gitops/clusters/homelab/infrastructure/smb-csi-driver/helmrelease.yaml` - CSI driver
- `gitops/clusters/homelab/infrastructure/smb-csi-driver/secrets/samba-credentials.sops.yaml` - Credentials
- `gitops/clusters/homelab/apps/samba/configmap.yaml` - Samba share config
- `gitops/clusters/homelab/apps/claudecodeui/smb-claude-sessions-pv.yaml` - Disabled PV/PVC

---

## Tags

smb, csi, samba, cifs, mount, debug, claudecodeui, backup
