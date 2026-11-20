#!/usr/bin/env python3
"""Generate the reconciliation worker, bootstrap Job and monitoring (#217)."""
import hashlib
from pathlib import Path
import yaml
HERE=Path(__file__).resolve().parent
OUT=HERE.parents[1]/'gitops/clusters/homelab/apps/photo-enrichment/immich-sync'
# Reuse the exact already running official image; it contains pg and Sharp.
IMAGE='ghcr.io/immich-app/immich-server:v3.4.2@sha256:fc880c1bf665b4aab1e74c15e56ab871225989cd546536e6b77e771869af06bd'
def generate(mode='dry-run', max_preserved=0):
    code={p.name:p.read_text() for p in sorted((HERE/'immich_sync').glob('*')) if p.suffix in ('.mjs','.sql') and p.name!='target-audit.sql'}
    checksum=hashlib.sha256(str(code).encode()).hexdigest()
    docs=[]
    def obj(api,kind,name,namespace,spec=None,**extra):
        value=dict(apiVersion=api,kind=kind,metadata=dict(name=name,namespace=namespace),**extra)
        if spec is not None:value['spec']=spec
        docs.append(value);return value
    for ns in ['database','immich-pilot']:obj('v1','ConfigMap','immich-sync-code',ns,data=code)
    def env(name,value=None,key=None,secret='immich-sync'):
        return {'name':name,**({'value':value} if value is not None else {'valueFrom':{'secretKeyRef':{'name':secret,'key':key}}})}
    def pod(container):
        return {'restartPolicy':'Always','automountServiceAccountToken':False,
          'nodeSelector':{'kubernetes.io/hostname':'k3s-vm-pumped-piglet-gpu'},
          'securityContext':{'runAsNonRoot':True,'runAsUser':1000,'seccompProfile':{'type':'RuntimeDefault'}},
          'containers':[{'name':'sync','image':IMAGE,'securityContext':{'readOnlyRootFilesystem':True,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},
            'volumeMounts':[{'name':'code','mountPath':'/code','readOnly':True}],**container}],
          'volumes':[{'name':'code','configMap':{'name':'immich-sync-code'}}]}
    boot=pod({'command':['node','/code/bootstrap.mjs'],'env':[env('PGHOST','postgres-postgresql.database.svc.cluster.local'),env('PGDATABASE','photo_enrichment'),env('PGUSER','postgres'),env('PGPASSWORD',key='postgres-password',secret='postgres-credentials'),env('ROLE_PASSWORD',key='password',secret='immich-sync-bootstrap')],
      'resources':{'requests':{'cpu':'25m','memory':'64Mi'},'limits':{'cpu':'500m','memory':'256Mi'}}})
    boot['restartPolicy']='Never'
    # Stable name: changes to bootstrap are explicitly versioned instead of mutating Job specs.
    obj('batch/v1','Job','immich-sync-schema-v3','database',{'backoffLimit':3,'template':{'spec':boot}})
    worker=pod({'command':['node','/code/worker.mjs'],
      'env':[env('PGHOST','postgres-postgresql.database.svc.cluster.local'),env('PGDATABASE','photo_enrichment'),env('PGUSER','immich_reconciler'),env('PGPASSWORD',key='pg-password'),env('SYNC_MODE',mode),env('ENABLE_FACE_TRANSFER','false'),env('SYNC_BATCH_SIZE','25'),env('SYNC_MAX_PRESERVED',str(max_preserved))],
      'resources':{'requests':{'cpu':'100m','memory':'256Mi'},'limits':{'cpu':'1','memory':'2Gi'}},
      'ports':[{'name':'metrics','containerPort':9200}],
      'readinessProbe':{'httpGet':{'path':'/healthz','port':'metrics'}},
      'livenessProbe':{'httpGet':{'path':'/healthz','port':'metrics'},'initialDelaySeconds':30}})
    worker['containers'][0]['volumeMounts'] += [{'name':'credentials','mountPath':'/credentials','readOnly':True},{'name':'originals','mountPath':'/external/gphotos','readOnly':True}]
    worker['volumes'] += [{'name':'credentials','secret':{'secretName':'immich-sync','items':[{'key':'api-key','path':'api-key'}]}},{'name':'originals','hostPath':{'path':'/mnt/gphotos/library','type':'Directory'}}]
    labels={'app':'immich-sync'}
    obj('apps/v1','Deployment','immich-sync','immich-pilot',{'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':labels},'template':{'metadata':{'labels':labels,'annotations':{'checksum/code':checksum}},'spec':worker}})
    svc=obj('v1','Service','immich-sync','immich-pilot',{'selector':labels,'ports':[{'name':'metrics','port':9200,'targetPort':'metrics'}]});svc['metadata']['labels']=labels
    sm=obj('monitoring.coreos.com/v1','ServiceMonitor','immich-sync','immich-pilot',{'selector':{'matchLabels':labels},'endpoints':[{'port':'metrics','interval':'30s'}]});sm['metadata']['labels']={'release':'kube-prometheus-stack'}
    rule=obj('monitoring.coreos.com/v1','PrometheusRule','immich-sync','immich-pilot',{'groups':[{'name':'immich.reconciliation','rules':[
      {'alert':'ImmichReconciliationUnavailable','expr':'immich_sync_api_ready == 0 or absent(immich_sync_api_ready)','for':'10m','labels':{'severity':'warning'},'annotations':{'summary':'Knowledge Index to Immich reconciliation is unavailable'}},
      {'alert':'ImmichReconciliationStalled','expr':'(sum(immich_sync_assets{state="pending"}) > 0) and on() (immich_sync_mode{mode="apply"} == 1) and on() (time()-immich_sync_last_success > 900)','for':'5m','labels':{'severity':'warning'},'annotations':{'summary':'Immich preservation queue is not making progress'}},
      {'alert':'ImmichReconciliationFailures','expr':'sum(immich_sync_assets{state="error"}) > 0','for':'10m','labels':{'severity':'warning'},'annotations':{'summary':'Immich enrichment transfers require diagnosis','description':'Inspect structured immich-sync pod logs. Failed transfers retry with bounded backoff; originals are read-only.'}}
    ]}]});rule['metadata']['labels']={'release':'kube-prometheus-stack'}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'resources.yaml').write_text(yaml.safe_dump_all(docs,sort_keys=False))
    (OUT/'kustomization.yaml').write_text('apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n  - credentials.sops.yaml\n  - resources.yaml\n')
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['dry-run','apply'],default='dry-run');p.add_argument('--max-preserved',type=int,default=0);args=p.parse_args();generate(args.mode,args.max_preserved)
