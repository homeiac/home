# The Samba "Permission Denied" That Wasn't About Permissions

**Date**: 2026-02-09
**Tags**: samba, kubernetes, debugging, permissions, homelab, frustration, lessons-learned

## The Error

macOS Finder shows the most useless error message possible:

> "There was a problem connecting to the server '192.168.4.120'. You do not have permission to access this server."

That's it. No error code. No hint. Just "permission denied."

## The Investigation Spiral

Here's what I checked, in order:

1. **Is the pod running?** Yes. `kubectl get pods -n samba` shows 1/1 Running.

2. **Is the service reachable?** Yes. `nc -zv 192.168.4.120 445` connects fine.

3. **Are the users created?** Yes. `pdbedit -L` shows both users in the samba database.

4. **Is the password correct?** Decoded the secret, verified it matches.

5. **Is there a stale macOS keychain entry?** Found one! Deleted it. Still broken.

6. **Is it a Mac-specific SMB issue?** Tried from Linux: same `Permission denied`.

At this point I'm questioning reality. Users exist. Password is correct. Service is up. What else is there?

## The Actual Problem

Tested from inside the Kubernetes cluster:

```bash
$ smbclient //10.42.0.83/secure -U gshiva%password -c 'ls'
NT_STATUS_ACCESS_DENIED listing \*
```

Wait. `NT_STATUS_ACCESS_DENIED` is different from authentication failure. This means **auth succeeded** but the user can't list the directory.

Checked the share directory:

```bash
$ ls -la /shares
drwxrwx---    4 root     root     4096 Feb  9 16:49 .
```

The samba config has `force user=nobody`. But `/shares` is owned by `root:root` with mode `770`. The `nobody` user (uid 65534) has zero access.

## The Fix

```bash
chown nobody:nogroup /shares
chmod 0775 /shares
```

That's it. The share instantly works.

## Why This Happens

The deployment had an init container to set permissions:

```yaml
initContainers:
- name: init-perms
  command:
  - sh
  - -c
  - |
    chown nobody:nogroup /mnt/smb_data
    chmod 0770 /mnt/smb_data
```

Two problems:

1. **Wrong mode**: `0770` means owner and group only. But `force user=nobody` maps all samba access to the `nobody` user, who isn't in the `root` group. Should be `0775`.

2. **Fragile assumption**: The init container runs once. If something else changes the permissions (another process, a PV migration, manual debugging), the fix disappears.

## The Rage-Inducing Part

This took over an hour to debug. The error message "You do not have permission" is technically correct but completely misleading. The natural assumption is:

- Wrong username
- Wrong password
- User doesn't exist
- Auth mechanism misconfigured

Nobody thinks "the directory permissions inside the container are wrong" when they see "permission denied" on connection.

Samba's own logs showed nothing useful at log level 3. The connection came in, auth succeeded, and then... silence. No "user nobody cannot access /shares" message. Nothing.

## Lessons

1. **"Permission denied" has multiple layers**: Authentication permissions (can this user log in?) vs filesystem permissions (can this user read the files?) vs samba share permissions (is this user in valid users?). The error message doesn't tell you which layer failed.

2. **Test from inside the cluster first**: If I'd run `smbclient` from a pod immediately, I'd have seen `NT_STATUS_ACCESS_DENIED` instead of the generic macOS error. That would have pointed directly at filesystem permissions.

3. **`force user` is a footgun**: It maps all access to a single Unix user, but that user still needs actual filesystem permissions. The samba share config and the filesystem permissions must agree.

4. **Init containers are one-shot**: They fix things at pod startup but don't maintain them. If you need persistent permissions, consider a sidecar or just fixing the underlying storage.

5. **770 vs 775 matters**: That single bit (other-execute, which for directories means "can traverse") is the difference between working and "permission denied."

## The Debugging Checklist I Wish I Had

For future samba "permission denied" errors:

```bash
# 1. Can you auth at all? (from inside cluster)
smbclient //POD_IP/share -U user%pass -c 'ls'

# If NT_STATUS_LOGON_FAILURE: auth problem (user/pass/samba config)
# If NT_STATUS_ACCESS_DENIED: filesystem permissions

# 2. Check filesystem permissions
kubectl exec -n samba POD -- ls -la /path/to/share

# 3. Check what user samba runs as
grep "force user" /etc/samba/smb.conf

# 4. Verify that user can access the directory
kubectl exec -n samba POD -- su -s /bin/sh nobody -c "ls /path/to/share"
```

## Final Thought

The error wasn't wrong. I genuinely didn't have permission. But "permission" in networked file systems is a four-layer stack (network, auth, share ACL, filesystem), and a single word doesn't tell you which layer rejected you.

Next time: test from inside first, check `NT_STATUS_*` codes, verify filesystem permissions match the forced user.
