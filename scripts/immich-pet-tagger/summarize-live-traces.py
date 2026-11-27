#!/usr/bin/env python3
"""Summarize real worker samples without mistaking waiting samples for GPU time."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import plistlib
import re

p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--output',type=Path);args=p.parse_args()

def sample(path):
    lines=path.read_text().splitlines();starts=[i for i,line in enumerate(lines) if re.match(r'^    \d+ Thread_',line)]
    body=lines[starts[0]:starts[1]];total=int(body[0].split()[0]);nodes=[]
    for line in body[1:]:
        match=re.match(r'^([ +!|:]*)(\d+) (.+)$',line)
        if match:nodes.append((len(match[1]),int(match[2]),match[3]))
    stack=[];counts=Counter()
    for index,(depth,count,text) in enumerate(nodes):
        while stack and stack[-1][0]>=depth:stack.pop()
        stack.append((depth,text))
        if index+1<len(nodes) and nodes[index+1][0]>depth:continue
        frames='\n'.join(s for _,s in stack)
        if 'SSLSocket_do_handshake' in frames:kind='TLS_handshake'
        elif 'SSLSocket_read' in frames:kind='HTTPS_read'
        elif 'sock_connect' in frames:kind='TCP_connect'
        elif 'time_sleep' in frames:kind='sleep'
        elif 'PyThread_acquire_lock' in frames:kind='Python_condition_wait'
        else:kind='other'
        counts[kind]+=count
    assert sum(counts.values())==total,(path,total,counts)
    return {'file':path.name,'main_thread_samples':total,'samples':dict(counts),'percent':{k:round(v*100/total,2) for k,v in counts.items()}}

reports={'samples':[sample(path) for path in sorted(args.directory.glob('*.sample.txt'))],
         'limits':['Native sample percentages are main-thread wall-stack observations, not CPU utilization or exclusive GPU kernel time.',
                   'HTTPS_read includes waiting on remote application work as well as network transport; it is not proof of bandwidth saturation.',
                   'Python condition waits include asynchronous model workers; these do not measure GPU occupancy.',
                   'Traces attach to real workers and real photos under shared load. Different windows/photos are not a matched hardware benchmark.']}
for path in sorted(args.directory.glob('*-still-fawn-live.json')):
    r=json.loads(path.read_text());elapsed=r['after']['at']-r['before']['at']
    def ticks(stat):
        fields=stat[stat.rindex(')')+2:].split();return int(fields[11])+int(fields[12])
    r['cpu_cores']=(ticks(r['after']['process'])-ticks(r['before']['process']))/r['clock_ticks']/elapsed
    reports.setdefault('linux',[]).append({'file':path.name,'elapsed':elapsed,'cpu_cores':r['cpu_cores'],'trace':r['trace']})
for path in sorted(args.directory.glob('*-nettop.csv')):
    groups={}
    for row in csv.reader(path.open()):
        if not row or row[0]=='time':continue
        if len(row)>8:groups.setdefault(row[1],[]).append(row)
    values=[]
    for name,rows in groups.items():
        first,last=rows[0],rows[-1]
        def seconds(value):
            h,m,s=value.split(':');return int(h)*3600+int(m)*60+float(s)
        elapsed=seconds(last[0])-seconds(first[0])
        if elapsed<=0:continue
        values.append({'process':name,'seconds':elapsed,'received_bytes':int(last[4])-int(first[4]),
                       'sent_bytes':int(last[5])-int(first[5]),'retransmitted_bytes':int(last[8])-int(first[8]),
                       'receive_megabits_per_second':8*(int(last[4])-int(first[4]))/elapsed/1e6})
    reports.setdefault('network',[]).append({'file':path.name,'processes':values})
output=json.dumps(reports,indent=2)+'\n'
for path in sorted(args.directory.glob('*-sudo*/powermetrics.plist')):
    records=[plistlib.loads(part.strip()) for part in path.read_bytes().split(b'\0') if part.strip()]
    metadata=dict(line.split('=',1) for line in (path.parent/'metadata.txt').read_text().splitlines() if '=' in line)
    pid=int(metadata['pid']);elapsed=sum(r['elapsed_ns'] for r in records)
    tasks=[t for r in records for t in r['tasks'] if t['pid']==pid]
    reports.setdefault('privileged_mac',[]).append({
        'directory':path.parent.name,'records':len(records),'elapsed_seconds':elapsed/1e9,
        'thermal_pressure':dict(Counter(r['thermal_pressure'] for r in records)),
        'whole_host_gpu_busy_percent':100*sum((1-r['gpu']['idle_ratio'])*r['elapsed_ns'] for r in records)/elapsed,
        'metal_worker_records':len(tasks),'metal_worker_reported_cpu_seconds':sum(t['cputime_ns'] for t in tasks)/1e9,
        'metal_worker_reported_received_bytes':sum(t['bytes_received'] for t in tasks),
        'task_gpu_fields':sorted({k for r in records for t in r['tasks'] for k in t if 'gpu' in k.lower()}),
        'dtrace_status':metadata.get('dtrace_status'),'dtrace_output_bytes':(path.parent/'dtrace.txt').stat().st_size,
        'powermetrics_status':metadata.get('powermetrics_status'),
        'powermetrics_warnings':dict(Counter((path.parent/'powermetrics.stderr').read_text().splitlines())),
        'limits':['Whole-host GPU activity cannot be attributed to this worker when task GPU fields are absent.',
                  'Reported worker CPU/bytes aggregate emitted task records only; idle task records may be omitted.',
                  'This capture overlaps a missing-preview/backoff interval, not steady productive inference.']})
output=json.dumps(reports,indent=2)+'\n'
if args.output:args.output.write_text(output)
print(output)
