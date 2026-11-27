#!/usr/bin/env python3
"""Generate isolated cached media recovery using the verified pinned Immich image."""
import hashlib
import importlib.util
from pathlib import Path
import yaml
here=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('generator',here/'generate-distributed.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
files={name:(here/name).read_text() for name in ['media-fallback-core.mjs','media-fallback.mjs']}
name='waffles-media';labels={'app':name}
objects=[g.obj('ConfigMap',name,data=files),g.obj('PersistentVolumeClaim',name,spec={'accessModes':['ReadWriteOnce'],'storageClassName':'local-path','resources':{'requests':{'storage':'4Gi'}}})]
objects[-1]['metadata']['annotations']={'kustomize.toolkit.fluxcd.io/prune':'disabled'}
objects.append(g.obj('Deployment',name,api='apps/v1',spec={'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':labels},'template':{
 'metadata':{'labels':labels,'annotations':{'checksum/code':hashlib.sha256(''.join(files.values()).encode()).hexdigest()}},
 'spec':{'automountServiceAccountToken':False,'securityContext':g.SECURITY,'nodeSelector':{'kubernetes.io/hostname':'k3s-vm-still-fawn'},
 'volumes':[{'name':'code','configMap':{'name':name}},{'name':'data','persistentVolumeClaim':{'claimName':name}}],
 'containers':[{'name':'media','image':g.NODE_IMAGE,'command':['node','/code/media-fallback.mjs'],'securityContext':g.CONTAINER_SECURITY,
 'resources':{'requests':{'cpu':'50m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}},
 'env':[g.env('IMMICH_API_KEY',secret='immich-pet-tagger',key='api-key'),g.env('WORKER_TOKEN',secret='waffles-queue',key='worker-token')],
 'volumeMounts':[{'name':'code','mountPath':'/code','readOnly':True},{'name':'data','mountPath':'/data'}],
 'ports':[{'name':'http','containerPort':9201}],'readinessProbe':{'httpGet':{'path':'/healthz','port':'http'}},'livenessProbe':{'httpGet':{'path':'/healthz','port':'http'},'initialDelaySeconds':15}}]}}}))
objects.append(g.obj('Service',name,spec={'selector':labels,'ports':[{'name':'http','port':9201,'targetPort':'http'}]}))
objects.append(g.obj('NetworkPolicy',name,api='networking.k8s.io/v1',spec={'podSelector':{'matchLabels':labels},'policyTypes':['Ingress'],
 'ingress':[{'from':[{'podSelector':{'matchLabels':{'app':'waffles-queue'}}}],'ports':[{'protocol':'TCP','port':9201}]}]}))
(g.DEST/'media-fallback.yaml').write_text(yaml.safe_dump_all(objects,sort_keys=False))
