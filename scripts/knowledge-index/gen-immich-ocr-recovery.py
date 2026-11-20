#!/usr/bin/env python3
"""Generate an idempotent native missing-only OCR recovery Job (#217)."""
from pathlib import Path
import yaml
root=Path(__file__).resolve().parents[2]
name='immich-ocr-gpu-recovery-v1'
image='ghcr.io/immich-app/immich-server:v3.4.2@sha256:fc880c1bf665b4aab1e74c15e56ab871225989cd546536e6b77e771869af06bd'
metadata={'name':name,'namespace':'immich-pilot'}
code={'apiVersion':'v1','kind':'ConfigMap','metadata':metadata,'data':{'recovery.mjs':(Path(__file__).parent/'recover-immich-ocr.mjs').read_text()}}
job={'apiVersion':'batch/v1','kind':'Job','metadata':metadata,'spec':{'backoffLimit':1,'activeDeadlineSeconds':120,'template':{'spec':{'restartPolicy':'Never','automountServiceAccountToken':False,'nodeSelector':{'kubernetes.io/hostname':'k3s-vm-pumped-piglet-gpu'},'containers':[{'name':'recovery','image':image,'command':['node','/scripts/recovery.mjs'],'env':[{'name':'APPLY','value':'true'}],'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'256Mi'}},'volumeMounts':[{'name':'code','mountPath':'/scripts','readOnly':True}]}],'volumes':[{'name':'code','configMap':{'name':name}}]}}}}
out=root/'gitops/clusters/homelab/apps/photo-enrichment/immich-ocr-recovery'
out.mkdir(exist_ok=True)
(out/'resources.yaml').write_text(yaml.safe_dump_all([code,job],sort_keys=False))
(out/'kustomization.yaml').write_text('apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n  - resources.yaml\n')
