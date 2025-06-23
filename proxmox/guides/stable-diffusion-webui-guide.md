# Stable Diffusion Web UI via Flux

This guide shows how to deploy the `stable-diffusion-webui` project using FluxCD and persist model files on local storage. The manifests reference the Docker Hub image `universonic/stable-diffusion-webui:full`.

The manifests live under `gitops/clusters/homelab/apps/stable-diffusion/`. Flux automatically applies the namespace, persistent volume claim, deployment, service and ingress when they are committed.

Models are stored in a `PersistentVolumeClaim` named `sd-models` mounted at `/app/stable-diffusion-webui/models`. The PVC uses the `local-path` storage class so the files remain on the node across pod restarts.

## Standalone Docker Example

For quick testing outside Kubernetes you can run the container directly:

```bash
docker run --gpus all --restart unless-stopped -p 8080:8080 \
  --name stable-diffusion-webui -d universonic/stable-diffusion-webui:full
```

Persist data by mounting a directory from the host:

```bash
docker run --gpus all --restart unless-stopped -p 8080:8080 \
  -v /my/own/datadir/extensions:/app/stable-diffusion-webui/extensions \
  -v /my/own/datadir/models:/app/stable-diffusion-webui/models \
  -v /my/own/datadir/outputs:/app/stable-diffusion-webui/outputs \
  -v /my/own/datadir/localizations:/app/stable-diffusion-webui/localizations \
  --name stable-diffusion-webui -d universonic/stable-diffusion-webui:full
```

Check logs if the container fails to start:

```bash
docker logs -f stable-diffusion-webui
```

## Kubernetes Deployment

The Kubernetes manifests expose the web UI on port `8080` inside the
container. A service forwards traffic from port `80` to `8080` so you can
access the interface via the cluster ingress.

PVCs store models, outputs, extensions and localizations. The deployment mounts
each claim and sets `fsGroup: 1000` so the container user can write to these
paths.
