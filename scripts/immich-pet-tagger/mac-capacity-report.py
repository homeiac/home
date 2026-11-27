#!/usr/bin/env python3
"""Summarize the latest immutable-journal Mac capacity session, including failures."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
JOURNAL=ROOT/'docs/experiments/waffles/2026-11-26-fifo-capacity.jsonl'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--write',action='store_true');args=p.parse_args()
rows=[json.loads(line) for line in JOURNAL.read_text().splitlines() if line.strip()]
start=max(i for i,r in enumerate(rows) if r['event']=='protocol');current=rows[start:];protocol=current[0]
trials=[r for r in current if r['event']=='trial_finished']
selected=next((r['selected'] for r in reversed(current) if r['event']=='experiment_completed'),None)
lines=['# Mac capacity after indexed FIFO',f"Session {protocol['session']}; source {protocol['git_revision']}.",
       'Status: '+('completed and adopted' if selected else 'canary sweep interrupted; production-first observation recorded' if any(r['event']=='production_observation_passed' for r in current) else 'interrupted' if any(r.get('error_type')=='KeyboardInterrupt' for r in current) else 'failed' if any(r['event']=='experiment_failed' for r in current) else 'running'),
       '', '| Device | Extras | Pass | Photos/min | Mean processing s | TP / FP | Changed decisions | Valid |',
       '|---|---:|---|---:|---:|---|---:|---|']
for r in trials:
    lines.append(f"| {r['device']} | {r['slots']} | {r['run'].split('-')[-1]} | {r['photos_per_minute']:.1f} | {r['mean_processing_seconds']:.3f} | {r['accuracy']['true_positive']} / {r['accuracy']['false_positive']} | {r['decisions_changed']} | {r['valid']} |")
for r in current:
    if r['event'] in ('configuration_rejected','device_escalation_stopped','experiment_failed'):
        lines.append(f"\n{r['event']}: {r.get('device','')} {r.get('slots','')} — {r['reason']}.")
if selected:
    lines.append(f"\nAdopted one permanent Metal baseline plus {selected['slots']} {selected['device']} extras. Repeated canary throughput: {selected['photos_per_minute']:.1f} photos/min, excluding baseline production and Immich writes.")
for r in current:
    if r['event']=='adoption_passed':lines.append(f"\nProduction validation: {r['seconds']:.1f} seconds; committed photos by backend: {json.dumps(r['production_delta'],sort_keys=True)}. Mac unexpected exits: {r['unexpected_exit_delta']}.")
for r in current:
    if r['event']=='production_observation_passed':lines.append(f"\nProduction adoption: {r['mac_instances']} Mac processes, {r['production_delta']['mac']} committed photos in {r['seconds']:.1f} seconds ({r['mac_photos_per_minute']:.1f}/min). Other backends: {json.dumps(r['production_delta'],sort_keys=True)}.")
    if r['event'] in ('production_capacity_window','production_capacity_accepted','production_capacity_regression','production_capacity_negative_result','production_capacity_finished'):
        lines.append('\n'+r['event']+': '+json.dumps({k:v for k,v in r.items() if k not in ('event','at')},sort_keys=True))
resources=[r['observation']['mac'] for r in current if r['event']=='resource_sample']
if resources:
    lines.append(f"\nMac observed resource range: CPU peak {max(r['cpu_percent'] for r in resources):.1f}%; minimum available {min(r['available_bytes'] for r in resources)/1024**3:.2f} GiB; maximum pressure level {max(r['pressure'] for r in resources)}. GPU utilization is whole-host, including unrelated workloads.")
lines+=['','The 122-photo canary uses frozen inputs, reversed-order repetitions and unchanged classifier/thresholds. Its 13 negative controls do not establish library-wide precision. Native guarded standby remains separately visible in the full append-only journal. Failed and interrupted sessions are retained there.']
output='\n'.join(lines)+'\n';print(output)
if args.write:(JOURNAL.parent/'2026-11-26-fifo-capacity-results.md').write_text(output)
