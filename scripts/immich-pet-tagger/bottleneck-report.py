#!/usr/bin/env python3
"""Capture repeatable read-only Waffles bottleneck measurements and compare snapshots.

Usage: python3 bottleneck-report.py capture before --directory /private/tmp/waffles-bottleneck
       python3 bottleneck-report.py capture after --directory /private/tmp/waffles-bottleneck
       python3 bottleneck-report.py compare /private/tmp/waffles-bottleneck/{before,after}.json
Optional --sample-mac runs native stack sampling with the installed worker venv.
No queue mutations, tuning, photo IDs, or credentials are included in the report.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
LIMITS=['Candidate timing is a SELECT without row locks/UPDATE; it is not total claim latency.',
        'Processing includes download and inference, but excludes claim and completion acknowledgement.',
        'Completion intervals include the independent Immich writer. Residual is estimated pipeline overhead, not measured network time.',
        'Three-minute production windows contain different photos; they are not matched hardware benchmarks.',
        'Network probe measures a small control GET, not photo download bandwidth or claim latency.']

def calculate(queue,claim,network):
    cycles=[]
    for row in queue['base_cycles']:
        cycle=float(row['completion_cycle_mean']);processing=float(row['processing_mean'])
        cycles.append({'worker':row['worker'],'samples':row['intervals'],'processing_seconds':processing,
                       'completion_interval_seconds':cycle,'estimated_nonprocessing_seconds':cycle-processing,
                       'estimated_processing_fraction':processing/cycle if cycle else None})
    plans={}
    for name,rows in claim.items():
        if not isinstance(rows,list) or not rows:continue
        plan=rows[0];node=plan['Plan']
        plans[name]={'candidate_ms':plan.get('Execution Time'),'returned_rows':node.get('Actual Rows'),
                     'shared_hits':node.get('Shared Hit Blocks'),'shared_reads':node.get('Shared Read Blocks'),
                     'plan':node}
    return {'baseline_cycles':cycles,'candidate_plans':plans,'queue_version':claim['version'],
            'control_get_median_ms':1000*network['current_urllib']['median_seconds'],
            'production_last_3m':queue['recent']}

def markdown(report):
    c=report['calculated'];lines=[f"# Waffles bottleneck capture: {report['label']}",f"Captured {report['at']}",
        f"Queue: {c['queue_version']}; control GET median: {c['control_get_median_ms']:.2f} ms.",
        '', '| Backend baseline | Samples | Processing s/photo | Completion interval s | Estimated residual s |',
        '|---|---:|---:|---:|---:|']
    for r in c['baseline_cycles']:
        lines.append(f"| {r['worker']} | {r['samples']} | {r['processing_seconds']:.4f} | {r['completion_interval_seconds']:.4f} | {r['estimated_nonprocessing_seconds']:.4f} |")
    for name,p in c['candidate_plans'].items():
        lines.append(f"\nCandidate {name}: {p['candidate_ms']} ms; returned {p['returned_rows']} row(s); shared hits {p['shared_hits']}, physical reads {p['shared_reads']}.")
    lines+=['','Interpretation limits:','']+['- '+s for s in LIMITS]
    return '\n'.join(lines)+'\n'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    cap=sub.add_parser('capture');cap.add_argument('label');cap.add_argument('--directory',type=Path,required=True);cap.add_argument('--sample-mac',action='store_true')
    comp=sub.add_parser('compare');comp.add_argument('before',type=Path);comp.add_argument('after',type=Path)
    args=parser.parse_args()
    if args.command=='compare':
        reports=[json.loads(p.read_text()) for p in [args.before,args.after]]
        print('| Capture | Backend | Processing s | Completion interval s | Estimated residual s |\n|---|---|---:|---:|---:|')
        for report in reports:
            for row in report['calculated']['baseline_cycles']:
                print(f"| {report['label']} | {row['worker']} | {row['processing_seconds']:.4f} | {row['completion_interval_seconds']:.4f} | {row['estimated_nonprocessing_seconds']:.4f} |")
        for report in reports:
            print(f"\n{report['label']} candidate timings: "+', '.join(f"{k}={v['candidate_ms']} ms ({v['returned_rows']} rows)" for k,v in report['calculated']['candidate_plans'].items()))
        print('\n'+'\n'.join('- '+s for s in LIMITS));return
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',args.label):parser.error('Use a simple alphanumeric label')
    os.umask(0o077);args.directory.mkdir(parents=True,exist_ok=True)
    path=args.directory/(args.label+'.json')
    if path.exists():raise FileExistsError('Captures are immutable; choose a new label')
    def probe(name):
        proc=subprocess.run([sys.executable,str(HERE/name)],capture_output=True,text=True,timeout=90,check=True)
        return json.loads(proc.stdout)
    names=['diagnose-queue.py','diagnose-claim.py','diagnose-network.py']
    with ThreadPoolExecutor(max_workers=3) as pool:queue,claim,network=list(pool.map(probe,names))
    report={'label':args.label,'at':datetime.now(timezone.utc).isoformat(),
            'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=HERE,text=True).strip(),
            'queue':queue,'claim':claim,'network':network,'limits':LIMITS,'calculated':calculate(queue,claim,network)}
    if args.sample_mac:
        python=Path.home()/'Library/Application Support/immich-pet-tagger/venv/bin/python'
        proc=subprocess.run([str(python),str(HERE/'diagnose-mac.py'),str(args.directory/'native')],capture_output=True,text=True,timeout=90,check=True)
        report['mac']=json.loads(proc.stdout)
    path.write_text(json.dumps(report,indent=2)+'\n');path.with_suffix('.md').write_text(markdown(report))
    print(markdown(report));print('Saved '+str(path))

if __name__=='__main__':main()
