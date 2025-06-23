# Stable Diffusion Web UI via Flux

This guide shows how to deploy the `stable-diffusion-webui` project using FluxCD and persist model files on local storage.

The manifests live under `gitops/clusters/homelab/apps/stable-diffusion/`. Flux automatically applies the namespace, persistent volume claim, deployment, service and ingress when they are committed.

Models are stored in a `PersistentVolumeClaim` named `sd-models` mounted at `/stable-diffusion-webui/models`. The PVC uses the `local-path` storage class so the files remain on the node across pod restarts.
