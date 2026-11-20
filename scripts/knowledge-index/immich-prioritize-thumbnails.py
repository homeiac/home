#!/usr/bin/env python3
"""Prioritize existing thumbnail jobs for the first page of the timeline (#217).

Read-only SQL selects missing derivatives; BullMQ's supported changePriority API
moves only matching waiting jobs forward. No jobs are created or deleted, and no
Immich metadata, originals, faces or authentication records are changed.
Uses the existing kubeconfig; no application credentials are required.
"""
import argparse
import json
from pathlib import Path
import subprocess
import uuid

KUBE = ['kubectl','--kubeconfig',str(Path.home()/'kubeconfig'),'-n','immich-pilot']


def run(limit: int, apply: bool) -> None:
    """Inspect or expedite a bounded set of normal timeline thumbnails."""
    if not 1 <= limit <= 100:
        raise ValueError('Limit must be 1 through 100')
    query = '''SELECT a.id FROM asset a
        WHERE a.visibility='timeline' AND a."deletedAt" IS NULL
        AND NOT EXISTS (SELECT 1 FROM asset_file f WHERE f."assetId"=a.id AND f.type='thumbnail')
        ORDER BY a."localDateTime" DESC,a.id LIMIT '''+str(limit)
    output = subprocess.check_output(KUBE+['exec','deployment/immich-postgres','--',
        'psql','-U','immich','-d','immich','-At','-c',query],text=True)
    assets = [str(uuid.UUID(x)) for x in output.splitlines() if x]
    print(json.dumps(dict(missing_timeline_thumbnails=len(assets),apply=apply)),flush=True)
    if not apply or not assets:
        return
    script = '''import {createRequire} from 'node:module';
const require=createRequire('/usr/src/app/server/package.json');
const {Queue}=require('bullmq');
const targets=new Set(TARGETS);
const q=new Queue('thumbnailGeneration',{prefix:'immich_bull',connection:{host:'immich-valkey',port:6379}});
try {
  const found=[];
  const count=await q.getWaitingCount();
  // Collect before reordering so moving jobs cannot skip the remaining pages.
  for(let start=0;start<count;start+=500){
    for(const j of await q.getJobs(['wait'],start,start+499,true)){
      if(j.name==='AssetGenerateThumbnails' && targets.has(j.data.id))found.push(j);
    }
  }
  let moved=0;
  for(const j of found){
    if(await j.getState()==='waiting'){
      await j.changePriority({priority:0,lifo:true});
      moved++;
    }
  }
  console.log(JSON.stringify({prioritized:moved,selected:targets.size,waiting:await q.getWaitingCount()}));
} finally {await q.close();}
'''.replace('TARGETS',json.dumps(assets))
    subprocess.run(KUBE+['exec','-i','deployment/immich-server','--','node','--input-type=module'],
        input=script,text=True,check=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,default=60)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    run(args.limit,args.apply)
