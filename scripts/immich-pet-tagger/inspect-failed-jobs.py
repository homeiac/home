#!/usr/bin/env python3
"""Inspect aggregate retry outcomes and failed thumbnails without printing photo IDs."""
import subprocess
import argparse
from distributed import KUBE

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--annotate',action='store_true',help='Retain verified thumbnail HTTP status on already-failed jobs; never reset attempts')
args=parser.parse_args()
code='''import {createRequire} from 'node:module';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();
console.log(JSON.stringify((await db.query(`SELECT status,worker,last_error,count(*)::int jobs FROM waffles.jobs WHERE run_id='historical-waffles' AND (attempts>1 OR status='failed') GROUP BY status,worker,last_error`)).rows));
const jobs=(await db.query("SELECT asset_id,last_error,worker,attempts FROM waffles.jobs WHERE run_id='historical-waffles' AND status='failed' ORDER BY ordinal LIMIT 20")).rows;
for(const j of jobs){const url='http://immich-server.immich-pilot.svc.cluster.local:2283/api/assets/'+j.asset_id,options={headers:{'x-api-key':process.env.IMMICH_API_KEY}};const response=await fetch(url+'/thumbnail?size=preview',options);const asset=await fetch(url,options);const details=asset.ok?await asset.json():{};let annotated=0;if(process.argv.includes('--annotate')&&!response.ok)annotated=(await db.query("UPDATE waffles.jobs SET last_error=$2 WHERE run_id='historical-waffles' AND asset_id=$1 AND status='failed'",[j.asset_id,'thumbnail_http_'+response.status])).rowCount;console.log(JSON.stringify({worker:j.worker,error:j.last_error,attempts:j.attempts,thumbnail_status:response.status,asset_status:asset.status,type:details.type,isOffline:details.isOffline,isTrashed:details.isTrashed,annotated}));}
await db.end();'''
subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-']+(['--annotate'] if args.annotate else []),input=code,text=True,check=True)
