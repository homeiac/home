#!/usr/bin/env python3
"""Read the experiment journal and optionally render its aggregate results."""
import argparse
import json
import re
from experiment import JOURNAL,ROOT

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--live',action='store_true')
parser.add_argument('--write',action='store_true')
parser.add_argument('--allow-partial',action='store_true')
args=parser.parse_args()
events=[json.loads(line) for line in JOURNAL.read_text().splitlines() if line.strip()]
trials=[e for e in events if e['event']=='trial_finished']
print('Latest journal event:',events[-1]['at'],events[-1]['event'])
for e in trials:
    print(f"{e['run']}: {e['photos_per_minute']:.2f} photos/min; valid={e['valid']}; TP={e['accuracy']['true_positive']}/13 FP={e['accuracy']['false_positive']}/13; changed={e['decisions_changed']}")
if args.live:
    from distributed import request
    data=request('/admin/status');active={}
    for row in data['runs']:
        if row['state']=='running' and row['mode']=='benchmark':
            statuses=active.setdefault(row['id'],{})
            statuses[row['status']]=statuses.get(row['status'],0)+row['jobs']
    print('Active benchmark runs:',json.dumps(active))
    print('Active process counts:',json.dumps({w['name']:w['active_instances'] for w in data['workers']}))
if args.write:
    complete=[e for e in events if e['event']=='experiment_completed']
    if not complete and not args.allow_partial:raise RuntimeError('Use --allow-partial to publish an explicitly interrupted result')
    lines=['# Waffles live tuning results'+(' — interrupted' if not complete else ''),'',
           'See the [preregistered protocol](2026-11-26-live-tuning.md) and [append-only journal](2026-11-26-live-tuning.jsonl).',
           'Times are UTC. These are warm benchmark results on 122 fixed photos, including 26 reviewed holdouts. Benchmark runs do not write Immich faces.','',
           '| Trial | Photos/min | Wall seconds | Mean seconds/photo | P95 seconds | Waffles / 13 | False positives / 13 | Changed decisions | Valid |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    for e in trials:
        lines.append(f"| {e['run']} | {e['photos_per_minute']:.2f} | {e['wall_seconds']:.3f} | {e['mean_processing_seconds']:.3f} | {e['p95_seconds']:.3f} | {e['accuracy']['true_positive']} | {e['accuracy']['false_positive']} | {e['decisions_changed']} | {e['valid']} |")
    lines+=['','## Selection and repeatability','']
    for e in events:
        if e['event']=='backend_selected':
            lines.append(f"- {e['worker']}: selected {e['slots']} process(es), using the preregistered 5% preference for fewer processes.")
            for c in e['candidates']:
                lines.append(f"  - {c['slots']} process(es): pooled {c['photos_per_minute']:.2f} photos/min; fastest/slowest repetition spread {100*c['repeat_spread']:.1f}%.")
    combined={}
    for profile in ('before','after'):
        rows=[e for e in trials if '-pool-'+profile+'-' in e['run'] and e['valid']]
        if len(rows)==2:combined[profile]=60*sum(e['photos'] for e in rows)/sum(e['wall_seconds'] for e in rows)
    if len(combined)==2:
        lines+=['',f"Combined pool: **{combined['before']:.2f} → {combined['after']:.2f} photos/min ({combined['after']/combined['before']:.3f}×)**."]
    lines+=['','## Resource observations','',
            'Values below are snapshots after each pass. Process RSS is the sum of process high-water marks, not current memory, and may exclude Metal allocations. Swap is system-wide and includes unrelated applications. Kubernetes CPU values average the preceding minute; working-set values are snapshots, not measured peaks.','',
            '| Trial | Mac process peak RSS, GiB | still-fawn working set, GiB | still-fawn CPU cores | Mac swap used, GiB |',
            '|---|---:|---:|---:|---:|']
    for e in trials:
        s=e['resource_snapshot']
        rss=next(int(w['rss_bytes']) for w in s['workers'] if w['name']=='mac')/2**30
        memory=sum(float(m['value']) for m in s['metrics']['k8s_working_set_bytes'] if 'still-fawn' in m['labels'].get('pod',''))/2**30
        cpu=sum(float(m['value']) for m in s['metrics']['k8s_cpu_cores'] if 'still-fawn' in m['labels'].get('pod',''))
        swap=float(re.search(r'used = ([\d.]+)M',s['mac_host']['swap'])[1])/1024
        lines.append(f"| {e['run']} | {rss:.2f} | {memory:.2f} | {cpu:.2f} | {swap:.2f} |")
    lines+=['','## Deviations, failures and observations','']
    for e in events:
        if e['event'] in ('operator_note','trial_failed','experiment_failed','restoration_failed'):
            lines.append(f"- {e['at']}: {e.get('note',e.get('reason',e.get('error_type','Restoration failed')))}")
    lines+=['','## Interpretation limits','',
            'Two repetitions per configuration provide a directional result, not a confidence interval. Background desktop activity, source I/O and shared-host load can vary. The journal includes CPU, memory, swap and process observations before and after each pass. A selected sample of 13 positive and 13 negative dogs cannot establish library-wide precision or recall. Production throughput also includes Immich writes.','',
            ('The selected settings were persisted and the previously running production queues were resumed.' if complete else 'The user interrupted this protocol to require continuous baseline workers on all nodes. Production was restored at one worker per admitted backend. The combined ABBA comparison was not run; no final combined gain or completed-study selection is claimed.'),
            'RTX remained unused. Subsequent continuous-production measurements belong to a separate protocol.','']
    destination=JOURNAL.with_name('2026-11-26-live-tuning-results.md')
    destination.write_text('\n'.join(lines))
    print('Wrote',destination)
