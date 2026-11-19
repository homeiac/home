#!/usr/bin/env python3
"""Verify stored traces/logs and scraped photo metrics via temporary read-only forwards."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.parse
import urllib.request


def main():
    env=dict(os.environ,KUBECONFIG=os.environ.get('KUBECONFIG',str(Path.home()/'kubeconfig')))
    forwards=[];ports={}
    def get(service,path,text=False):
        with urllib.request.urlopen(f'http://127.0.0.1:{ports[service]}'+path,timeout=10) as response:
            data=response.read().decode()
            return data if text else json.loads(data)
    try:
        for service,remote in [('photo-otel',8889),('photo-tempo',3200),('photo-loki',3100),('kube-prometheus-stack-prometheus',9090)]:
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            ports[service]=port
            forwards.append(subprocess.Popen(['kubectl','-n','monitoring','port-forward','service/'+service,f'{port}:{remote}'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
            for _ in range(30):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
                except OSError:time.sleep(.2)
            else:raise RuntimeError('Port-forward unavailable: '+service)
        metrics=get('photo-otel','/metrics',True)
        names=sorted({line.split('{')[0].split()[0] for line in metrics.splitlines() if line.startswith('photo_app_')})
        print('Collector metric families:',names,flush=True)
        if not names:raise RuntimeError('No photo app metrics received')
        traces=get('photo-tempo','/api/search?'+urllib.parse.urlencode({'q':'{resource.service.name="photo-review"}','limit':5}))
        print('Stored photo traces:',len(traces.get('traces',[])),flush=True)
        if not traces.get('traces'):raise RuntimeError('No stored photo traces')
        query={'query':'{service_name=~"photo-review|photo-triage"}','limit':20,'start':str(int((time.time()-900)*1e9))}
        logs=get('photo-loki','/loki/api/v1/query_range?'+urllib.parse.urlencode(query))
        records=[json.loads(value) for stream in logs['data']['result'] for _,value in stream['values']]
        print('Stored structured log events:',sorted({r.get('event') for r in records}),flush=True)
        if not records:raise RuntimeError('No stored structured photo logs')
        prometheus='kube-prometheus-stack-prometheus'
        for expr in ['count(photo_app_http_requests_total{service_name="photo-review"})',
            'count(photo_app_pg_pool_connections{service_name="photo-review"})',
            'count(photo_app_db_duration_seconds_count{stage="duckdb.query"})',
            'min(photo_app_probe_success{probe="api"})']:
            result=get(prometheus,'/api/v1/query?'+urllib.parse.urlencode({'query':expr}))['data']['result']
            print(expr, [row['value'][1] for row in result],flush=True)
            if not result or float(result[0]['value'][1])<=0:raise RuntimeError('Missing/failed metric: '+expr)
        import runpy
        dashboard=runpy.run_path(str(Path(__file__).with_name('gen-photo-app-dashboard.py')))['dashboard']()
        for panel in dashboard['panels']:
            for target in panel.get('targets',[]):
                if panel['datasource']['type']=='prometheus':
                    get(prometheus,'/api/v1/query?'+urllib.parse.urlencode({'query':target['expr']}))
        print('Photo dashboard PromQL: all valid')
    finally:
        for process in forwards:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill()


if __name__=='__main__':main()
