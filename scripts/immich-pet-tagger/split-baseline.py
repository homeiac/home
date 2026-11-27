#!/usr/bin/env python3
"""Preserve the existing baseline pod specs while adding independent burst workers."""
from pathlib import Path
import yaml

root=Path(__file__).resolve().parents[2]
directory=root/'gitops/clusters/homelab/apps/photo-enrichment/immich-pet-tagger'
destination=directory/'baseline.yaml'
if destination.exists():raise SystemExit('Baseline already split; do not overwrite its reviewed pod specs')
documents=list(yaml.safe_load_all((directory/'distributed.yaml').read_text()))
names={'waffles-worker-still-fawn','waffles-worker-pve'}
baseline=[d for d in documents if d['metadata']['name'] in names]
assert len(baseline)==6
destination.write_text(yaml.safe_dump_all(baseline,sort_keys=False))
manifest=yaml.safe_load((directory/'kustomization.yaml').read_text())
manifest['resources'].append('baseline.yaml')
(directory/'kustomization.yaml').write_text(yaml.safe_dump(manifest,sort_keys=False))
print('Preserved baseline deployments, caches and VPAs without changing pod templates')
