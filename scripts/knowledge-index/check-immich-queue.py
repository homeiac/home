#!/usr/bin/env python3
"""Read current Immich queue depth and recent progress without credentials or writes."""
import argparse
import json
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('queue', choices=['ocr', 'thumbnail_generation', 'face_detection', 'facial_recognition', 'metadata', 'video_conversion'])
args = parser.parse_args()
selector = 'immich_queue_jobs{queue="'+args.queue+'"}'
queries = [
    {'name':'current_states', 'expr':selector},
    {'name':'states_five_minutes_ago', 'expr':selector+' offset 5m'},
    {'name':'telemetry_age_seconds', 'expr':'time()-immich_observer_last_success_timestamp_seconds{source="queues"}'},
    {'name':'ocr_completed_last_five_minutes', 'expr':'sum(increase(immich_jobs_ocr_success_total{namespace="immich-pilot",endpoint="metrics-ms"}[5m]))'},
    {'name':'ocr_success_counter', 'expr':'sum(immich_jobs_ocr_success_total{namespace="immich-pilot",endpoint="metrics-ms"})'},
    {'name':'ocr_failed_counter', 'expr':'sum(immich_jobs_ocr_failed_total{namespace="immich-pilot",endpoint="metrics-ms"})'},
    {'name':'ocr_failed_last_five_minutes', 'expr':'sum(increase(immich_jobs_ocr_failed_total{namespace="immich-pilot",endpoint="metrics-ms"}[5m]))'},
    {'name':'ocr_peak_success_per_minute_two_hours', 'expr':'max_over_time((sum(rate(immich_jobs_ocr_success_total{namespace="immich-pilot",endpoint="metrics-ms"}[5m]))*60)[2h:1m])'},
]
code = """let input='';for await(const c of process.stdin)input+=c;
for(const q of JSON.parse(input)){
 const r=await fetch('http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090/api/v1/query?query='+encodeURIComponent(q.expr));
 const data=await r.json();console.log(JSON.stringify({name:q.name,status:data.status,error:data.error,samples:data.data?.result?.map(x=>({labels:x.metric,value:x.value[1],timestamp:x.value[0]}))}));
}"""
command=['kubectl','--kubeconfig',os.environ.get('KUBECONFIG',str(Path.home()/'kubeconfig')),'-n','immich-pilot','exec','-i','deployment/immich-server','--','node','--input-type=module','-e',code]
result=subprocess.run(command,input=json.dumps(queries),text=True,capture_output=True,check=True)
print(result.stdout,end='')
