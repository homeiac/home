#!/usr/bin/env python3
"""Summarize continuous-production evidence, explicitly retaining incomplete status."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
folder=root/'docs/experiments/waffles'
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true')
args=parser.parse_args()
path=folder/'2026-11-26-continuous-production.jsonl'
rows=[json.loads(line) for line in path.read_text().splitlines()]
protocols=[(n,r) for n,r in enumerate(rows) if r['event']=='protocol']
start,protocol=protocols[-1];session=rows[start:]
trials=[r for r in session if r['event']=='trial_finished']
complete=next((r for r in reversed(session) if r['event']=='experiment_completed'),None)
failed=[r for r in session if r['event']=='experiment_failed']
lines=['# Waffles continuous-production results','',
       '**Status: '+('complete' if complete else 'interrupted / incomplete' if failed else 'running')+'.**', '',
       'Baseline production workers remained separate from the extra-worker benchmark. Mac baseline uses Metal; Linux baselines use CPU. Chief-horse is guarded standby and RTX is unused.', '',
       'The frozen sample contains 122 photos including 13 Waffles and 13 non-Waffles controls. A valid trial requires at least 9 true positives, zero false positives, unchanged binary decisions, one attempt and no unexpected process exits. These selected controls do not establish library-wide accuracy.', '',
       '| Backend / device | Extra processes | CPU lanes | Pass | Photos/min | Mean seconds/photo | TP / FP | Valid |',
       '|---|---:|---:|---|---:|---:|---|---|']
for r in trials:
    lines.append('| '+str(r.get('worker','combined'))+' / '+str(r.get('device','mixed'))+' | '+str(r.get('slots','—'))+' | '+str(r.get('cores') or 'default')+' | '+r['run'].split('-')[-1]+' | '+f"{r['photos_per_minute']:.1f}"+' | '+f"{r['mean_processing_seconds']:.3f}"+' | '+str(r['accuracy']['true_positive'])+' / '+str(r['accuracy']['false_positive'])+' | '+str(r['valid'])+' |')
lines+=['','## Selected settings','']
for r in session:
    if r['event']=='backend_selected':
        lines.append(f"- {r['worker']}: {r['slots']} extra {r['device']} processes, {r['cores'] or 'default'} CPU lanes; paired rate {r['photos_per_minute']:.1f} photos/min. "+('Final selection.' if complete else 'Provisional; the complete experiment has not passed.'))
if complete:
    groups=defaultdict(list)
    for r in trials:
        if '-pool-' in r['run']:groups[r['run'].split('-')[-2]].append(r)
    rates={k:60*sum(r['photos'] for r in v)/sum(r['wall_seconds'] for r in v) for k,v in groups.items()}
    if set(rates)=={'before','after'}:
        lines+=['',f"Combined extra capacity: **{rates['before']:.1f} → {rates['after']:.1f} photos/min ({rates['after']/rates['before']:.2f}×)** on identical benchmark inputs while baseline production continued. This is not a baseline-only versus total-production speedup.",'']
    else:lines+=['','Combined comparison was not eligible; no before/after gain is claimed.','']
    lines.append('Production completions during the experiment: '+', '.join(f"{w} {n-protocol['production_start'][w]:,}" for w,n in complete['production_end'].items())+'.')
for r in failed:lines+=['',f"Failure retained: {r['reason']} ({r['error_type']}). Extra capacity restored; baseline production is not paused by this runner."]
for r in session:
    if r['event']=='trial_failed':lines+=['',f"Trial failure retained: {r['worker']} {r['device']} {r['slots']} extras, attempt {r['attempt']}: {r['reason']}."]
samples=[r['observation'] for r in session if r['event']=='resource_sample']
if samples:
    lines+=['','## Observed resource ranges','',
            f"Mac whole-system CPU: {min(s['mac']['cpu_percent'] for s in samples):.1f}–{max(s['mac']['cpu_percent'] for s in samples):.1f}%. Apple GPU: {min(s['mac'].get('gpu_percent',0) for s in samples):.0f}–{max(s['mac'].get('gpu_percent',0) for s in samples):.0f}%. These include other applications.",
            f"Mac system swap at first/last sample: {samples[0]['mac']['swap_bytes']/1024**3:.2f}/{samples[-1]['mac']['swap_bytes']/1024**3:.2f} GiB. This includes preexisting swap; it is not attributed entirely to Waffles.",
            f"still-fawn maximum observed host temperature: {max(s['still-fawn']['temperature_c'] for s in samples):.1f}°C."]
lines+=['','## Provenance','',f"Session `{protocol['session']}`; code revision `{protocol['git_revision']}`.",f"Sample SHA-256 `{protocol['sample_sha256']}`.",f"Classifier SHA-256 `{protocol['classifier_sha256']}`.",'','[Protocol](2026-11-26-continuous-production.md) · [Append-only journal](2026-11-26-continuous-production.jsonl)','']
text='\n'.join(lines)
if args.write:(folder/'2026-11-26-continuous-production-results.md').write_text(text)
print(text)
