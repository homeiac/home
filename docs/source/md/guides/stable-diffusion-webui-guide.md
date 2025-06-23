# Stable Diffusion Web UI via Flux

Deploy the [universonic/stable-diffusion-webui](https://hub.docker.com/r/universonic/stable-diffusion-webui) container on your cluster. FluxCD watches the manifests under `gitops/clusters/homelab/apps/stable-diffusion/` and ensures the web UI runs with GPU access.

A `PersistentVolumeClaim` called `sd-models` stores models at `/app/stable-diffusion-webui/models`, keeping them across pod restarts.

## Standalone Docker Example

Run the container directly for local testing:

```bash
docker run --gpus all --restart unless-stopped -p 8080:8080 \
  --name stable-diffusion-webui -d universonic/stable-diffusion-webui:full
```

Mount a data directory to persist extensions, models and outputs:

```bash
docker run --gpus all --restart unless-stopped -p 8080:8080 \
  -v /my/own/datadir/extensions:/app/stable-diffusion-webui/extensions \
  -v /my/own/datadir/models:/app/stable-diffusion-webui/models \
  -v /my/own/datadir/outputs:/app/stable-diffusion-webui/outputs \
  -v /my/own/datadir/localizations:/app/stable-diffusion-webui/localizations \
  --name stable-diffusion-webui -d universonic/stable-diffusion-webui:full
```

View logs with `docker logs -f stable-diffusion-webui` if you encounter startup issues.

## Kubernetes Deployment

The manifests in `gitops/clusters/homelab/apps/stable-diffusion/` create
persistent volumes for models, outputs, extensions and localizations. The
deployment mounts these PVCs and sets `fsGroup: 1000` so the container user can
write to them.

