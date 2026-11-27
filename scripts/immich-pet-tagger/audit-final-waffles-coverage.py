#!/usr/bin/env python3
"""Count unique final Waffles assets and compare frozen versus current dog descriptions.

Read-only database export. Identifiers/captions stay in the private output directory;
only aggregate results are printed or optionally written to a public report.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
from distributed import KUBE

RUNS=['historical-waffles','waffles-media-recovery-20261127','waffles-motion-recovery-20261127']
PATTERNS={'literal_dog':re.compile(r'\bdogs?\b',re.I),
          'dog_terms':re.compile(r'\b(dogs?|pupp(?:y|ies)|canines?|husk(?:y|ies)|shepherds?|retrievers?)\b',re.I)}

def compare(rows: list[dict], captions: dict[str,str]) -> dict:
    """Compare description candidates against unique final model results."""
    report={}
    for name,pattern in PATTERNS.items():
        selected={r['asset_id'] for r in rows if pattern.search(captions.get(r['asset_id'],'') or '')}
        positive={r['asset_id'] for r in rows if r['matched']}
        completed={r['asset_id'] for r in rows if r['status']=='complete'}
        selected_complete=selected&completed
        rejected=selected_complete-positive
        report[name]={'description_candidates':len(selected),'waffles_matches_in_candidates':len(selected&positive),
            'waffles_matches_outside_candidates':len(positive-selected),'candidates_complete_without_waffles_match':len((selected&completed)-positive),
            'candidates_unresolved':len(selected-completed),
            'recovered_waffles_in_candidates':sum(r['matched'] and r['run_id']!='historical-waffles' and r['asset_id'] in selected for r in rows),
            'complete_candidates_by_media':dict(Counter(r['type'] for r in rows if r['asset_id'] in selected_complete)),
            'unmatched_candidates_by_outcome':dict(Counter(r['outcome'] for r in rows if r['asset_id'] in rejected))}
        assert len(selected&positive)+len(rejected)+len(selected-completed)==len(selected)
    return report


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--output',type=Path);p.add_argument('--reuse-export',action='store_true');a=p.parse_args()
    os.umask(0o077);a.directory.mkdir(parents=True,exist_ok=True);root=a.directory.parent
    sql="""BEGIN READ ONLY; SET LOCAL statement_timeout='30s';
SELECT jsonb_build_object('kind','job','asset_id',asset_id,'run_id',run_id,'status',status,'applied',applied,
'matched',coalesce(jsonb_array_length(result->'matches'),0)>0,'unknown',coalesce((result->>'unknown')::int,0),
'low_confidence',coalesce((result->>'low_confidence')::int,0),'out_of_range',coalesce((result->>'out_of_range')::int,0))
FROM waffles.jobs WHERE run_id IN ('historical-waffles','waffles-media-recovery-20261127','waffles-motion-recovery-20261127');
SELECT jsonb_build_object('kind','description','asset_id',asset_id,
'summary',coalesce(applied->>'summary',payload->>'summary',''),
'description',coalesce(applied->>'summary',payload->>'summary','') || ' ' || coalesce((applied->'tags')::text,(payload->'tags')::text,''))
FROM immich_sync.jobs WHERE asset_id IS NOT NULL;
COMMIT;"""
    print('START: read-only count of unique Waffles results and description coverage',flush=True)
    if a.reuse_export:records=json.loads((a.directory/'database-export.json').read_text())
    else:
        result=subprocess.run(KUBE+['-n','database','exec','-i','postgres-postgresql-0','--','psql','-XAtq','-v','ON_ERROR_STOP=1','-U','postgres','-d','photo_enrichment'],input=sql,text=True,capture_output=True,check=True,timeout=120)
        records=[json.loads(s) for s in result.stdout.splitlines() if s.startswith('{')]
        (a.directory/'database-export.json').write_text(json.dumps(records)+'\n')
    jobs=[r for r in records if r['kind']=='job'];by_id={}
    for run in RUNS:
        for row in jobs:
            if row['run_id']==run and (row['asset_id'] not in by_id or row['status']=='complete'):
                by_id[row['asset_id']]=dict(row)
    inventory={r['id']:r for r in json.loads((root/'distributed/inventory.json').read_text())}
    for row in by_id.values():
        row['type']=inventory[row['asset_id']]['type']
        row['outcome']=('matched' if row['matched'] else 'low_confidence' if row['low_confidence'] else 'unknown' if row['unknown'] else 'out_of_range' if row['out_of_range'] else 'no_detection')
    rows=list(by_id.values())
    frozen=json.loads((root/'production-quality-20261127/descriptions.json').read_text())
    old={r['asset_id']:r['description'] for r in frozen}
    current={};summaries={}
    for row in records:
        if row['kind']=='description':
            current[row['asset_id']]=current.get(row['asset_id'],'')+' '+row['description']
            summaries[row['asset_id']]=summaries.get(row['asset_id'],'')+' '+row['summary']
    by_run={}
    for run in RUNS:
        subset=[r for r in rows if r['run_id']==run and r['matched']]
        by_run[run]={'waffles_assets':len(subset),'media':dict(Counter(r['type'] for r in subset)),
            'new_assignments':sum(r['applied'] or 0 for r in jobs if r['run_id']==run)}
    audit=json.loads((root/'query-quality-20261127/visual-labels.json').read_text())
    manifest_file=root/'query-quality-20261127/sample.json'
    assert hashlib.sha256(manifest_file.read_bytes()).hexdigest()==audit['manifest_sha256']
    manifest=json.loads(manifest_file.read_text())
    audited_miss_indices={r['index'] for r in audit['labels'] if r['clear_waffles_model_miss']}
    # Samples use the original frozen identifier field; retain the list only privately.
    misses=[r for r in manifest if r['index'] in audited_miss_indices]
    (a.directory/'visually-reviewed-misses.json').write_text(json.dumps(misses,indent=2)+'\n')
    report={'observed_at':datetime.now(timezone.utc).isoformat(),'population':len(rows),
        'complete':sum(r['status']=='complete' for r in rows),'unresolved':sum(r['status']!='complete' for r in rows),
        'unique_waffles_assets':sum(r['matched'] for r in rows),'waffles_by_media':dict(Counter(r['type'] for r in rows if r['matched'])),
        'by_run':by_run,'frozen_descriptions_and_tags':compare(rows,old),
        'current_descriptions_and_tags':compare(rows,current),'current_summary_only':compare(rows,summaries),
        'previous_visual_audit':{'description_positive_classifier_negative_sample':32,'visible_dog':26,'clear_waffles_misses':len(misses),
            'still_unmatched':sum(not by_id[r['asset_id']]['matched'] for r in misses),
            'in_frozen_literal_dog_candidates':sum(bool(PATTERNS['literal_dog'].search(old.get(r['asset_id'],''))) for r in misses),
            'reviewer':'assistant visual inspection, not owner confirmation'}}
    assert report['unique_waffles_assets']==sum(r['waffles_assets'] for r in by_run.values())
    (a.directory/'final-assets.json').write_text(json.dumps(rows)+'\n')
    (a.directory/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
