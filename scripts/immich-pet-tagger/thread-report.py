#!/usr/bin/env python3
"""Render the one-model CPU-thread journal with uncertainty and failed attempts."""
import argparse
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2];folder=root/'docs/experiments/waffles'
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');args=parser.parse_args()
rows=[json.loads(l) for l in (folder/'2026-11-26-cpu-threads.jsonl').read_text().splitlines()]
start=max(i for i,r in enumerate(rows) if r['event']=='protocol');rows=rows[start:];protocol=rows[0]
complete=next((r for r in reversed(rows) if r['event']=='experiment_completed'),None)
failure=next((r for r in reversed(rows) if r['event']=='experiment_failed'),None)
lines=['# One-model CPU-thread results','', '**Status: '+('complete' if complete else 'incomplete / stopped' if failure else 'running')+'.**','',
       'One extra Mac CPU process; baseline Metal and all admitted production workers stay running. Same 122 photos, six excluded warm-up photos, reverse order on the second pass. Earlier process-sweep environment variables did not verify the detector thread count; this phase explicitly controls the pinned Ultralytics selector.','',
       '| Threads | Pass | Photos/min | Mean seconds/photo | TP / FP | Valid |','|---:|---|---:|---:|---|---|']
for r in rows:
    if r['event']=='trial_finished':lines.append(f"| {r['threads']} | {r['run'].split('-')[-1]} | {r['photos_per_minute']:.1f} | {r['mean_processing_seconds']:.3f} | {r['accuracy']['true_positive']} / {r['accuracy']['false_positive']} | {r['valid']} |")
if complete:
    value=complete['selected'];selection=next(r for r in rows if r['event']=='threads_selected')
    before=next(c for c in selection['candidates'] if c['threads']==2)
    lines+=['',f"Selected **{value['threads']} threads**: {value['photos_per_minute']:.1f} photos/min pooled over two passes, range {value['range'][0]:.1f}–{value['range'][1]:.1f}. Fewest threads within 5% of fastest eligible configuration.",
            f"Two-thread reference: {before['photos_per_minute']:.1f} photos/min; selected/reference ratio {value['photos_per_minute']/before['photos_per_minute']:.2f}×. This measures extra-worker benchmark throughput, not total-production speedup."]
    lines+=['','Production completions during the experiment: '+', '.join(f"{w} {n-protocol['production_start'][w]:,}" for w,n in complete['production_end'].items())+'.']
if failure:lines+=['','Failure retained: '+failure['reason']+'. Previous extra policy was restored; no completed winner is claimed.']
samples=[r['observation']['mac'] if r['event']=='resource_sample' else r['observation'] for r in rows if r['event'] in ('resource_sample','memory_warning_followup')]
if samples:lines+=['',f"Observed whole-Mac CPU range: {min(s['cpu_percent'] for s in samples):.1f}–{max(s['cpu_percent'] for s in samples):.1f}%; includes other applications. System swap first/last: {samples[0]['swap_bytes']/1024**3:.2f}/{samples[-1]['swap_bytes']/1024**3:.2f} GiB."]
lines+=['','Two repetitions are not a confidence interval. Zero false positives on 13 selected controls does not establish library-wide precision.', '',f"Session `{protocol['session']}`; code `{protocol['git_revision']}`; sample SHA-256 `{protocol['sample_sha256']}`.",'','[Protocol](2026-11-26-cpu-threads.md) · [Journal](2026-11-26-cpu-threads.jsonl)','']
text='\n'.join(lines)
if args.write:(folder/'2026-11-26-cpu-threads-results.md').write_text(text)
print(text)
