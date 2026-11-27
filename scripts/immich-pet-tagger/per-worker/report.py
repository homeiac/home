#!/usr/bin/env python3
"""Aggregate exact-byte stage timings and decision agreement; never export IDs."""
import argparse,json,statistics,hashlib
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
report={'trials':{},'network':{}};decisions={}
for folder in sorted(a.directory.iterdir()):
 if not folder.is_dir() or not (folder/'metadata.json').exists():continue
 meta=json.loads((folder/'metadata.json').read_text())
 if 'after' not in meta:continue
 rows=[json.loads(line) for line in (folder/'rows.jsonl').read_text().splitlines()]
 assert len(rows)==52 and {(r['pass'],r['index']) for r in rows}=={(rep,i) for rep in [0,1] for i in range(26)}, 'Incomplete or duplicate trial'
 passes=[]
 for rep in sorted({r['pass'] for r in rows}):
  group=[r for r in rows if r['pass']==rep];seconds=meta.get('pass_wall_seconds',[sum(r['total'] for r in rows if r['pass']==n) for n in [0,1]])[rep]
  passes.append({'pass':rep,'photos':len(group),'photos_per_minute':len(group)*60/seconds,'seconds':seconds,'means':{key:statistics.mean(r[key] for r in group) for key in ['decode','detect','embed','classify','total']},'true_positive':sum(r['matched'] and r['expected']=='positive' for r in group),'false_positive':sum(r['matched'] and r['expected']=='negative' for r in group)})
 decisions[folder.name]={(r['pass'],r['index']):r['matched'] for r in rows}
 report['trials'][folder.name]={'metadata':{k:v for k,v in meta.items() if k not in ['pid','before','after']},'passes':passes,'cpu_seconds':meta['after']['cpu']-meta['before']['cpu'],'wall_seconds':meta['after']['wall']-meta['before']['wall'],'rss_peak':meta['after']['rss']}
 for key in ['nr_throttled','throttled_usec']:
  def value(s):return int(next((line.split()[1] for line in s.splitlines() if line.startswith(key+' ')),'0'))
  if '/sys/fs/cgroup/cpu.stat' in meta['after']:report['trials'][folder.name][key+'_delta']=value(meta['after']['/sys/fs/cgroup/cpu.stat'])-value(meta['before']['/sys/fs/cgroup/cpu.stat'])
for backend in ['mac','still-fawn']:
 file=a.directory/(backend+'-network.json')
 if not file.exists():continue
 rows=json.loads(file.read_text());groups=[]
 for rep in [0,1]:
  for mode in ['fresh','pooled']:
   group=[r for r in rows if r['pass']==rep and r['mode']==mode]
   groups.append({'pass':rep,'mode':mode,'mean_ms':statistics.mean(r['seconds'] for r in group)*1000,'median_ms':statistics.median(r['seconds'] for r in group)*1000,'bytes':sum(r['bytes'] for r in group)})
 report['network'][backend]=groups
 report['network'][backend+'_stable_hashes']=all(len({r['sha256'] for r in rows if r['index']==i})==1 for i in range(26))
metas=[v['metadata'] for v in report['trials'].values()]
for field in ['manifest_sha256','classifier_sha256','weights_sha256','clip_sha256']:
 assert len({m[field] for m in metas})<=1, 'Mismatched '+field
report['agreement']=[{'a':x,'b':y,'compared':len(set(decisions[x])&set(decisions[y])),'differences':sum(decisions[x][k]!=decisions[y][k] for k in set(decisions[x])&set(decisions[y]))} for x in decisions for y in decisions if x<y]
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
