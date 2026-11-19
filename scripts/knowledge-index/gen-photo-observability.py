#!/usr/bin/env python3
"""Generate the small private OTel/Tempo/Loki stack for photo-app diagnostics."""
import hashlib
import json
import yaml

NS='monitoring'
NODE='k3s-vm-still-fawn'

tempo={'target':'all','stream_over_http_enabled':True,'server':{'http_listen_port':3200},
 'distributor':{'receivers':{'otlp':{'protocols':{'grpc':{'endpoint':'0.0.0.0:4317'}}}}},
 'storage':{'trace':{'backend':'local','wal':{'path':'/var/tempo/wal'},'local':{'path':'/var/tempo/blocks'}}},
 'backend_worker':{'compaction':{'block_retention':'48h'}},'usage_report':{'reporting_enabled':False}}
loki={'auth_enabled':False,'server':{'http_listen_port':3100,'grpc_listen_port':9096},
 'common':{'instance_addr':'127.0.0.1','path_prefix':'/loki','replication_factor':1,
 'ring':{'kvstore':{'store':'inmemory'}},'storage':{'filesystem':{'chunks_directory':'/loki/chunks','rules_directory':'/loki/rules'}}},
 'schema_config':{'configs':[{'from':'2020-10-24','store':'tsdb','object_store':'filesystem','schema':'v13','index':{'prefix':'index_','period':'24h'}}]},
 'storage_config':{'tsdb_shipper':{'active_index_directory':'/loki/index','cache_location':'/loki/index-cache'}},
 'ingester':{'wal':{'dir':'/loki/wal'}},
 'compactor':{'working_directory':'/loki/compactor','compaction_interval':'10m','retention_enabled':True,'retention_delete_delay':'2h','retention_delete_worker_count':10,'delete_request_store':'filesystem'},
 'limits_config':{'allow_structured_metadata':True,'retention_period':'72h'},'analytics':{'reporting_enabled':False}}
collector={'extensions':{'health_check':{'endpoint':'0.0.0.0:13133'}},
 'receivers':{'otlp':{'protocols':{'http':{'endpoint':'0.0.0.0:4318'}}}},
 'processors':{'memory_limiter':{'check_interval':'1s','limit_mib':192,'spike_limit_mib':32},'batch':{'timeout':'1s','send_batch_size':256}},
 'exporters':{'otlp/tempo':{'endpoint':'photo-tempo.monitoring.svc.cluster.local:4317','tls':{'insecure':True}},
 'otlphttp/loki':{'endpoint':'http://photo-loki.monitoring.svc.cluster.local:3100/otlp'},
 'prometheus':{'endpoint':'0.0.0.0:8889','resource_to_telemetry_conversion':{'enabled':True}}},
 'service':{'extensions':['health_check'],'pipelines':{
 'traces':{'receivers':['otlp'],'processors':['memory_limiter','batch'],'exporters':['otlp/tempo']},
 'logs':{'receivers':['otlp'],'processors':['memory_limiter','batch'],'exporters':['otlphttp/loki']},
 'metrics':{'receivers':['otlp'],'processors':['memory_limiter','batch'],'exporters':['prometheus']}}}}


def resource(kind,name,spec=None,**extra):
    value={'apiVersion':'v1','kind':kind,'metadata':{'name':name,'namespace':NS}}
    if spec is not None:value['spec']=spec
    value.update(extra)
    return value


def component(name,image,config,args,ports,uid,memory,volume=None):
    config_text=yaml.safe_dump(config,sort_keys=False)
    yield resource('ConfigMap',name+'-config',data={'config.yaml':config_text})
    mounts=[{'name':'config','mountPath':'/etc/photo-observability','readOnly':True}]
    volumes=[{'name':'config','configMap':{'name':name+'-config'}}]
    if volume:
        yield resource('PersistentVolumeClaim',name,{'accessModes':['ReadWriteOnce'],'storageClassName':'local-path','resources':{'requests':{'storage':'5Gi'}}})
        mounts.append({'name':'data','mountPath':volume})
        volumes.append({'name':'data','persistentVolumeClaim':{'claimName':name}})
    ready=3200 if name=='photo-tempo' else 3100 if name=='photo-loki' else 13133
    container={'name':name,'image':image,'args':args,'ports':[{'name':n,'containerPort':p} for n,p in ports],
      'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':memory}},
      'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},
      'volumeMounts':mounts,'readinessProbe':{'httpGet':{'path':'/ready' if volume else '/','port':ready},'initialDelaySeconds':10,'periodSeconds':5},
      'livenessProbe':{'httpGet':{'path':'/ready' if volume else '/','port':ready},'initialDelaySeconds':90,'periodSeconds':20,'failureThreshold':6}}
    yield resource('Deployment',name,{'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app':name}},
      'template':{'metadata':{'labels':{'app':name},'annotations':{'checksum/config':hashlib.sha256(config_text.encode()).hexdigest()}},
      'spec':{'nodeSelector':{'kubernetes.io/hostname':NODE},'securityContext':{'runAsNonRoot':True,'runAsUser':uid,'runAsGroup':uid,'fsGroup':uid},
        'containers':[container],'volumes':volumes}}},apiVersion='apps/v1')
    service=resource('Service',name,{'selector':{'app':name},'ports':[{'name':n,'port':p,'targetPort':n} for n,p in ports]})
    service['metadata']['labels']={'app':name}
    yield service


def resources():
    yield from component('photo-tempo','grafana/tempo:3.1.0',tempo,['-config.file=/etc/photo-observability/config.yaml'],[('http',3200),('otlp-grpc',4317)],10001,'1Gi','/var/tempo')
    yield from component('photo-loki','grafana/loki:3.7.10',loki,['-config.file=/etc/photo-observability/config.yaml','-target=all'],[('http',3100)],10001,'512Mi','/loki')
    yield from component('photo-otel','otel/opentelemetry-collector-contrib:0.165.0',collector,['--config=/etc/photo-observability/config.yaml'],[('otlp-http',4318),('metrics',8889),('health',13133)],10001,'256Mi')
    yield resource('Middleware','photo-otel-private',{'ipAllowList':{'sourceRange':['192.168.4.0/24','100.64.0.0/10','10.42.0.0/16']}},apiVersion='traefik.io/v1alpha1')
    yield resource('IngressRoute','photo-otel',{'entryPoints':['websecure'],'routes':[{'match':'Host(`photo-otel.app.home.panderosystems.com`)','kind':'Rule',
      'middlewares':[{'name':'photo-otel-private'}],'services':[{'name':'photo-otel','port':4318}]}],'tls':{}},apiVersion='traefik.io/v1alpha1')
    monitor=resource('ServiceMonitor','photo-otel',{'selector':{'matchLabels':{'app':'photo-otel'}},'endpoints':[{'port':'metrics','interval':'15s'}]},apiVersion='monitoring.coreos.com/v1')
    monitor['metadata']['labels']={'release':'kube-prometheus-stack'}
    yield monitor
    sources={'apiVersion':1,'datasources':[
      {'name':'Photo traces','uid':'photo-tempo','type':'tempo','access':'proxy','url':'http://photo-tempo.monitoring.svc.cluster.local:3200',
       'jsonData':{'tracesToLogsV2':{'datasourceUid':'photo-loki','spanStartTimeShift':'-1m','spanEndTimeShift':'1m','customQuery':True,
        'query':'{service_name="photo-review"} | json | trace_id="$${__span.traceId}"'}}},
      {'name':'Photo logs','uid':'photo-loki','type':'loki','access':'proxy','url':'http://photo-loki.monitoring.svc.cluster.local:3100',
       'jsonData':{'derivedFields':[{'name':'TraceID','matcherRegex':'"trace_id":\\s*"([a-f0-9]{32})"','datasourceUid':'photo-tempo','url':'$${__value.raw}'}]}}]}
    ds=resource('ConfigMap','photo-observability-datasources',data={'datasources.yaml':yaml.safe_dump(sources,sort_keys=False)})
    ds['metadata']['labels']={'grafana_datasource':'1'}
    yield ds


if __name__=='__main__':
    print(yaml.safe_dump_all(resources(),sort_keys=False),end="")
