#!/usr/bin/env python3
"""Read back review-run assignments and keep per-photo verification private."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
from distributed import KUBE

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();os.umask(0o077)
 print('Starting private database and Immich face readback...',flush=True)
 code="""import {createRequire} from 'node:module';const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const base=process.env.IMMICH_URL??'http://immich-server.immich-pilot.svc.cluster.local:2283';
const db=new Client();await db.connect();
const run=(await db.query("SELECT id,state,config FROM waffles.runs WHERE id='waffles-reviewed-recovery-20261127'")).rows[0];
if(!run)throw Error('Review run missing');
const jobs=(await db.query('SELECT asset_id,status,result,applied,last_error,apply_attempts FROM waffles.jobs WHERE run_id=$1',[run.id])).rows;
const targets=jobs.filter(j=>j.result?.matches?.length);let position=0;
async function verify(){for(;;){const index=position++;if(index>=targets.length)return;const j=targets[index];
try{const r=await fetch(base+'/api/faces?id='+j.asset_id,{headers:{'x-api-key':process.env.IMMICH_API_KEY},signal:AbortSignal.timeout(15000)});
if(!r.ok)throw Error('Face readback failed');const faces=await r.json();j.waffles_faces=faces.filter(f=>(f.person?.id??f.personId)===run.config.person_id).length;
}catch(e){j.verification_error=e.name;}}
}
await Promise.all(Array.from({length:4},verify));await db.end();console.log(JSON.stringify({run:run.id,state:run.state,jobs}));"""
 result=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'],input=code,text=True,capture_output=True,timeout=240)
 # Only private output includes IDs or model explanations.
 if result.returncode:
  (a.directory/'readback-error.log').write_text(result.stderr);raise RuntimeError('Readback failed; private diagnostics retained')
 data=json.loads(result.stdout);(a.directory/'recovery-readback.json').write_text(json.dumps(data,indent=2)+'\n')
 inventory={r['id']:r for r in json.loads((a.directory.parent/'distributed/inventory.json').read_text())}
 matched=[r for r in data['jobs'] if r['result'].get('matches')];verified=[r for r in matched if r.get('waffles_faces',0)==1]
 nine={r['asset_id'] for r in json.loads((a.directory/'nine-misses.json').read_text())}
 report={'at':datetime.now(timezone.utc).isoformat(),'run':data['run'],'state':data['state'],'statuses':dict(Counter(r['status'] for r in data['jobs'])),
 'recovery_candidates':len(matched),'verified_unique_assignments':len(verified),'new_faces_added':sum(r['applied'] for r in matched),
 'recovered_by_media':dict(Counter(inventory[r['asset_id']]['type'] for r in verified)),
 'duplicate_waffles_faces':sum(r.get('waffles_faces',0)>1 for r in matched),'missing_or_failed_readback':sum(r.get('waffles_faces')!=1 for r in matched),
 'original_nine_recovered':sum(r['asset_id'] in nine for r in verified),
 'union_with_previous_833':833+len(verified),'scope_note':'Recovery cohort excluded the previous 833 model-positive assets. Readback confirms current assignment, not population recall.'}
 if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))

if __name__=='__main__':main()
