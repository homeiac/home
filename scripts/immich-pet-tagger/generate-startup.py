#!/usr/bin/env python3
"""Render the auditable startup script into its Flux-managed ConfigMap."""
from pathlib import Path
import yaml

root = Path(__file__).resolve().parents[2]
source = Path(__file__).with_name('startup.py').read_text()
target = root/'gitops/clusters/homelab/apps/photo-enrichment/immich-pet-tagger/startup-configmap.yaml'
target.write_text(yaml.safe_dump(dict(apiVersion='v1', kind='ConfigMap',
    metadata=dict(name='immich-pet-tagger-startup', namespace='immich-pilot'),
    data={'startup.py': source}), sort_keys=False))
