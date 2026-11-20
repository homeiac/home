#!/usr/bin/env python3
"""Generate a narrowly targeted GitOps host-driver maintenance Job (#217)."""
import argparse
from pathlib import Path
import yaml
root=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','install']);args=p.parse_args()
name='piglet-driver-580-'+args.phase+'-v4'
image='ghcr.io/immich-app/immich-server:v3.4.2@sha256:fc880c1bf665b4aab1e74c15e56ab871225989cd546536e6b77e771869af06bd'
code={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'piglet-driver-580-code','namespace':'gpu-operator'},'data':{'driver.sh':(Path(__file__).parent/'upgrade.sh').read_text()}}
job={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':'gpu-operator'},'spec':{'backoffLimit':0,'activeDeadlineSeconds':1800,'template':{'spec':{'restartPolicy':'Never','hostNetwork':True,'dnsPolicy':'ClusterFirstWithHostNet','automountServiceAccountToken':False,'nodeSelector':{'kubernetes.io/hostname':'k3s-vm-pumped-piglet-gpu'},'containers':[{'name':'maintenance','image':image,'command':['bash','-c',f'exec chroot /host /bin/bash -s -- {args.phase} < /scripts/driver.sh'],'securityContext':{'privileged':True},'resources':{'requests':{'cpu':'100m','memory':'256Mi'},'limits':{'cpu':'2','memory':'4Gi'}},'volumeMounts':[{'name':'host','mountPath':'/host'},{'name':'code','mountPath':'/scripts','readOnly':True}]}],'volumes':[{'name':'host','hostPath':{'path':'/','type':'Directory'}},{'name':'code','configMap':{'name':'piglet-driver-580-code'}}]}}}}
out=root/'gitops/clusters/homelab/apps/photo-enrichment/gpu-maintenance'
(out/'resources.yaml').write_text(yaml.safe_dump_all([code,job],sort_keys=False))
(out/'kustomization.yaml').write_text('apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n  - resources.yaml\n')
