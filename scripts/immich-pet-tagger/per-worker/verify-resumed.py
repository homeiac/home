#!/usr/bin/env python3
"""Verify restored original process identity, responsiveness and CPU progress."""
import argparse,json,time,urllib.request,urllib.error
from pathlib import Path
import psutil
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--session',default='aba');a=p.parse_args();study=a.directory/('contention-'+a.session)
rows=json.loads((study/'resume.json').read_text());before={};result=[]
for row in rows:
 process=psutil.Process(row['pid']);assert process.create_time()==row['created'] and process.name()=='llama-server';assert process.status()!=psutil.STATUS_STOPPED
 before[process.pid]=sum(process.cpu_times()[:2])
 args=process.cmdline();port=None
 for index,arg in enumerate(args):
  if arg=='--port' and index+1<len(args):port=int(args[index+1])
 if port is None:port=8080
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=5) as response:status=response.status
 except urllib.error.HTTPError as error:status=error.code
 result.append({'pid':process.pid,'identity_preserved':True,'state':process.status(),'health_http':status})
time.sleep(2)
for row in result:
 process=psutil.Process(row['pid']);row['cpu_seconds_after_resume_probe']=sum(process.cpu_times()[:2])-before[process.pid];assert process.status()!=psutil.STATUS_STOPPED
(study/'resume-health.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
