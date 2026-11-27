#!/usr/bin/env python3
"""Read committed production photos per backend over a recent, explicit window."""
import argparse
import json
import subprocess
from distributed import KUBE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seconds',type=int,default=60);args=p.parse_args()
assert 30<=args.seconds<=3600
code='''import {createRequire} from 'node:module';const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();await db.query('BEGIN READ ONLY');
const seconds=Number(process.argv[2]);const rows=(await db.query(`SELECT j.worker,count(*)::int completed,round((count(*)*60.0/$1)::numeric,1) photos_per_minute FROM waffles.jobs j JOIN waffles.runs r ON r.id=j.run_id WHERE r.mode='production' AND j.status='complete' AND j.completed_at>now()-$1*interval '1 second' GROUP BY j.worker ORDER BY completed DESC`,[seconds])).rows;
console.log(JSON.stringify({at:new Date().toISOString(),window_seconds:seconds,backends:rows}));await db.query('ROLLBACK');await db.end();'''
r=subprocess.run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-',str(args.seconds)],input=code,text=True,capture_output=True,check=True)
print(json.dumps(json.loads(r.stdout),indent=2))
