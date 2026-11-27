#!/usr/bin/env python3
"""Generate an isolated preview scanner without rolling queue or inference pods."""
import hashlib
import importlib.util
from pathlib import Path
import yaml

here=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('distributed_generator',here/'generate-distributed.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
files={name:(here/name).read_text() for name in ['preview-preflight-core.mjs','preview-preflight.mjs']}
digest=hashlib.sha256(''.join(files.values()).encode()).hexdigest()
config=g.obj('ConfigMap','waffles-preview-preflight',data=files)
job=g.obj('Job','waffles-preview-preflight-v1',api='batch/v1',spec={
    'backoffLimit':2,'activeDeadlineSeconds':10800,
    'template':{'metadata':{'labels':{'app':'waffles-preview-preflight'},'annotations':{'checksum/code':digest}},
    'spec':{'automountServiceAccountToken':False,'securityContext':g.SECURITY,'restartPolicy':'Never',
        'nodeSelector':{'kubernetes.io/hostname':'k3s-vm-still-fawn'},
        'terminationGracePeriodSeconds':20,
        'volumes':[{'name':'code','configMap':{'name':'waffles-preview-preflight'}}],
        'containers':[{'name':'scanner','image':g.NODE_IMAGE,'command':['node','/code/preview-preflight.mjs'],
            'securityContext':g.CONTAINER_SECURITY,
            'resources':{'requests':{'cpu':'25m','memory':'64Mi'},'limits':{'cpu':'250m','memory':'256Mi'}},
            'volumeMounts':[{'name':'code','mountPath':'/code','readOnly':True}],
            'env':[g.env('PGHOST','postgres-postgresql.database.svc.cluster.local'),
                   g.env('PGDATABASE','photo_enrichment'),g.env('PGUSER','waffles_worker'),
                   g.env('PGPASSWORD',secret='waffles-queue',key='password'),
                   g.env('IMMICH_API_KEY',secret='immich-pet-tagger',key='api-key'),
                   g.env('PREFLIGHT_RUN','historical-waffles'),g.env('PREFLIGHT_CONCURRENCY','4'),
                   g.env('PREFLIGHT_REQUESTS_PER_SECOND','20')]}]}}})
(g.DEST/'preview-preflight.yaml').write_text(yaml.safe_dump_all([config,job],sort_keys=False))
