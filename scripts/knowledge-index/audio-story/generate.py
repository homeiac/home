#!/usr/bin/env python3
"""Use the existing restricted SSH Job/ConfigMap path for the separate audio worker."""
import copy,hashlib,importlib.util,json
from pathlib import Path
import yaml
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('caption_generate',HERE.parent/'caption-gitops/generate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
files={'audio-worker.py':'worker.py','audio-config.json':'config.json','knowledge-index-audio-story.service':'knowledge-index-audio-story.service'}
bundle={name:(HERE/source).read_text() for name,source in files.items()}
raw=json.dumps(bundle,sort_keys=True);name='audio-worker-'+hashlib.sha256(raw.encode()).hexdigest()[:12]
resources=copy.deepcopy(m.resources())
resources[0]['metadata']['name']=name;resources[0]['data']['bundle.json']=raw
resources[1]['metadata']['name']=name
resources[2]['metadata']['name']='audio-worker-reconcile'
for pod in [resources[1]['spec']['template'],resources[2]['spec']['jobTemplate']['spec']['template']]:
 pod['metadata']['labels']['app']='audio-worker-installer'
 pod['spec']['volumes'][0]['configMap']['name']=name
out=HERE.parents[2]/'gitops/clusters/homelab/apps/photo-enrichment/audio-worker'
out.mkdir(exist_ok=True)
(out/'resources.yaml').write_text(yaml.safe_dump_all(resources,sort_keys=False,width=120))
(out/'kustomization.yaml').write_text('apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n  - resources.yaml\n')
