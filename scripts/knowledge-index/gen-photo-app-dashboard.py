#!/usr/bin/env python3
"""Generate the photo GUI latency, live-request and automated-triage dashboard."""
import json
import yaml

PROM={'type':'prometheus','uid':'prometheus'}
panels=[]


def panel(title,expr,x,y,w=8,h=6,kind='timeseries',unit='short',legend='{{route}}'):
    panels.append({'id':len(panels)+1,'title':title,'type':kind,'datasource':PROM,
        'gridPos':{'x':x,'y':y,'w':w,'h':h},'targets':[{'refId':'A','expr':expr,'legendFormat':legend}],
        'fieldConfig':{'defaults':{'unit':unit},'overrides':[]},
        'options':{'legend':{'displayMode':'list','placement':'bottom'},'reduceOptions':{'calcs':['lastNotNull']}}})


def dashboard():
    panels.clear()
    panel('Independent API probe','min(photo_app_probe_success{probe="api"})',0,0,6,4,'stat')
    panel('Requests waiting for the DB lock','max(photo_app_lock_waiters{service_name="photo-review"})',6,0,6,4,'stat')
    panel('Oldest unfinished request','max(photo_app_oldest_request_seconds{service_name="photo-review"})',12,0,6,4,'stat','s')
    panel('Time since automated triage','time()-max(photo_app_triage_timestamp_seconds)',18,0,6,4,'stat','s')
    panel('Requests per second','sum by(route)(rate(photo_app_http_requests_total{service_name="photo-review"}[5m]))',0,4,12,7,legend='{{route}}')
    panel('Request latency p95','histogram_quantile(0.95,sum by(le,route)(rate(photo_app_http_duration_seconds_bucket{service_name="photo-review"}[5m])))',12,4,12,7,unit='s')
    panel('Errors and busy responses','sum by(route,status)(rate(photo_app_http_requests_total{service_name="photo-review",status=~"5.."}[5m]))',0,11,12,7,legend='{{route}} · {{status}}')
    panel('Database time: PostgreSQL vs DuckDB','sum by(stage)(rate(photo_app_db_duration_seconds_sum{service_name="photo-review"}[5m]))',12,11,12,7,unit='s',legend='{{stage}}')
    panel('DB lock wait p95','histogram_quantile(0.95,sum by(le)(rate(photo_app_lock_wait_seconds_bucket{service_name="photo-review"}[5m])))',0,18,8,6,unit='s')
    panel('In-flight requests','max(photo_app_inflight{service_name="photo-review"})',8,18,8,6)
    panel('Automatic diagnostic incident','max(photo_app_triage_incident)',16,18,8,6,'stat')
    panel('PostgreSQL pooled connections in use','photo_app_pg_pool_connections{service_name="photo-review"}-photo_app_pg_pool_idle{service_name="photo-review"}',0,24,8,6,legend='{{pool}}')
    panel('PostgreSQL requests waiting for a connection','photo_app_pg_pool_waiting{service_name="photo-review"}',8,24,8,6,legend='{{pool}}')
    panel('Connection pool wait p95','histogram_quantile(0.95,sum by(le,pool)(rate(photo_app_pool_wait_seconds_bucket{service_name="photo-review"}[5m])))',16,24,8,6,unit='s',legend='{{pool}}')
    panels.append({'id':len(panels)+1,'title':'Slow requests, errors and automatic diagnosis · trace IDs link to Photo traces','type':'logs',
      'datasource':{'type':'loki','uid':'photo-loki'},'gridPos':{'x':0,'y':30,'w':24,'h':12},
      'targets':[{'refId':'A','expr':'{service_name=~"photo-review|photo-triage|photo-context"} | json | event=~"request.slow|request.error|triage.result|matching.finished|context.finished|context.error|context.deferred"','queryType':'range'}],
      'options':{'showTime':True,'wrapLogMessage':True,'sortOrder':'Descending','enableLogDetails':True}})
    panel('GPS context backlog','sum by(kind)(photo_context_jobs)',0,42,8,6,legend='{{kind}}')
    panel('GPS lookup and local LLM stage time','sum by(stage)(rate(photo_context_stage_seconds_total[5m]))',8,42,8,6,unit='s',legend='{{stage}}')
    panel('GPS lookup cache use since worker start','sum by(kind)(photo_context_inventory)',16,42,8,6,legend='{{kind}}')
    return {'uid':'photo-app','title':'Photo App · Requests, traces & triage','schemaVersion':39,'version':1,
      'tags':['photos','otel'],'refresh':'10s','time':{'from':'now-1h','to':'now'},'timezone':'browser','panels':panels,
      'description':'Request telemetry from OpenTelemetry; independent health checks run every minute. Slow requests are logged before their spans finish. DuckDB queries use Parquet snapshots plus live PostgreSQL review edits.',
      'links':[{'title':'Photo GUI','url':'https://photos.app.home.panderosystems.com'},
        {'title':'Pipeline value stream map','url':'/d/knowledge-index/knowledge-index'},
        {'title':'Explore traces and logs','url':'/explore'}]}


if __name__=='__main__':
    print(yaml.safe_dump({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'grafana-dashboard-photo-app','namespace':'monitoring',
      'labels':{'grafana_dashboard':'1'},'annotations':{'grafana_folder':'Homelab'}},
      'data':{'photo-app.json':json.dumps(dashboard(),indent=2)}},sort_keys=False),end='')
