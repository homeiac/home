# OpenCloud File Manager via Flux

Deploy the [opencloudeu/opencloud-rolling](https://hub.docker.com/r/opencloudeu/opencloud-rolling) container on your k3s cluster using FluxCD. The manifests are stored under `gitops/clusters/homelab/apps/opencloud/` and create a namespace, deployment, service and ingress.

If authentication fails with DNS lookup errors, see the troubleshooting section below.

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

## Troubleshooting Login Errors

If the OpenCloud proxy logs show errors resolving `opencloud.app.homelab`, add a host alias so the pod can resolve itself:

```yaml
hostAliases:
  - ip: "127.0.0.1"
    hostnames:
      - opencloud.app.homelab
```

Apply the updated deployment manifest to update the running pod. This maps the domain to `127.0.0.1` inside the container so token verification works.

## Removing the Deployment

To delete the OpenCloud resources from the cluster, remove the `apps/opencloud` entry from `gitops/clusters/homelab/kustomization.yaml` and delete the directory `gitops/clusters/homelab/apps/opencloud`. Commit the changes so Flux applies them:

```bash
git rm -r gitops/clusters/homelab/apps/opencloud
sed -i '/apps\/opencloud/d' gitops/clusters/homelab/kustomization.yaml
git commit -m "Remove OpenCloud" && git push
```

Flux will then prune the OpenCloud Deployment, Service and related objects from the cluster.
