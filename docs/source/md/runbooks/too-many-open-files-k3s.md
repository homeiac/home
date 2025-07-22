# Troubleshooting "Too Many Open Files" in K3s

When running K3s you may encounter errors like:

```text
Failed to allocate directory watch: Too many open files
lsof: no pwd entry for UID 65535
```

These messages usually mean the kernel inotify limits are too low or a container is using too many file descriptors.
This runbook explains how to investigate and fix the issue.

## Increase inotify limits

Append the following to `/etc/sysctl.conf`:

```bash
fs.inotify.max_user_watches=524288
fs.inotify.max_user_instances=1024
fs.inotify.max_queued_events=16384
```

Apply the new values:

```bash
sudo sysctl -p
```

Check the current settings with:

```bash
cat /proc/sys/fs/inotify/max_user_watches
cat /proc/sys/fs/inotify/max_user_instances
cat /proc/sys/fs/inotify/max_queued_events
```

## Check open file count

See how many file descriptors are open across the system:

```bash
lsof | wc -l
```

## Find top file descriptor consumers

Identify which processes hold the most descriptors:

```bash
sudo lsof | awk '{print $2}' | sort | uniq -c | sort -nr | head -20
```

For each PID you can see details with:

```bash
ps -p <PID> -o pid,user,cmd
sudo lsof -p <PID> | less
```

## Investigate UIDs without passwd entries

If `lsof` shows warnings like `no pwd entry for UID 65535`, determine which process belongs to that UID:

```bash
lsof 2>&1 | grep 'no pwd entry' | awk '{print $NF}' | sort | uniq -c
ps -eo pid,uid,cmd | awk '$2 == <UID>'
sudo ls /proc/<PID>/fd | wc -l
```

In our cluster we saw high usage from UIDs 472 (grafana sidecar) and 65532 (traefik, coredns).

## Optional: set systemd limits

If you run K3s under `systemd` you can raise the open file limit:

```bash
sudo mkdir -p /etc/systemd/system/k3s.service.d
echo -e "[Service]\nLimitNOFILE=65535" | sudo tee /etc/systemd/system/k3s.service.d/override.conf
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl restart k3s
```

## Key takeaways

* `ulimit -n` alone is not enough—adjust inotify limits too
* Long-running containers like Traefik or CoreDNS may slowly leak descriptors
* `lsof` warnings for UID 65535 (usually `nobody`) are expected in container workloads
* Always correlate UID, PID, command, and open descriptor count
