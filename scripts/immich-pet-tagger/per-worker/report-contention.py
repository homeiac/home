#!/usr/bin/env python3
"""Export aggregate ABA timings and verified resume state; never process IDs/media."""
import argparse,json,statistics
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--session',default='aba');p.add_argument('--output',type=Path,required=True);a=p.parse_args();study=a.directory/('contention-'+a.session)
verified=json.loads((study/'verified.json').read_text());assert verified['state']=='complete' and verified['stopped']==verified['resumed'] and not verified['watchdog_fired']
health=json.loads((study/'resume-health.json').read_text());assert all(r['identity_preserved'] and r['state']!='stopped' and r['health_http']==200 for r in health)
aggregate=json.loads((a.directory/'aggregate.json').read_text());phases={};truth={}
for phase in ['before','paused','resumed']:
 start=json.loads((study/(phase+'-start.json')).read_text());end=json.loads((study/(phase+'-end.json')).read_text())
 initial={r['pid']:r for r in start['servers']};final={r['pid']:r for r in end['servers']};assert set(initial)==set(final),'Competing server membership changed'
 trials={}
 for variant in ['mac-mps','mac-cpu','hybrid']:
  label=a.session+'-'+phase+'-'+variant;trial=aggregate['trials'][label];passes=trial['passes'];rows=[json.loads(r) for r in (a.directory/label/'rows.jsonl').read_text().splitlines()]
  decisions={(r['pass'],r['index']):r['matched'] for r in rows}
  if truth:assert decisions==truth,'Decision drift across ABA'
  else:truth=decisions
  seconds=sum(r['seconds'] for r in passes)
  trials[variant]={'photos':sum(r['photos'] for r in passes),'photos_per_minute':sum(r['photos'] for r in passes)*60/seconds,'pass_rates':[r['photos_per_minute'] for r in passes],'mean_detect_ms':statistics.mean(r['detect'] for r in rows)*1000,'mean_embed_ms':statistics.mean(r['embed'] for r in rows)*1000,'mean_decode_ms':statistics.mean(r['decode'] for r in rows)*1000,'true_positive_per_pass':[r['true_positive'] for r in passes],'false_positive_per_pass':[r['false_positive'] for r in passes]}
 phases[phase]={'start_host':start['host'],'end_host':end['host'],'competing_process_count':len(initial),'competing_cpu_seconds':sum(final[pid]['cpu_seconds']-r['cpu_seconds'] for pid,r in initial.items()),'all_competitors_stopped':all(r['status']=='stopped' for r in start['servers']+end['servers']),'trials':trials}
assert phases['paused']['all_competitors_stopped'] and phases['paused']['competing_cpu_seconds']<.05
report={'state':'complete','protocol':'before/paused/resumed; same26 photos; one process; two threads; two reversed passes per variant','verification':{k:v for k,v in verified.items() if k!='at'},'resume_health_http':[r['health_http'] for r in health],'resume_cpu_seconds_after_health_probe':sum(r['cpu_seconds_after_resume_probe'] for r in health),'phases':phases,'binary_decisions_compared_per_trial':len(truth),'all_binary_decisions_identical':True,'limits':['One ABA cycle, shared live host; not a precise reconstruction of historical contention','Pausing removes competing CPU and GPU submission together; CPU-only control measures broader scheduling effects','Same process memory retained; no exclusive kernel-time or thermal attribution','13 negative controls do not establish population precision']}
control=aggregate['trials'].get(a.session+'-control-still-fawn')
if control:
 passes=control['passes'];seconds=sum(r['seconds'] for r in passes)
 report['refreshed_still_fawn_control']={'photos_per_minute':sum(r['photos'] for r in passes)*60/seconds,'pass_rates':[r['photos_per_minute'] for r in passes],'true_positive_per_pass':[r['true_positive'] for r in passes],'false_positive_per_pass':[r['false_positive'] for r in passes]}
 report['quiet_metal_vs_still_fawn']=phases['paused']['trials']['mac-mps']['photos_per_minute']/report['refreshed_still_fawn_control']['photos_per_minute']
 report['quiet_hybrid_vs_still_fawn']=phases['paused']['trials']['hybrid']['photos_per_minute']/report['refreshed_still_fawn_control']['photos_per_minute']
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
