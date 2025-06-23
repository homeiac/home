# Stable Diffusion Web UI via Flux

Deploy the [AUTOMATIC1111/stable-diffusion-webui](https://github.com/AUTOMATIC1111/stable-diffusion-webui) project on your cluster. FluxCD watches the manifests under `gitops/clusters/homelab/apps/stable-diffusion/` and ensures the web UI runs with GPU access.

A `PersistentVolumeClaim` called `sd-models` stores models at `/stable-diffusion-webui/models`, keeping them across pod restarts.
