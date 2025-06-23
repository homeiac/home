# OpenCloud File Manager via Flux

Deploy the [opencloudeu/opencloud-rolling](https://hub.docker.com/r/opencloudeu/opencloud-rolling) container on your k3s cluster using FluxCD. The manifests are stored under `gitops/clusters/homelab/apps/opencloud/` and create a namespace, deployment, service and ingress.

The container initializes its configuration on first start with `opencloud init` and then runs the server. Data is stored on the host at `/mnt/smb_data/opencloud` so files survive pod restarts. Configuration files are persisted on a Longhorn volume for redundancy. Pods are scheduled on the `k3s-vm-still-fawn` node to match the Samba permissions.

## Standalone Docker Example

Run the container locally for testing:

```bash
docker run -p 9200:9200 \
  -v /tmp/oc-config:/etc/opencloud \
  -v /tmp/oc-data:/var/lib/opencloud \
  opencloudeu/opencloud-rolling:latest sh -c 'opencloud init || true; opencloud server'
```

## Kubernetes Deployment

The files in `gitops/clusters/homelab/apps/opencloud/` define a Deployment exposing port `9200` via an Ingress at `opencloud.app.homelab`. Apply them with Flux or `kubectl apply -k`.

Refer to the [OpenCloud documentation](https://docs.opencloud.eu/docs/admin/getting-started/container/docker-compose-local/) for additional environment variables and advanced configuration options.
